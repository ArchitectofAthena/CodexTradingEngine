from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass(slots=True)
class GeodesicInput:
    charity_id: str
    impact_score: float
    need_score: float
    urgency_score: float = 0.0
    neglect_factor: float = 0.0
    funding_gap_score: float = 0.0
    absorptive_capacity_score: float = 0.0
    confidence_score: float = 0.0
    telemetry_source_reliability: float = 0.0
    provenance: List[str] | None = None


@dataclass(slots=True)
class GeodesicDecision:
    charity_id: str
    allocation_priority: float
    recommended_weight: float
    requires_human_review: bool
    hold_transfer: bool
    reason_codes: List[str]
    risk_flags: List[str]
    inputs: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def score_allocation(signal: GeodesicInput) -> GeodesicDecision:
    provenance = signal.provenance or []
    impact = clamp01(signal.impact_score)
    need = clamp01(signal.need_score)
    urgency = clamp01(signal.urgency_score)
    neglect = clamp01(signal.neglect_factor)
    funding_gap = clamp01(signal.funding_gap_score)
    absorb = clamp01(signal.absorptive_capacity_score)
    confidence = clamp01(signal.confidence_score)
    reliability = clamp01(signal.telemetry_source_reliability)

    raw_priority = (
        0.35 * impact
        + 0.25 * need
        + 0.15 * urgency
        + 0.10 * neglect
        + 0.10 * funding_gap
        + 0.05 * absorb
    )
    allocation_priority = clamp01(raw_priority * confidence)

    reason_codes: List[str] = []
    risk_flags: List[str] = []
    requires_review = False

    if not provenance:
        risk_flags.append("missing_provenance")
        reason_codes.append("hold_without_provenance")
        requires_review = True
    if confidence < 0.55:
        risk_flags.append("low_confidence")
        requires_review = True
    if reliability < 0.50:
        risk_flags.append("low_source_reliability")
        requires_review = True
    if need >= 0.80 and impact < 0.35:
        reason_codes.append("urgent_need_low_impact_review")
        requires_review = True
    if absorb < 0.25 and allocation_priority > 0.0:
        risk_flags.append("limited_absorptive_capacity")
        requires_review = True
    if not reason_codes:
        reason_codes.append("balanced_need_impact_signal")

    return GeodesicDecision(
        charity_id=signal.charity_id,
        allocation_priority=allocation_priority,
        recommended_weight=allocation_priority,
        requires_human_review=requires_review,
        hold_transfer=True,
        reason_codes=reason_codes,
        risk_flags=risk_flags,
        inputs={
            "impact_score": impact,
            "need_score": need,
            "urgency_score": urgency,
            "neglect_factor": neglect,
            "funding_gap_score": funding_gap,
            "absorptive_capacity_score": absorb,
            "confidence_score": confidence,
            "telemetry_source_reliability": reliability,
            "provenance": provenance,
        },
    )
