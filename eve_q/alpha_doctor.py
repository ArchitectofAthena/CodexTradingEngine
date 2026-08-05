"""Gate 1A alpha environment doctor and public-testnet source registry validator.

The doctor explains the local checkout before any network observation. It has no
capture, proposal, signing, transaction, execution, wallet, or capital authority.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from eve_q.gate1_readonly_runtime import dangerous_secret_names


REGISTRY_ID = "codex.gate1a.testnet-source-registry.v0.1"
DOCTOR_VERSION = "codex-alpha-doctor-v0.1"
GATE_POSTURE = {
    "gate_0": "ACTIVE",
    "gate_1a": "ACTIVE_FOR_APPROVED_ALPHA_RUNS",
    "gate_1b": "LOCKED",
    "gate_2": "LOCKED",
    "gate_3": "LOCKED",
    "gate_4_through_6": "LOCKED",
}
AUTHORITY_BOUNDARY = {
    "authority": False,
    "artifact_is_command": False,
    "network_capture_allowed": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_move_capital": False,
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class AlphaDoctorError(RuntimeError):
    """Raised when the doctor cannot safely evaluate its own inputs."""


@dataclass(frozen=True, slots=True)
class RegistrySummary:
    valid: bool
    errors: tuple[str, ...]
    eligible_source_ids: tuple[str, ...]
    hold_source_ids: tuple[str, ...]
    rejected_source_ids: tuple[str, ...]
    registry_sha256: str


@dataclass(frozen=True, slots=True)
class DoctorFacts:
    repo_root: str
    commit_sha: str | None
    git_error: str | None
    dirty_paths: tuple[str, ...]
    python_version: str
    package_origin: str
    kill_switch_active: bool
    dangerous_secret_names: tuple[str, ...]
    rust_verifier_path: str | None
    rust_verifier_expected_sha256: str | None
    rust_verifier_actual_sha256: str | None
    rust_verifier_state: str
    registry: RegistrySummary


@dataclass(frozen=True, slots=True)
class DoctorResult:
    status: str
    holds: tuple[str, ...]
    warnings: tuple[str, ...]
    facts: DoctorFacts
    authority: Mapping[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return {
            "doctor_version": DOCTOR_VERSION,
            "status": self.status,
            "holds": list(self.holds),
            "warnings": list(self.warnings),
            "repository": {
                "root": self.facts.repo_root,
                "commit_sha": self.facts.commit_sha,
                "git_error": self.facts.git_error,
                "dirty": bool(self.facts.dirty_paths),
                "dirty_paths": list(self.facts.dirty_paths),
            },
            "python": {
                "version": self.facts.python_version,
                "package_origin": self.facts.package_origin,
            },
            "gate_posture": dict(GATE_POSTURE),
            "kill_switch_active": self.facts.kill_switch_active,
            "dangerous_secret_names": list(self.facts.dangerous_secret_names),
            "rust_verifier": {
                "path": self.facts.rust_verifier_path,
                "expected_sha256": self.facts.rust_verifier_expected_sha256,
                "actual_sha256": self.facts.rust_verifier_actual_sha256,
                "state": self.facts.rust_verifier_state,
            },
            "source_registry": {
                "valid": self.facts.registry.valid,
                "errors": list(self.facts.registry.errors),
                "eligible_source_ids": list(self.facts.registry.eligible_source_ids),
                "hold_source_ids": list(self.facts.registry.hold_source_ids),
                "rejected_source_ids": list(self.facts.registry.rejected_source_ids),
                "eligible_source_count": len(self.facts.registry.eligible_source_ids),
                "registry_sha256": self.facts.registry.registry_sha256,
            },
            "authority": dict(self.authority),
        }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _schema_error(error: Any) -> str:
    path = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{path}: {error.message}"


def _semantic_registry_errors(document: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    source_ids: set[str] = set()
    for index, source in enumerate(document.get("sources", [])):
        prefix = f"sources.{index}"
        source_id = str(source.get("source_id", ""))
        if source_id in source_ids:
            errors.append(f"{prefix}.source_id: duplicate source ID {source_id}")
        source_ids.add(source_id)

        raw_url = str(source.get("url", ""))
        parsed = urllib.parse.urlparse(raw_url)
        host = str(source.get("host", "")).strip().rstrip(".").lower()
        parsed_host = (parsed.hostname or "").strip().rstrip(".").lower()
        if parsed.scheme.lower() != "https":
            errors.append(f"{prefix}.url: only HTTPS is permitted")
        if parsed.username or parsed.password:
            errors.append(f"{prefix}.url: embedded credentials are forbidden")
        try:
            port = parsed.port
        except ValueError:
            port = -1
        if port not in {None, 443}:
            errors.append(f"{prefix}.url: only the default HTTPS port is permitted")
        if not host or parsed_host != host:
            errors.append(f"{prefix}.host: exact host must match the URL hostname")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            errors.append(f"{prefix}.host: loopback hosts are forbidden")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            errors.append(f"{prefix}.host: IP-literal hosts are forbidden")

        mainnet_tokens = (
            source_id,
            str(source.get("network_name", "")),
            raw_url,
        )
        if any("mainnet" in token.lower() for token in mainnet_tokens):
            errors.append(f"{prefix}: mainnet identifiers are forbidden in Gate 1A")

        methods = {str(item).upper() for item in source.get("allowed_methods", [])}
        if not methods or not methods.issubset({"GET", "HEAD"}):
            errors.append(f"{prefix}.allowed_methods: only GET and HEAD are permitted")

        if source.get("disposition") == "ELIGIBLE":
            terms = source.get("terms_review", {})
            if terms.get("status") != "reviewed":
                errors.append(f"{prefix}: ELIGIBLE source terms must be reviewed")
            if not source.get("review_evidence"):
                errors.append(f"{prefix}: ELIGIBLE source requires review evidence")
            if not source.get("reviewed_at"):
                errors.append(f"{prefix}: ELIGIBLE source requires a review timestamp")
    return errors


def validate_registry(
    document: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> RegistrySummary:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    schema_errors = sorted(
        validator.iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    errors = [_schema_error(error) for error in schema_errors]
    errors.extend(_semantic_registry_errors(document))

    sources = document.get("sources", []) if isinstance(document, Mapping) else []
    eligible = sorted(
        str(source["source_id"])
        for source in sources
        if source.get("disposition") == "ELIGIBLE"
    )
    hold = sorted(
        str(source["source_id"])
        for source in sources
        if source.get("disposition") == "HOLD"
    )
    rejected = sorted(
        str(source["source_id"])
        for source in sources
        if source.get("disposition") == "REJECT"
    )
    return RegistrySummary(
        valid=not errors,
        errors=tuple(errors),
        eligible_source_ids=tuple(eligible),
        hold_source_ids=tuple(hold),
        rejected_source_ids=tuple(rejected),
        registry_sha256=sha256_hex(canonical_json_bytes(document)),
    )


def load_registry(registry_path: Path, schema_path: Path) -> RegistrySummary:
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return RegistrySummary(
            valid=False,
            errors=(f"registry_load_error: {type(exc).__name__}: {exc}",),
            eligible_source_ids=(),
            hold_source_ids=(),
            rejected_source_ids=(),
            registry_sha256="",
        )
    if not isinstance(registry, Mapping) or not isinstance(schema, Mapping):
        return RegistrySummary(
            valid=False,
            errors=("registry and schema roots must be JSON objects",),
            eligible_source_ids=(),
            hold_source_ids=(),
            rejected_source_ids=(),
            registry_sha256="",
        )
    return validate_registry(registry, schema)


def _run_git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def _collect_git(repo_root: Path) -> tuple[str | None, str | None, tuple[str, ...]]:
    try:
        commit = _run_git(repo_root, "rev-parse", "HEAD").lower()
        status = _run_git(repo_root, "status", "--porcelain=v1")
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}", ()
    dirty_paths = tuple(line for line in status.splitlines() if line.strip())
    return commit, None, dirty_paths


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate_rust_verifier(
    repo_root: Path,
    path_value: str | None,
    expected_sha256: str | None,
) -> tuple[str, str | None, str | None, str | None]:
    if not path_value:
        return "NOT_CONFIGURED", None, None, None
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        return "HOLD_MISSING", str(path), expected_sha256, None
    try:
        actual = _file_sha256(path)
    except OSError:
        return "HOLD_UNREADABLE", str(path), expected_sha256, None
    if _is_within(path, repo_root):
        return "CHECKOUT_LOCAL", str(path), expected_sha256, actual
    normalized_expected = (expected_sha256 or "").lower()
    if _SHA256_RE.fullmatch(normalized_expected) and actual == normalized_expected:
        return "REVIEWED_DIGEST", str(path), normalized_expected, actual
    return "HOLD_UNEXPLAINED", str(path), expected_sha256, actual


def collect_facts(
    *,
    repo_root: Path,
    registry_path: Path,
    schema_path: Path,
    environment: Mapping[str, str] | None = None,
    package_origin: Path | None = None,
) -> DoctorFacts:
    env = dict(environment or os.environ)
    root = repo_root.expanduser().resolve()
    commit, git_error, dirty_paths = _collect_git(root)
    if package_origin is None:
        import eve_q

        package_origin = Path(str(eve_q.__file__)).resolve()
    rust_state, rust_path, expected_digest, actual_digest = evaluate_rust_verifier(
        root,
        env.get("EVE_Q_RUST_VERIFIER_PATH"),
        env.get("EVE_Q_RUST_VERIFIER_SHA256"),
    )
    return DoctorFacts(
        repo_root=str(root),
        commit_sha=commit,
        git_error=git_error,
        dirty_paths=dirty_paths,
        python_version=".".join(str(item) for item in sys.version_info[:3]),
        package_origin=str(package_origin.resolve()),
        kill_switch_active=env.get("EVE_Q_GATE1_KILL_SWITCH") == "1",
        dangerous_secret_names=tuple(dangerous_secret_names(env)),
        rust_verifier_path=rust_path,
        rust_verifier_expected_sha256=expected_digest,
        rust_verifier_actual_sha256=actual_digest,
        rust_verifier_state=rust_state,
        registry=load_registry(registry_path, schema_path),
    )


def evaluate_facts(
    facts: DoctorFacts,
    *,
    acknowledge_dirty: bool = False,
) -> DoctorResult:
    holds: list[str] = []
    warnings: list[str] = []
    root = Path(facts.repo_root).resolve()
    package_origin = Path(facts.package_origin).resolve()

    if facts.git_error:
        holds.append("repository state cannot be explained: " + facts.git_error)
    if not facts.commit_sha or not _COMMIT_RE.fullmatch(facts.commit_sha):
        holds.append("repository commit is missing or invalid")
    if not _is_within(package_origin, root):
        holds.append("installed eve_q package resolves outside the checked-out repository")
    if facts.dirty_paths:
        if acknowledge_dirty:
            warnings.append("working tree is dirty and was explicitly acknowledged for local research")
        else:
            holds.append("working tree contains unexplained changes")
    if facts.kill_switch_active:
        holds.append("Gate 1 kill switch is active")
    if facts.dangerous_secret_names:
        holds.append(
            "write-capable secret names are present: "
            + ", ".join(facts.dangerous_secret_names)
        )
    if facts.rust_verifier_state.startswith("HOLD_"):
        holds.append("Rust verifier origin is unexplained: " + facts.rust_verifier_state)
    elif facts.rust_verifier_state == "NOT_CONFIGURED":
        warnings.append("no Rust verifier is configured; Rust verification is unavailable")
    if not facts.registry.valid:
        holds.append("testnet source registry is invalid")
    elif not facts.registry.eligible_source_ids:
        warnings.append("no public testnet source has earned ELIGIBLE status")

    status = "HOLD" if holds else "READY_WITH_WARNINGS" if warnings else "READY"
    return DoctorResult(
        status=status,
        holds=tuple(holds),
        warnings=tuple(warnings),
        facts=facts,
        authority=dict(AUTHORITY_BOUNDARY),
    )


def render_text(result: DoctorResult) -> str:
    registry = result.facts.registry
    lines = [
        "CODEX GATE 1A ALPHA DOCTOR v0.1",
        f"STATUS: {result.status}",
        f"COMMIT: {result.facts.commit_sha or 'UNKNOWN'}",
        f"DIRTY TREE: {'yes' if result.facts.dirty_paths else 'no'}",
        f"PYTHON: {result.facts.python_version}",
        f"PACKAGE ORIGIN: {result.facts.package_origin}",
        f"KILL SWITCH: {'active' if result.facts.kill_switch_active else 'inactive'}",
        f"RUST VERIFIER: {result.facts.rust_verifier_state}",
        f"REGISTRY: {'valid' if registry.valid else 'invalid'}",
        f"ELIGIBLE TESTNET SOURCES: {len(registry.eligible_source_ids)}",
        "GATE 2: LOCKED",
        "EXECUTION: LOCKED",
        "CAPITAL: LOCKED",
    ]
    if result.holds:
        lines.append("HOLDS:")
        lines.extend(f"- {item}" for item in result.holds)
    if result.warnings:
        lines.append("WARNINGS:")
        lines.extend(f"- {item}" for item in result.warnings)
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Explain the Gate 1A alpha environment before network observation."
    )
    parser.add_argument("--repo-root", type=Path, default=default_root)
    parser.add_argument(
        "--registry",
        type=Path,
        default=default_root / "registry" / "alpha_testnet_sources_v0_1.json",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=default_root / "schemas" / "alpha_testnet_source_registry_v0_1.schema.json",
    )
    parser.add_argument(
        "--acknowledge-dirty",
        action="store_true",
        help="Treat a dirty working tree as a warning for local research only.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--output", type=Path, help="Write the result to this file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    facts = collect_facts(
        repo_root=args.repo_root,
        registry_path=args.registry,
        schema_path=args.schema,
    )
    result = evaluate_facts(facts, acknowledge_dirty=args.acknowledge_dirty)
    rendered = (
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n"
        if args.json
        else render_text(result)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 2 if result.status == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
