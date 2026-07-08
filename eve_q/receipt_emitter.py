#!/usr/bin/env python3
"""
Artifact-only receipt emitter for CodexTradingEngine.

This module emits JSON receipts that SpiralBloom OS can ingest.
It does not execute trades, sign transactions, touch wallets, schedule work,
or authorize capital movement.

Agent proposes. Artifact records. Verifier gates. Registry remembers. Human promotes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SPIRALBLOOM_REQUIRED_FIELDS = {
    "source_repo",
    "source_commit",
    "artifact_type",
    "artifact_path",
    "artifact_sha256",
    "mode",
}

ACTION_INTENT_FIELDS = {
    "action",
    "requested_action",
    "intent",
    "operation",
    "execution",
    "next_action",
    "capability",
    "capabilities",
    "automation",
    "scheduler",
    "webhook",
}

DEFAULT_BOUNDARY = [
    "no wallet access",
    "no transaction signing",
    "no capital movement",
    "no autonomous execution",
    "human promotion required",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def resolve_artifact_path(artifact_path: str | Path, root: Path) -> Path:
    path = Path(artifact_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"artifact file not found: {path}")
    return path


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def build_receipt(
    *,
    artifact_path: str | Path,
    source_repo: str,
    source_commit: str,
    source_pr: int | None = None,
    artifact_type: str = "safety_bridge_receipt",
    summary: str = "CodexTradingEngine artifact-only receipt.",
    root: str | Path = ".",
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    artifact_file = resolve_artifact_path(artifact_path, root_path)

    receipt: dict[str, Any] = {
        "source_repo": source_repo,
        "source_commit": source_commit,
        "artifact_type": artifact_type,
        "artifact_path": display_path(artifact_file, root_path),
        "artifact_sha256": sha256_file(artifact_file),
        "mode": "artifact_only",
        "summary": summary,
        "boundary": list(DEFAULT_BOUNDARY),
        "human_promotion_required": True,
        "generated_at": utc_now_iso(),
    }

    if source_pr is not None:
        receipt["source_pr"] = source_pr

    errors = validate_emitted_receipt(receipt)
    if errors:
        raise ValueError("; ".join(errors))

    return receipt


def validate_emitted_receipt(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    missing = sorted(SPIRALBLOOM_REQUIRED_FIELDS - set(receipt))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")

    if receipt.get("mode") != "artifact_only":
        errors.append("mode must be artifact_only")

    if receipt.get("human_promotion_required") is not True:
        errors.append("human_promotion_required must be true")

    artifact_sha = str(receipt.get("artifact_sha256", ""))
    if len(artifact_sha) != 64:
        errors.append("artifact_sha256 must be a 64-character sha256 hex digest")
    else:
        try:
            int(artifact_sha, 16)
        except ValueError:
            errors.append("artifact_sha256 must be hex")

    forbidden_present = sorted(ACTION_INTENT_FIELDS & set(receipt))
    if forbidden_present:
        errors.append(
            "receipt must not contain action/intent fields: " + ", ".join(forbidden_present)
        )

    return errors


def write_receipt(receipt: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit an artifact-only receipt compatible with SpiralBloom OS."
    )
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--source-repo",
        default="ArchitectofAthena/CodexTradingEngine",
    )
    parser.add_argument("--source-commit")
    parser.add_argument("--source-pr", type=int)
    parser.add_argument(
        "--artifact-type",
        default="safety_bridge_receipt",
    )
    parser.add_argument(
        "--summary",
        default="CodexTradingEngine artifact-only receipt.",
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()

    root = args.root.resolve()
    source_commit = args.source_commit or detect_git_commit(root)

    receipt = build_receipt(
        artifact_path=args.artifact,
        source_repo=args.source_repo,
        source_commit=source_commit,
        source_pr=args.source_pr,
        artifact_type=args.artifact_type,
        summary=args.summary,
        root=root,
    )
    write_receipt(receipt, args.out)

    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "artifact_path": receipt["artifact_path"],
                "artifact_sha256": receipt["artifact_sha256"],
                "mode": receipt["mode"],
                "human_promotion_required": receipt["human_promotion_required"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
