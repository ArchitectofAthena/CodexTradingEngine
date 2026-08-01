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
USES = re.compile(r"^\s*uses:\s*([^\s#]+)", re.M)
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
    return text.count("\n", 0, index) + 1


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def bool_literal(node: ast.AST | None) -> bool | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, bool) else None


def safe_yaml_loader(call: ast.Call) -> bool:
    loader = dotted(kw(call, "Loader")) if kw(call, "Loader") is not None else ""
    return loader.endswith("SafeLoader") or loader.endswith("CSafeLoader")


def scan_python(root: Path) -> list[Finding]:
    out: list[Finding] = []
    for path in files(root, {".py"}):
        if any(part in RUNTIME_SKIP for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name, lineno = dotted(node.func), getattr(node, "lineno", 1)
            item: tuple[str, str, str] | None = None
            if name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
                item = ("PY001", "HIGH", f"dynamic code execution via {name}")
            elif name in {"os.system", "os.popen"}:
                item = ("PY002", "HIGH", f"shell command execution via {name}")
            elif name.startswith("subprocess.") and bool_literal(kw(node, "shell")) is True:
                item = ("PY003", "HIGH", "subprocess call enables shell=True")
            elif name in {"pickle.load", "pickle.loads", "dill.load", "dill.loads", "marshal.load", "marshal.loads"}:
                item = ("PY004", "HIGH", f"unsafe deserialization via {name}")
            elif name in {"yaml.load", "yaml.full_load"} and not safe_yaml_loader(node):
                item = ("PY005", "HIGH", f"unsafe YAML loader via {name}")
            elif name == "ssl._create_unverified_context":
                item = ("PY006", "HIGH", "TLS certificate verification disabled")
            elif name.startswith(("requests.", "httpx.")) and bool_literal(kw(node, "verify")) is False:
                item = ("PY007", "HIGH", f"TLS verification disabled in {name}")
            elif name == "tempfile.mktemp":
                item = ("PY008", "MEDIUM", "race-prone tempfile.mktemp usage")
            elif name in {"hashlib.md5", "hashlib.sha1"} and bool_literal(kw(node, "usedforsecurity")) is not False:
                item = ("PY009", "MEDIUM", f"weak hash primitive {name}")
            if item:
                out.append(Finding.make(item[0], item[1], path, lineno, item[2], root))
        for match in AUTHORITY_TRUE.finditer(source):
            out.append(Finding.make("BOUNDARY001", "HIGH", path, line_of(source, match.start()), "runtime authority boundary is explicitly enabled", root))
    return out


def placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return any(token in lowered for token in PLACEHOLDERS) or len(set(lowered)) <= 3


def scan_secrets(root: Path) -> list[Finding]:
    out: list[Finding] = []
    for path in files(root, TEXT_SUFFIXES):
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for rule, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                out.append(Finding.make(rule, "HIGH", path, line_of(text, match.start()), "high-confidence secret-shaped material detected; value redacted", root))
        if any(part in {"tests", "test", "fixtures", "docs", "examples"} for part in path.parts):
            continue
        for match in GENERIC_SECRET.finditer(text):
            if not placeholder(match.group(2)):
                out.append(Finding.make("SEC006", "HIGH", path, line_of(text, match.start()), f"hard-coded {match.group(1)} assignment detected; value redacted", root))
    return out


def scan_workflows(root: Path) -> list[Finding]:
    out: list[Finding] = []
    folder = root / ".github" / "workflows"
    if not folder.exists():
        return out
    for path in folder.glob("*.y*ml"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for token, rule, message in (
            ("pull_request_target", "GH001", "pull_request_target exposes privileged context to untrusted changes"),
            ("permissions: write-all", "GH002", "workflow grants write-all token permissions"),
        ):
            idx = text.find(token)
            if idx >= 0:
                out.append(Finding.make(rule, "HIGH", path, line_of(text, idx), message, root))
        for match in CURL_PIPE.finditer(text):
            out.append(Finding.make("GH004", "HIGH", path, line_of(text, match.start()), "network download is piped directly into a shell", root))
        for match in USES.finditer(text):
            spec = match.group(1)
            if spec.startswith(("./", "docker://")):
                continue
            if "@" not in spec:
                out.append(Finding.make("GH003", "MEDIUM", path, line_of(text, match.start()), f"action {spec} has no immutable ref", root))
                continue
            action, ref = spec.rsplit("@", 1)
            if not FULL_SHA.fullmatch(ref):
                out.append(Finding.make("GH003", "MEDIUM", path, line_of(text, match.start()), f"action {action} uses mutable ref {ref!r}", root))
    return out


def scan_containers(root: Path) -> list[Finding]:
    out: list[Finding] = []
    checks = (
        (re.compile(r"(?mi)^\s*privileged:\s*true\s*$"), "CTR001", "HIGH", "container runs privileged"),
        (re.compile(r"(?mi)^\s*network_mode:\s*host\s*$"), "CTR002", "MEDIUM", "container shares the host network namespace"),
        (re.compile(r"(?mi)^\s*(?:pid|ipc):\s*host\s*$"), "CTR003", "HIGH", "container shares a host namespace"),
        (re.compile(r"(?m)^\s*-\s*/var/run/docker\.sock:"), "CTR004", "HIGH", "container mounts the Docker control socket"),
        (re.compile(r"(?mi)^\s*cap_add:\s*$"), "CTR005", "MEDIUM", "container adds Linux capabilities"),
    )
    for path in files(root, {".yml", ".yaml"}):
        if "compose" not in path.name.lower():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, rule, severity, message in checks:
            for match in pattern.finditer(text):
                out.append(Finding.make(rule, severity, path, line_of(text, match.start()), message, root))
    for path in files(root):
        if not path.name.lower().startswith("dockerfile"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?mi)^\s*FROM\s+([^\s]+)", text)
        if match and "@sha256:" not in match.group(1):
            out.append(Finding.make("CTR006", "MEDIUM", path, line_of(text, match.start()), "base image uses a mutable tag rather than a digest pin", root))
        if not re.search(r"(?mi)^\s*USER\s+(?!0\b|root\b)", text):
            out.append(Finding.make("CTR007", "MEDIUM", path, 1, "Dockerfile lacks a non-root runtime USER", root))
    return out


def allowlist(root: Path) -> set[str]:
    path = root / ".security-audit-allowlist.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("fingerprints", [])
    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
        raise SystemExit(".security-audit-allowlist.json fingerprints must be strings")
    return set(values)


def markdown(findings: Sequence[Finding], suppressed: int) -> str:
    counts = {key: 0 for key in ORDER}
    for item in findings:
        counts[item.severity] += 1
    lines = ["# Security Audit", "", f"- Schema: `{SCHEMA}`", f"- Findings: **{len(findings)}**", f"- Suppressed: **{suppressed}**", f"- Critical: **{counts['CRITICAL']}**", f"- High: **{counts['HIGH']}**", f"- Medium: **{counts['MEDIUM']}**", ""]
    if findings:
        lines += ["| Severity | Rule | Location | Finding | Fingerprint |", "|---|---|---|---|---|"]
        for item in findings:
            lines.append(f"| {item.severity} | `{item.rule_id}` | `{item.path}:{item.line}` | {item.message.replace('|', '\\|')} | `{item.fingerprint}` |")
        lines += ["", "Suspected secret values are always redacted."]
    else:
        lines.append("No findings.")
    return "\n".join(lines) + "\n"


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
