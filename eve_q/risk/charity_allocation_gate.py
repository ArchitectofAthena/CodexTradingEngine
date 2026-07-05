from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass(slots=True)
class CharityGateResult:
    allowed_to_record_balance: bool
    allowed_to_release_funds: bool
    requires_human_review: bool
    block_reasons: List[str]
    review_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_charity_gate(
    proposal: Dict[str, Any],
    *,
    human_reviewed: bool = False,
    receipt_path_available: bool = False,
) -> CharityGateResult:
    block_reasons: List[str] = []
    review_reasons: List[str] = []

    provenance = proposal.get("provenance") or proposal.get("inputs", {}).get("provenance") or []
    confidence = float(
        proposal.get("confidence_score", proposal.get("inputs", {}).get("confidence_score", 0.0))
    )
    reliability = float(
        proposal.get(
            "telemetry_source_reliability",
            proposal.get("inputs", {}).get("telemetry_source_reliability", 0.0),
        )
    )

    if not provenance:
        block_reasons.append("missing_provenance")
    if not human_reviewed:
        block_reasons.append("human_review_missing")
    if not receipt_path_available:
        review_reasons.append("receipt_path_not_confirmed")
    if confidence < 0.55:
        review_reasons.append("low_confidence")
    if reliability < 0.50:
        review_reasons.append("low_source_reliability")
    if proposal.get("requires_human_review"):
        review_reasons.append("policy_requested_review")

    return CharityGateResult(
        allowed_to_record_balance=bool(provenance),
        allowed_to_release_funds=len(block_reasons) == 0 and receipt_path_available,
        requires_human_review=True,
        block_reasons=block_reasons,
        review_reasons=sorted(set(review_reasons)),
    )
