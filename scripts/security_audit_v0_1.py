#!/usr/bin/env python3
"""Dependency-free repository security scanner with redacted findings."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Sequence

SCHEMA = "spiralbloom.security_audit.v0.1"
ORDER = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
SKIP = {".git", ".venv", "venv", "node_modules", "dist", "build", "htmlcov", "__pycache__", "security-artifacts"}
RUNTIME_SKIP = SKIP | {"tests", "test", "fixtures"}
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".env", ".md", ".txt", ".js", ".ts", ".sh"}
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.M)
CURL_PIPE = re.compile(r"(?i)\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh)\b")
AUTHORITY_TRUE = re.compile(r"(?m)^\s*(?:AUTHORITY|execution_authority|capital_movement_authority|wallet_authority|signing_authority)\s*[:=]\s*True\b")
SECRET_PATTERNS = (
    ("SEC001", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("SEC002", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SEC003", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("SEC004", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("SEC005", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)
GENERIC_SECRET = re.compile(r'''(?ix)\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|private[_-]?key|secret[_-]?key|password|passwd|mnemonic|seed[_-]?phrase)\b\s*[:=]\s*["']([^"']{8,})["']''')
PLACEHOLDERS = ("example", "placeholder", "changeme", "replace_me", "replace-me", "redacted", "dummy", "fake", "sample", "not-a-secret", "not_a_secret", "${", "{{", "<")

@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    path: str
    line: int
    message: str
    fingerprint: str

    @classmethod
    def make(cls, rule: str, severity: str, path: Path, line: int, message: str, root: Path) -> "Finding":
        rel = path.relative_to(root).as_posix()
        fp = hashlib.sha256(f"{rule}\0{rel}\0{line}\0{message}".encode()).hexdigest()[:20]
        return cls(rule, severity, rel, int(line), message, fp)


def files(root: Path, suffixes: set[str] | None = None) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP for part in path.parts):
            continue
        if suffixes is not None and path.suffix.lower() not in suffixes and not path.name.lower().startswith("dockerfile"):
            continue
        yield path


def line_of(text: str, index: int) -> int:
    return text.count("\n            safe_message = item.message.replace("|", "\\|")\n            lines.append(f"| {item.severity} | `{item.rule_id}` | `{item.path}:{item.line}` | {safe_message} | `{item.fingerprint}` |")\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", default="security-artifacts/security-audit.json")
    parser.add_argument("--markdown", default="security-artifacts/security-audit.md")
    parser.add_argument("--fail-on", choices=tuple(ORDER), default="HIGH")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    raw = scan_python(root) + scan_secrets(root) + scan_workflows(root) + scan_containers(root)
    unique = {item.fingerprint: item for item in raw}
    allowed = allowlist(root)
    active = [item for fp, item in unique.items() if fp not in allowed]
    active.sort(key=lambda item: (-ORDER[item.severity], item.path, item.line, item.rule_id))
    counts = {key: 0 for key in ORDER}
    for item in active:
        counts[item.severity] += 1
    payload = {"schema": SCHEMA, "root": root.name, "fail_on": args.fail_on, "counts": counts, "suppressed": len(set(unique) & allowed), "findings": [asdict(item) for item in active]}
    json_path, md_path = root / args.json, root / args.markdown
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = markdown(active, payload["suppressed"])
    md_path.write_text(report, encoding="utf-8")
    print(report)
    threshold = ORDER[args.fail_on]
    blockers = [item for item in active if ORDER[item.severity] >= threshold]
    if blockers:
        print(f"blocked by {len(blockers)} finding(s) at or above {args.fail_on}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
