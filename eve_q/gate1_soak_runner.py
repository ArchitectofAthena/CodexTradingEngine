from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from eve_q.gate1_hardening import validate_rollback_receipt
from eve_q.gate1_soak_scaffold import (
    CaptureAdapter,
    EnvironmentProvider,
    _default_environment_provider,
    compute_artifact_id,
    run_bounded_soak as _run_bounded_soak,
)


def run_bounded_soak(
    plan: Mapping[str, Any],
    source_review: Mapping[str, Any],
    output_dir: Path,
    *,
    capture_adapter: CaptureAdapter,
    environment_provider: EnvironmentProvider = _default_environment_provider,
) -> dict[str, Any]:
    """Run the scaffold and verify that every rollback has a full payload on disk."""
    summary = _run_bounded_soak(
        plan,
        source_review,
        output_dir,
        capture_adapter=capture_adapter,
        environment_provider=environment_provider,
    )

    rollback_count = int(summary["results"]["rollbacks"])
    rollback_paths = sorted((output_dir / "rollbacks").glob("*.json"))
    rollback_payloads_valid = len(rollback_paths) == rollback_count

    for path in rollback_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if validate_rollback_receipt(payload):
            rollback_payloads_valid = False
            break

    # A run with no failures satisfies this control vacuously. A failed run
    # satisfies it only when every rollback payload is present and valid.
    summary["acceptance"][
        "full_rollback_payload_persisted_on_failure"
    ] = rollback_payloads_valid
    summary["artifact_id"] = compute_artifact_id(summary)

    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
