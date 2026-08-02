#!/usr/bin/env python3
"""Repository leak and exposure scanner with redacted findings."""
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

SCHEMA = "spiralbloom.leak_audit.v0.2"
ORDER = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
SKIP = {
    ".git", ".venv", "venv", "node_modules", "dist", "build", "htmlcov",
    "__pycache__", "security-artifacts", ".mypy_cache", ".pytest_cache",
}
RUNTIME_SKIP = SKIP | {"tests", "test", "fixtures", "docs", "examples"}
TEXT_SUFFIXES = {
    ".py", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".env",
    ".md", ".txt", ".js", ".ts", ".sh", ".ps1",
}
SECRET_PATTERNS = (
    ("LEAK001", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("LEAK002", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("LEAK003", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("LEAK004", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("LEAK005", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("LEAK006", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("LEAK007", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("LEAK008", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
)
GENERIC_SECRET = re.compile(
    r'''(?ix)\b(api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|
    private[_-]?key|secret[_-]?key|password|passwd|mnemonic|seed[_-]?phrase|
    wallet[_-]?key)\b\s*[:=]\s*["']([^"']{8,})["']'''
)
PLACEHOLDERS = (
    "example", "placeholder", "changeme", "replace_me", "replace-me", "redacted",
    "dummy", "fake", "sample", "not-a-secret", "not_a_secret", "this-is-not",
    "${", "{{", "<",
)
SENSITIVE_NAMES = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_dsa", "id_ecdsa",
    "id_ed25519", "credentials.json", "service-account.json", "wallet.dat",
    "keystore.json",
}
SENSITIVE_SUFFIXES = {".pem", ".p12", ".pfx", ".jks", ".key"}
AUTHORITY_TRUE = re.compile(
    r'''(?im)^\s*["']?(?:AUTHORITY|execution_authority|capital_movement_authority|
    wallet_authority|signing_authority|may_execute|may_move_capital)["']?\s*[:=]\s*true\b''',
    re.X,
)
UNTRUSTED_CONTEXT = re.compile(
    r"\$\{\{\s*github\.event\.(?:pull_request\.(?:title|body|head\.ref)|"
    r"issue\.(?:title|body)|comment\.body|review\.body|head_commit\.message)"
)
SECRET_ECHO = re.compile(r"(?im)^\s*(?:echo|printf|Write-Host)\b[^\n]*\$\{\{\s*secrets\.")
ENV_DUMP = re.compile(r"(?im)^\s*(?:env|printenv|set|export\s+-p|Get-ChildItem\s+Env:)\s*$")
INSECURE_DOWNLOAD = re.compile(
    r"(?i)\b(?:curl\b[^\n]*(?:\s-k\b|--insecure\b)|wget\b[^\n]*--no-check-certificate\b)"
)
WORLD_WRITABLE = re.compile(r"(?i)\bchmod\s+(?:-R\s+)?(?:0?777|a\+rwx)\b")
PUBLIC_BIND = re.compile(
    r"(?i)(?:host\s*[:=]\s*[\"']?0\.0\.0\.0|listen(?:_address)?\s*[:=]\s*[\"']?0\.0\.0\.0|--host(?:=|\s+)0\.0\.0\.0)"
)


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


def keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def bool_literal(node: ast.AST | None) -> bool | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, bool) else None


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
        in_fixture = any(part in {"tests", "test", "fixtures", "docs", "examples"} for part in path.parts)
        if (path.name.lower() in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES) and not in_fixture:
            out.append(Finding.make("LEAK009", "HIGH", path, 1, "sensitive credential or key file is tracked", root))
        for rule, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                out.append(Finding.make(rule, "HIGH", path, line_of(text, match.start()), "high-confidence secret-shaped material detected; value redacted", root))
        if in_fixture:
            continue
        for match in GENERIC_SECRET.finditer(text):
            if not placeholder(match.group(2)):
                out.append(Finding.make("LEAK010", "HIGH", path, line_of(text, match.start()), f"hard-coded {match.group(1)} assignment detected; value redacted", root))
    return out


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
            name = dotted(node.func)
            line = getattr(node, "lineno", 1)
            if name.endswith((".extractall", ".extract")):
                out.append(Finding.make("PYL001", "MEDIUM", path, line, f"archive extraction requires traversal review: {name}", root))
            if name.endswith((".execute", ".executemany")) and node.args and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp)):
                out.append(Finding.make("PYL002", "MEDIUM", path, line, "dynamic SQL statement construction", root))
            if name.endswith(".run") and bool_literal(keyword(node, "debug")) is True:
                out.append(Finding.make("PYL003", "HIGH", path, line, "debug server mode enabled", root))
            if name in {"requests.get", "requests.post", "requests.put", "requests.patch", "requests.delete", "httpx.get", "httpx.post"} and keyword(node, "timeout") is None:
                out.append(Finding.make("PYL004", "MEDIUM", path, line, f"network request has no explicit timeout: {name}", root))
            if name.startswith(("logging.", "logger.", "self.logger.")):
                rendered = ast.get_source_segment(source, node) or ""
                if re.search(r"(?i)\b(?:authorization|cookie|token|secret|password|mnemonic|private[_-]?key)\b", rendered):
                    out.append(Finding.make("PYL005", "MEDIUM", path, line, "logging call may expose credential-bearing material", root))
        for match in AUTHORITY_TRUE.finditer(source):
            out.append(Finding.make("BOUNDARY002", "HIGH", path, line_of(source, match.start()), "runtime authority boundary is explicitly enabled", root))
    return out


def scan_workflows(root: Path) -> list[Finding]:
    out: list[Finding] = []
    folder = root / ".github" / "workflows"
    if not folder.exists():
        return out
    for path in folder.glob("*.y*ml"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, rule, severity, message in (
            (SECRET_ECHO, "GHL001", "CRITICAL", "workflow prints a GitHub secret expression"),
            (ENV_DUMP, "GHL002", "HIGH", "workflow dumps the complete environment"),
            (UNTRUSTED_CONTEXT, "GHL003", "HIGH", "untrusted GitHub event text is interpolated into shell-capable workflow text"),
            (INSECURE_DOWNLOAD, "GHL004", "HIGH", "workflow disables download TLS verification"),
            (re.compile(r"(?im)^\s*persist-credentials:\s*true\s*$"), "GHL005", "MEDIUM", "checkout retains repository credentials"),
            (re.compile(r"(?im)^\s*include-hidden-files:\s*true\s*$"), "GHL006", "MEDIUM", "artifact upload includes hidden files"),
            (re.compile(r"(?im)^\s*continue-on-error:\s*true\s*$"), "GHL007", "MEDIUM", "workflow suppresses a step or job failure"),
            (re.compile(r"(?im)^\s*path:\s*[^\n]*(?:\.env|id_rsa|credentials|service-account|\.ssh|wallet|keystore|private[_-]?key)[^\n]*$"), "GHL008", "HIGH", "artifact path may contain credentials or wallet material"),
            (re.compile(r"(?im)^\s*path:\s*[\"']?(?:\.|/|~|\*\*?)[\"']?\s*$"), "GHL009", "MEDIUM", "artifact upload path is overly broad"),
        ):
            for match in pattern.finditer(text):
                out.append(Finding.make(rule, severity, path, line_of(text, match.start()), message, root))
        has_pr = bool(re.search(r"(?m)^\s*(?:pull_request|pull_request_target)\s*:", text))
        if has_pr:
            for match in re.finditer(r"(?im)^\s*(?:actions|checks|contents|deployments|issues|packages|pull-requests|statuses|security-events):\s*write\s*$", text):
                out.append(Finding.make("GHL010", "HIGH", path, line_of(text, match.start()), "pull-request workflow grants a write-capable token scope", root))
    return out


def scan_containers_and_runtime(root: Path) -> list[Finding]:
    out: list[Finding] = []
    for path in files(root, {".yml", ".yaml", ".sh", ".ps1", ".toml", ".ini", ".cfg"}):
        if any(part in RUNTIME_SKIP for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        checks = (
            (re.compile(r"(?mi)^\s*privileged:\s*true\s*$"), "EXPOSE001", "HIGH", "container runs privileged"),
            (re.compile(r"(?mi)^\s*network_mode:\s*host\s*$"), "EXPOSE002", "MEDIUM", "container shares the host network namespace"),
            (re.compile(r"(?mi)^\s*(?:pid|ipc):\s*host\s*$"), "EXPOSE003", "HIGH", "container shares a host namespace"),
            (re.compile(r"(?m)^\s*-\s*/var/run/docker\.sock:"), "EXPOSE004", "CRITICAL", "container mounts the Docker control socket"),
            (re.compile(r"(?mi)^\s*cap_add:\s*$"), "EXPOSE005", "MEDIUM", "container adds Linux capabilities"),
            (re.compile(r"(?m)^\s*-\s*[\"']?(?:0\.0\.0\.0:)?\d+:\d+"), "EXPOSE006", "MEDIUM", "container publishes a port without explicit loopback bind"),
            (INSECURE_DOWNLOAD, "EXPOSE007", "HIGH", "runtime disables download TLS verification"),
            (WORLD_WRITABLE, "EXPOSE008", "HIGH", "runtime creates world-writable paths"),
            (PUBLIC_BIND, "EXPOSE009", "MEDIUM", "runtime configuration binds all network interfaces"),
        )
        for pattern, rule, severity, message in checks:
            for match in pattern.finditer(text):
                out.append(Finding.make(rule, severity, path, line_of(text, match.start()), message, root))
        for match in AUTHORITY_TRUE.finditer(text):
            out.append(Finding.make("BOUNDARY002", "HIGH", path, line_of(text, match.start()), "runtime authority boundary is explicitly enabled", root))
    for path in files(root):
        if not path.name.lower().startswith("dockerfile"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"(?mi)^\s*ADD\s+https?://", text):
            out.append(Finding.make("EXPOSE010", "HIGH", path, line_of(text, match.start()), "Dockerfile downloads a remote resource with ADD", root))
        for match in WORLD_WRITABLE.finditer(text):
            out.append(Finding.make("EXPOSE011", "HIGH", path, line_of(text, match.start()), "container build creates world-writable paths", root))
    return out


def scan_git_hygiene(root: Path) -> list[Finding]:
    out: list[Finding] = []
    path = root / ".gitignore"
    if not path.exists():
        fallback = root / "README.md"
        if not fallback.exists():
            fallback = next(files(root))
        return [Finding.make("GITL001", "MEDIUM", fallback, 1, "repository lacks a .gitignore for secret-bearing files", root)]
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    for token, label in ((".env", "environment files"), ("*.pem", "PEM key files"), ("*.key", "private-key files")):
        if token not in text:
            out.append(Finding.make("GITL002", "MEDIUM", path, 1, f".gitignore does not explicitly exclude {label}", root))
    return out


def allowlist(root: Path) -> set[str]:
    path = root / ".leak-audit-allowlist.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("fingerprints", [])
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise SystemExit(".leak-audit-allowlist.json fingerprints must be strings")
    return set(values)


def render(findings: Sequence[Finding], suppressed: int) -> str:
    counts = {key: 0 for key in ORDER}
    for finding in findings:
        counts[finding.severity] += 1
    lines = [
        "# Leak and Exposure Audit", "", f"- Schema: `{SCHEMA}`",
        f"- Findings: **{len(findings)}**", f"- Suppressed: **{suppressed}**",
        f"- Critical: **{counts['CRITICAL']}**", f"- High: **{counts['HIGH']}**",
        f"- Medium: **{counts['MEDIUM']}**", "",
    ]
    if findings:
        lines += ["| Severity | Rule | Location | Finding | Fingerprint |", "|---|---|---|---|---|"]
        for finding in findings:
            message = finding.message.replace("|", "\\|")
            lines.append(f"| {finding.severity} | `{finding.rule_id}` | `{finding.path}:{finding.line}` | {message} | `{finding.fingerprint}` |")
        lines += ["", "Suspected secret values are always redacted."]
    else:
        lines.append("No findings.")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", default="security-artifacts/leak-audit.json")
    parser.add_argument("--markdown", default="security-artifacts/leak-audit.md")
    parser.add_argument("--fail-on", choices=tuple(ORDER), default="HIGH")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    raw = scan_secrets(root) + scan_python(root) + scan_workflows(root) + scan_containers_and_runtime(root) + scan_git_hygiene(root)
    unique = {finding.fingerprint: finding for finding in raw}
    allowed = allowlist(root)
    active = [finding for fingerprint, finding in unique.items() if fingerprint not in allowed]
    active.sort(key=lambda finding: (-ORDER[finding.severity], finding.path, finding.line, finding.rule_id))
    counts = {key: 0 for key in ORDER}
    for finding in active:
        counts[finding.severity] += 1
    payload = {
        "schema": SCHEMA,
        "root": root.name,
        "fail_on": args.fail_on,
        "counts": counts,
        "suppressed": len(set(unique) & allowed),
        "findings": [asdict(finding) for finding in active],
    }
    json_path = root / args.json
    md_path = root / args.markdown
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = render(active, payload["suppressed"])
    md_path.write_text(report, encoding="utf-8")
    print(report)
    blockers = [finding for finding in active if ORDER[finding.severity] >= ORDER[args.fail_on]]
    if blockers:
        print(f"blocked by {len(blockers)} finding(s) at or above {args.fail_on}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
