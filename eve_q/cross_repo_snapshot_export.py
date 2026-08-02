from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from eve_q.live_read_only_telemetry import (
    ARTIFACT_TYPE as SNAPSHOT_ARTIFACT_TYPE,
    CONTRACT_VERSION as SNAPSHOT_CONTRACT_VERSION,
    PARSER_VERSION,
    canonical_json_bytes,
    replay_snapshot_bundle,
    sha256_hex,
)

ARTIFACT_TYPE = "CrossRepoSnapshotEnvelope"
CONTRACT_VERSION = "cross_repo_snapshot_envelope_v0.1"
EXPECTED_REPOSITORY = "ArchitectofAthena/CodexTradingEngine"
EXPECTED_COMPONENT = "live_read_only_telemetry_v0_1"
EXPECTED_GATE_POSTURE = {
    "gate_0": "ACTIVE",
    "gate_1": "PILOT_ONLY",
    "gate_2_through_6": "LOCKED",
}


class CrossRepoExportError(ValueError):
    """Raised when a snapshot cannot be exported through the reviewed membrane."""


def envelope_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload.pop("envelope_id", None)
    return payload


def compute_envelope_id(document: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(envelope_payload(document)))


def snapshot_document_sha256(document: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(document))


def _require_mapping(document: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise CrossRepoExportError(f"snapshot {key} must be an object")
    return value


def build_cross_repo_envelope(
    snapshot: Mapping[str, Any],
    raw_bytes: bytes,
    normalized_bytes: bytes,
) -> dict[str, Any]:
    findings = replay_findings(snapshot, raw_bytes, normalized_bytes)
    if findings:
        raise CrossRepoExportError("snapshot validation failed: " + "; ".join(findings))

    producer = _require_mapping(snapshot, "producer")
    source = _require_mapping(snapshot, "source")
    retrieval = _require_mapping(snapshot, "retrieval")
    hashes = _require_mapping(snapshot, "hashes")
    normalization = _require_mapping(snapshot, "normalization")

    if producer.get("repository") != EXPECTED_REPOSITORY:
        raise CrossRepoExportError("snapshot producer repository is not reviewed")
    if producer.get("component") != EXPECTED_COMPONENT:
        raise CrossRepoExportError("snapshot producer component is not reviewed")
    if snapshot.get("gate_posture") != EXPECTED_GATE_POSTURE:
        raise CrossRepoExportError("snapshot gate posture is not exportable")

    envelope: dict[str, Any] = {
        "artifact_type": ARTIFACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "producer": {
            "repository": producer["repository"],
            "commit_sha": str(producer["commit_sha"]).lower(),
            "component": producer["component"],
        },
        "snapshot": {
            "artifact_id": snapshot["artifact_id"],
            "contract_version": snapshot["contract_version"],
            "document_sha256": snapshot_document_sha256(snapshot),
            "source_id": source["source_id"],
            "source_kind": source["source_kind"],
            "raw_sha256": hashes["raw_sha256"],
            "normalized_sha256": hashes["normalized_sha256"],
            "parser_version": normalization["parser_version"],
        },
        "timing": {
            "observed_at": retrieval["observed_at"],
            "captured_at": retrieval["retrieved_at"],
            "expires_at": retrieval["expires_at"],
            "freshness_ttl_seconds": retrieval["freshness_ttl_seconds"],
        },
        "gate_posture": dict(snapshot["gate_posture"]),
        "artifact_is_command": False,
        "authority": False,
        "human_review_required": True,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }
    envelope["envelope_id"] = compute_envelope_id(envelope)
    return envelope


def replay_findings(
    snapshot: Mapping[str, Any],
    raw_bytes: bytes,
    normalized_bytes: bytes,
) -> list[str]:
    findings: list[str] = []
    if snapshot.get("artifact_type") != SNAPSHOT_ARTIFACT_TYPE:
        findings.append(f"artifact_type must be {SNAPSHOT_ARTIFACT_TYPE}")
    if snapshot.get("contract_version") != SNAPSHOT_CONTRACT_VERSION:
        findings.append(f"contract_version must be {SNAPSHOT_CONTRACT_VERSION}")
    if snapshot.get("artifact_id") is None:
        findings.append("artifact_id is required")

    hashes = snapshot.get("hashes")
    if not isinstance(hashes, Mapping):
        findings.append("hashes must be an object")
    else:
        if hashes.get("raw_sha256") != sha256_hex(raw_bytes):
            findings.append("raw payload hash mismatch")
        if hashes.get("normalized_sha256") != sha256_hex(normalized_bytes):
            findings.append("normalized payload hash mismatch")

    normalization = snapshot.get("normalization")
    if not isinstance(normalization, Mapping) or normalization.get("parser_version") != PARSER_VERSION:
        findings.append(f"parser_version must be {PARSER_VERSION}")

    for key, expected in {
        "artifact_is_command": False,
        "authority": False,
        "human_promotion_required": True,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_move_capital": False,
    }.items():
        if snapshot.get(key) is not expected:
            findings.append(f"{key} must be {str(expected).lower()}")
    return findings


def export_snapshot_bundle(bundle_dir: Path) -> dict[str, Any]:
    replay_findings_from_bundle = replay_snapshot_bundle(
        bundle_dir,
        require_fresh=False,
    )
    if replay_findings_from_bundle:
        raise CrossRepoExportError(
            "snapshot bundle replay failed: " + "; ".join(replay_findings_from_bundle)
        )
    snapshot = json.loads((bundle_dir / "snapshot.json").read_text(encoding="utf-8"))
    raw_bytes = (bundle_dir / "raw.bin").read_bytes()
    normalized_bytes = (bundle_dir / "normalized.json").read_bytes().rstrip(b"\n")
    return build_cross_repo_envelope(snapshot, raw_bytes, normalized_bytes)


def write_envelope(path: Path, envelope: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a validated Gate 1 snapshot bundle for SpiralBloom intake."
    )
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        envelope = export_snapshot_bundle(args.bundle)
    except (OSError, json.JSONDecodeError, CrossRepoExportError) as exc:
        print(f"Cross-repository snapshot export: HOLD ({exc})")
        return 1
    if args.output:
        print(write_envelope(args.output, envelope))
    else:
        print(json.dumps(envelope, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
