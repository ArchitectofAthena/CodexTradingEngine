from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


CONTRACT_VERSION = "eve_q_cross_repo_v0.1"
SOURCE_COMMIT = "792b002c95916ab1e0d1eef17a1dbf6692359fea"
SCHEMA_BY_TYPE = {
    "ProposalArtifact": "proposal_artifact_v0_1.schema.json",
    "EvidenceBundle": "evidence_bundle_v0_1.schema.json",
    "GateDecision": "gate_decision_v0_1.schema.json",
    "HumanPromotionReceipt": "human_promotion_receipt_v0_1.schema.json",
    "RegistryEntry": "registry_entry_v0_1.schema.json",
    "ExecutionReceipt": "execution_receipt_v0_1.schema.json",
}
HEX40 = "a" * 40
HEX64 = "b" * 64
STAMP = "2026-07-11T18:00:00Z"
EXPIRY = "2026-07-12T18:00:00Z"


@dataclass(frozen=True)
class ValidationFinding:
    code: str
    message: str
    artifact_type: str | None = None
    artifact_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
        }


def canonical_json_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def artifact_sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def load_schema(schema_root: Path, artifact_type: str) -> dict[str, Any]:
    try:
        filename = SCHEMA_BY_TYPE[artifact_type]
    except KeyError as exc:
        raise ValueError(f"unsupported artifact_type: {artifact_type!r}") from exc
    return json.loads((schema_root / filename).read_text(encoding="utf-8"))


def validate_artifact(
    document: dict[str, Any],
    schema_root: Path,
) -> list[ValidationFinding]:
    artifact_type = document.get("artifact_type")
    artifact_id = document.get("artifact_id")
    if artifact_type not in SCHEMA_BY_TYPE:
        return [
            ValidationFinding(
                code="unsupported_artifact_type",
                message=f"unsupported artifact_type: {artifact_type!r}",
                artifact_type=str(artifact_type) if artifact_type is not None else None,
                artifact_id=str(artifact_id) if artifact_id is not None else None,
            )
        ]

    schema = load_schema(schema_root, str(artifact_type))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    findings: list[ValidationFinding] = []
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path)):
        path = ".".join(str(part) for part in error.path) or "$"
        findings.append(
            ValidationFinding(
                code="schema_violation",
                message=f"{path}: {error.message}",
                artifact_type=str(artifact_type),
                artifact_id=str(artifact_id) if artifact_id is not None else None,
            )
        )
    return findings


def _add_unknown_reference(
    findings: list[ValidationFinding],
    artifact: dict[str, Any],
    field: str,
    expected_type: str,
    by_hash: dict[str, dict[str, Any]],
) -> None:
    reference = artifact.get(field)
    target = by_hash.get(reference)
    if target is None:
        findings.append(
            ValidationFinding(
                code="unknown_reference",
                message=f"{field} references unknown artifact hash {reference!r}",
                artifact_type=artifact.get("artifact_type"),
                artifact_id=artifact.get("artifact_id"),
            )
        )
    elif target.get("artifact_type") != expected_type:
        findings.append(
            ValidationFinding(
                code="reference_type_mismatch",
                message=(
                    f"{field} must reference {expected_type}, got "
                    f"{target.get('artifact_type')!r}"
                ),
                artifact_type=artifact.get("artifact_type"),
                artifact_id=artifact.get("artifact_id"),
            )
        )


