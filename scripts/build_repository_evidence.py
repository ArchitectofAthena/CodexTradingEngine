#!/usr/bin/env python3
"""Build a bounded, redacted repository evidence bundle.

This script is deliberately standard-library only. Repository content is treated as
untrusted data. It never imports or executes code from the inspected repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

SCHEMA = "repository.evidence_bundle.v0.1"
PRODUCER = "build_repository_evidence.py/v0.1"
MAX_DIFF_BYTES = 240_000
MAX_HASH_FILE_BYTES = 10 * 1024 * 1024

AUTHORITY = {
    "artifact_is_command": False,
    "human_promotion_required": True,
    "may_merge": False,
    "may_write_repository": False,
    "may_deploy": False,
    "may_execute": False,
    "may_sign": False,
    "may_broadcast": False,
    "may_move_capital": False,
}

ALLOW_PREFIXES = (
    ".github/workflows/",
    "config/",
    "deploy/",
    "docs/",
    "eve_q/",
    "examples/",
    "orchestration/",
    "packages/",
    "prompts/",
    "registry/",
    "schemas/",
    "scripts/",
    "spiralbloom_os/",
    "tests/",
    "tools/",
)
ALLOW_BASENAMES = {
    "Dockerfile",
    "Dockerfile.bloomhud",
    "Dockerfile.gate1",
    "SECURITY.md",
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.lock",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "Cargo.toml",
    "Cargo.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "compose.yml",
    "compose.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".gitleaks.toml",
    ".trivyignore.yaml",
    ".security-audit-allowlist.json",
}

DENY_PARTS = {
    ".env",
    ".git",
    ".idea",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "dist",
    "node_modules",
    "runtime",
    "secrets",
    "vendor",
}
DENY_SUFFIXES = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".bmp",
    ".crt",
    ".db",
    ".der",
    ".dll",
    ".dmg",
    ".doc",
    ".docx",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".iso",
    ".jar",
    ".jpeg",
    ".jpg",
    ".key",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".p12",
    ".pdf",
    ".pem",
    ".png",
    ".pyc",
    ".sqlite",
    ".tar",
    ".tgz",
    ".wav",
    ".webp",
    ".whl",
    ".zip",
}

SECRET_PATTERNS = [
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|private[_-]?key|secret)\b\s*[:=]\s*[^\s,;]{6,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def run_git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed with {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def normalize_path(raw: str) -> str:
    value = raw.replace("\\", "/").lstrip("./")
    return str(PurePosixPath(value))


def path_allowed(path: str) -> bool:
    normalized = normalize_path(path)
    parts = set(PurePosixPath(normalized).parts)
    if parts & DENY_PARTS:
        return False
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix in DENY_SUFFIXES:
        return False
    basename = PurePosixPath(normalized).name
    return basename in ALLOW_BASENAMES or normalized.startswith(ALLOW_PREFIXES)


def changed_files(repo: Path, base_ref: str, head_ref: str) -> list[dict[str, str]]:
    output = run_git(repo, "diff", "--name-status", "--find-renames", f"{base_ref}...{head_ref}")
    rows: list[dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        status = fields[0]
        path = fields[-1]
        rows.append({"status": status, "path": normalize_path(path)})
    return rows[:1000]


def redact_line(line: str) -> tuple[str, bool]:
    if any(pattern.search(line) for pattern in SECRET_PATTERNS):
        prefix = ""
        if line.startswith(("+", "-", " ")):
            prefix = line[0]
        return f"{prefix}[REDACTED_SECRET_SHAPE]", True
    return line, False


def bounded_diff(
    repo: Path,
    base_ref: str,
    head_ref: str,
    allowed_paths: Iterable[str],
) -> tuple[str, int, bool]:
    paths = [path for path in allowed_paths if path_allowed(path)]
    if not paths:
        return "", 0, False

    output = run_git(
        repo,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--find-renames",
        "--unified=3",
        f"{base_ref}...{head_ref}",
        "--",
        *paths,
    )

    redacted_count = 0
    redacted_lines: list[str] = []
    for line in output.splitlines():
        safe_line, redacted = redact_line(line)
        redacted_count += int(redacted)
        redacted_lines.append(safe_line)

    raw = ("\n".join(redacted_lines) + "\n").encode("utf-8")
    truncated = len(raw) > MAX_DIFF_BYTES
    if truncated:
        raw = raw[:MAX_DIFF_BYTES]
        while raw and (raw[-1] & 0b1100_0000) == 0b1000_0000:
            raw = raw[:-1]
        raw += b"\n[DIFF_TRUNCATED_AT_SIZE_CEILING]\n"
    return raw.decode("utf-8", errors="replace"), redacted_count, truncated


def manifest_hashes(repo: Path) -> tuple[list[dict[str, object]], int]:
    entries: list[dict[str, object]] = []
    excluded = 0
    output = run_git(repo, "ls-files")
    for raw_path in output.splitlines():
        path = normalize_path(raw_path)
        if not path_allowed(path):
            excluded += 1
            continue
        full = repo / path
        try:
            size = full.stat().st_size
        except OSError:
            continue
        if size > MAX_HASH_FILE_BYTES or not full.is_file():
            excluded += 1
            continue
        digest = hashlib.sha256(full.read_bytes()).hexdigest()
        entries.append({"path": path, "sha256": digest, "size_bytes": size})
        if len(entries) >= 500:
            break
    entries.sort(key=lambda item: str(item["path"]))
    return entries, excluded


def canonical_sha256(value: dict[str, object]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_bundle(repo: Path, repository: str, base_ref: str, head_ref: str) -> dict[str, object]:
    repo = repo.resolve()
    if not (repo / ".git").exists():
        raise ValueError(f"not a Git repository: {repo}")

    head_sha = run_git(repo, "rev-parse", head_ref).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise ValueError("head_ref did not resolve to a full commit SHA")

    changes = changed_files(repo, base_ref, head_ref)
    allowed_changed = [entry["path"] for entry in changes if path_allowed(entry["path"])]
    diff, secret_lines, truncated = bounded_diff(repo, base_ref, head_ref, allowed_changed)
    hashes, excluded_paths = manifest_hashes(repo)

    bundle: dict[str, object] = {
        "schema": SCHEMA,
        "producer": PRODUCER,
        "repository": repository,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "head_sha": head_sha,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "authority": AUTHORITY.copy(),
        "changed_files": changes,
        "manifest_hashes": hashes,
        "redaction": {
            "secret_shaped_lines": secret_lines,
            "excluded_paths": excluded_paths,
            "truncated": truncated,
        },
        "diff": diff,
    }
    bundle["bundle_sha256"] = canonical_sha256(bundle)
    return bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        bundle = build_bundle(
            repo=args.repo,
            repository=args.repository,
            base_ref=args.base_ref,
            head_ref=args.head_ref,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"evidence build failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {args.output} ({bundle['bundle_sha256']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