def validate_chain(
    artifacts: Iterable[dict[str, Any]],
    schema_root: Path,
) -> list[ValidationFinding]:
    documents = list(artifacts)
    findings: list[ValidationFinding] = []

    for document in documents:
        findings.extend(validate_artifact(document, schema_root))

    versions = {document.get("contract_version") for document in documents}
    if versions != {CONTRACT_VERSION}:
        findings.append(
            ValidationFinding(
                code="mixed_contract_versions",
                message=(
                    f"expected only {CONTRACT_VERSION!r}; "
                    f"observed {sorted(map(str, versions))}"
                ),
            )
        )

    by_hash: dict[str, dict[str, Any]] = {}
    for document in documents:
        digest = artifact_sha256(document)
        if digest in by_hash:
            findings.append(
                ValidationFinding(
                    code="duplicate_artifact_content",
                    message=f"duplicate canonical artifact hash {digest}",
                    artifact_type=document.get("artifact_type"),
                    artifact_id=document.get("artifact_id"),
                )
            )
        by_hash[digest] = document

    artifact_ids: set[str] = set()
    for document in documents:
        artifact_id = document.get("artifact_id")
        if isinstance(artifact_id, str):
            if artifact_id in artifact_ids:
                findings.append(
                    ValidationFinding(
                        code="duplicate_artifact_id",
                        message=f"duplicate artifact_id {artifact_id}",
                        artifact_type=document.get("artifact_type"),
                        artifact_id=artifact_id,
                    )
                )
            artifact_ids.add(artifact_id)

    for artifact in documents:
        artifact_type = artifact.get("artifact_type")
        if artifact_type == "EvidenceBundle":
            _add_unknown_reference(
                findings,
                artifact,
                "proposal_artifact_sha256",
                "ProposalArtifact",
                by_hash,
            )
        elif artifact_type == "GateDecision":
            _add_unknown_reference(
                findings,
                artifact,
                "proposal_artifact_sha256",
                "ProposalArtifact",
                by_hash,
            )
            _add_unknown_reference(
                findings,
                artifact,
                "evidence_bundle_sha256",
                "EvidenceBundle",
                by_hash,
            )
            evidence_doc = by_hash.get(artifact.get("evidence_bundle_sha256"))
            if evidence_doc is not None:
                expected_state = evidence_doc.get("evidence_state")
                if artifact.get("evidence_state") != expected_state:
                    findings.append(
                        ValidationFinding(
                            code="evidence_state_mismatch",
                            message="GateDecision evidence_state does not match EvidenceBundle",
                            artifact_type=artifact_type,
                            artifact_id=artifact.get("artifact_id"),
                        )
                    )
        elif artifact_type == "HumanPromotionReceipt":
            _add_unknown_reference(
                findings,
                artifact,
                "promoted_artifact_sha256",
                "ProposalArtifact",
                by_hash,
            )
            _add_unknown_reference(
                findings,
                artifact,
                "gate_decision_sha256",
                "GateDecision",
                by_hash,
            )
            gate_doc = by_hash.get(artifact.get("gate_decision_sha256"))
            if gate_doc is not None and gate_doc.get("decision") != "COMMIT":
                findings.append(
                    ValidationFinding(
                        code="promotion_without_commit",
                        message="HumanPromotionReceipt may only promote COMMIT",
                        artifact_type=artifact_type,
                        artifact_id=artifact.get("artifact_id"),
                    )
                )
        elif artifact_type == "RegistryEntry":
            subject_hash = artifact.get("subject_artifact_sha256")
            if subject_hash not in by_hash:
                findings.append(
                    ValidationFinding(
                        code="unknown_registry_subject",
                        message=f"RegistryEntry subject hash is unknown: {subject_hash!r}",
                        artifact_type=artifact_type,
                        artifact_id=artifact.get("artifact_id"),
                    )
                )
        elif artifact_type == "ExecutionReceipt":
            _add_unknown_reference(
                findings,
                artifact,
                "proposal_artifact_sha256",
                "ProposalArtifact",
                by_hash,
            )
            _add_unknown_reference(
                findings,
                artifact,
                "gate_decision_sha256",
                "GateDecision",
                by_hash,
            )
            promotion_hash = artifact.get("human_promotion_receipt_sha256")
            if artifact.get("capital_movement_occurred") is True:
                promotion_doc = by_hash.get(promotion_hash)
                if promotion_doc is None:
                    findings.append(
                        ValidationFinding(
                            code="capital_movement_without_known_promotion",
                            message=(
                                "reported capital movement requires a known "
                                "HumanPromotionReceipt"
                            ),
                            artifact_type=artifact_type,
                            artifact_id=artifact.get("artifact_id"),
                        )
                    )
                elif promotion_doc.get("artifact_type") != "HumanPromotionReceipt":
                    findings.append(
                        ValidationFinding(
                            code="promotion_reference_type_mismatch",
                            message="promotion hash references wrong artifact type",
                            artifact_type=artifact_type,
                            artifact_id=artifact.get("artifact_id"),
                        )
                    )
            elif promotion_hash is not None:
                promotion_doc = by_hash.get(promotion_hash)
                if (
                    promotion_doc is None
                    or promotion_doc.get("artifact_type") != "HumanPromotionReceipt"
                ):
                    findings.append(
                        ValidationFinding(
                            code="unknown_optional_promotion",
                            message="unknown optional promotion receipt",
                            artifact_type=artifact_type,
                            artifact_id=artifact.get("artifact_id"),
                        )
                    )

    return findings


def evidence(proposal_hash: str) -> dict[str, Any]:
    return {
        "artifact_type": "EvidenceBundle",
        "contract_version": CONTRACT_VERSION,
        "artifact_id": "4" * 64,
        "created_at": STAMP,
        "producer": {
            "repository": "ArchitectofAthena/spiralbloom-os",
            "component": "evidence_grounding_v0_1",
            "commit_sha": HEX40,
        },
        "proposal_artifact_sha256": proposal_hash,
        "sources": [
            {
                "source_id": "independent-sim-001",
                "source_uri": "artifact://simulation/independent-sim-001",
                "source_kind": "simulation_receipt",
                "independence_group": "independent-verifier-a",
                "content_sha256": "5" * 64,
                "position": "support",
                "causal_support": 0.8,
            },
            {
                "source_id": "counterevidence-001",
                "source_uri": "artifact://counterevidence/001",
                "source_kind": "counterevidence",
                "independence_group": "independent-verifier-b",
                "content_sha256": "6" * 64,
                "position": "mixed",
                "causal_support": 0.5,
            },
        ],
        "contradictions": [
            {
                "contradiction_id": "contradiction-001",
                "status": "reviewed",
                "summary": "slippage sensitivity increases under lower liquidity",
                "source_sha256": "6" * 64,
            }
        ],
        "evidence_grounding": {
            "source_independence": 0.82,
            "provenance_diversity": 0.75,
            "contradiction_coverage": 0.72,
            "causal_support": 0.68,
            "redundancy_penalty": 0.1,
            "coalition_coherence": 0.78,
            "coherence_conflict": 0.1,
        },
        "evidence_state": "GROUNDED",
        "agreement_is_not_truth": True,
        "authority": False,
        "human_promotion_required": True,
    }


def gate(proposal_hash: str, evidence_hash: str) -> dict[str, Any]:
    return {
        "artifact_type": "GateDecision",
        "contract_version": CONTRACT_VERSION,
        "artifact_id": "7" * 64,
        "created_at": STAMP,
        "producer": {
            "repository": "ArchitectofAthena/spiralbloom-os",
            "component": "paladin_gate_v0_1",
            "commit_sha": HEX40,
        },
        "proposal_artifact_sha256": proposal_hash,
        "evidence_bundle_sha256": evidence_hash,
        "decision": "COMMIT",
        "evidence_state": "GROUNDED",
        "contradiction_status": "reviewed",
        "reasons": ["evidence grounding exceeds the preregistered minimum"],
        "scope_authority": {
            "may_inform": True,
            "may_execute": False,
            "allowed_scope": ["human_review", "registry_update"],
            "expires_at": EXPIRY,
        },
        "execution_authority": False,
        "capital_movement_authorized": False,
        "authority": False,
        "human_promotion_required": True,
    }


def promotion(proposal_hash: str, gate_hash: str) -> dict[str, Any]:
    return {
        "artifact_type": "HumanPromotionReceipt",
        "contract_version": CONTRACT_VERSION,
        "artifact_id": "8" * 64,
        "created_at": STAMP,
        "reviewer": {
            "reviewer_id": "architect",
            "reviewer_type": "human",
            "review_method": "interactive_review",
        },
        "promoted_artifact_sha256": proposal_hash,
        "gate_decision_sha256": gate_hash,
        "approval_scope": ["further_simulation", "registry_promotion"],
        "promotion_status": "approved",
        "approved_at": STAMP,
        "expires_at": EXPIRY,
        "reversible_when_required": True,
        "records_human_authority": True,
        "artifact_authority": False,
        "may_execute": False,
        "attestations": {
            "reviewed_exact_hashes": True,
            "understands_scope": True,
            "understands_expiry": True,
            "no_self_promotion": True,
            "receipt_does_not_execute": True,
        },
    }


def registry(subject_hash: str, prior_hashes: list[str]) -> dict[str, Any]:
    return {
        "artifact_type": "RegistryEntry",
        "contract_version": CONTRACT_VERSION,
        "artifact_id": "9" * 64,
        "created_at": STAMP,
        "producer": {
            "repository": "ArchitectofAthena/spiralbloom-os",
            "component": "artifact_registry_v0_1",
            "commit_sha": HEX40,
        },
        "subject_artifact_sha256": subject_hash,
        "prior_artifact_hashes": prior_hashes,
        "state_transition": {
            "from": "COMMITTED",
            "to": "PROMOTED",
            "reason": "explicit scoped human promotion recorded",
        },
        "alternatives_preserved": [],
        "contradictions_preserved": [
            {
                "contradiction_id": "contradiction-001",
                "status": "reviewed",
                "summary": "slippage sensitivity remains in the audit lineage",
            }
        ],
        "immutable": True,
        "execution_inferred": False,
        "authority": False,
    }


def execution(
    proposal_hash: str,
    gate_hash: str,
    promotion_hash: str,
) -> dict[str, Any]:
    return {
        "artifact_type": "ExecutionReceipt",
        "contract_version": CONTRACT_VERSION,
        "artifact_id": "a" * 64,
        "created_at": STAMP,
        "executor": {
            "executor_id": "simulation-harness-v0-1",
            "executor_type": "simulation_harness",
        },
        "execution_mode": "simulation",
        "proposal_artifact_sha256": proposal_hash,
        "gate_decision_sha256": gate_hash,
        "human_promotion_receipt_sha256": promotion_hash,
        "observed": True,
        "inferred": False,
        "proposal_approval_was_not_treated_as_execution": True,
        "capital_movement_occurred": False,
        "result": {
            "status": "succeeded",
            "observed_at": STAMP,
            "summary": "bounded simulation completed",
            "output_hashes": [HEX64],
            "external_reference": None,
        },
        "authority": False,
    }
