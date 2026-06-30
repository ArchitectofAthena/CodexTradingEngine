from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(slots=True)
class NeedSignal:
    cause_id: str
    region: str | None = None
    funding_gap_score: float = 0.0
    urgency_score: float = 0.0
    population_affected_score: float = 0.0
    neglect_factor: float = 0.0
    time_sensitivity_score: float = 0.0
    preventive_value_score: float = 0.0
    regional_vulnerability_score: float = 0.0
    absorptive_capacity_score: float = 0.0
    telemetry_source_reliability: float = 0.0
    provenance: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score_need(signal: NeedSignal) -> Dict[str, Any]:
    funding_gap = clamp01(signal.funding_gap_score)
    urgency = clamp01(signal.urgency_score)
    affected = clamp01(signal.population_affected_score)
    neglect = clamp01(signal.neglect_factor)
    time_sensitivity = clamp01(signal.time_sensitivity_score)
    preventive = clamp01(signal.preventive_value_score)
    vulnerability = clamp01(signal.regional_vulnerability_score)
    absorb = clamp01(signal.absorptive_capacity_score)
    reliability = clamp01(signal.telemetry_source_reliability)
    provenance = signal.provenance or []

    raw_need = (
        0.20 * funding_gap
        + 0.20 * urgency
        + 0.15 * affected
        + 0.15 * neglect
        + 0.10 * time_sensitivity
        + 0.10 * preventive
        + 0.10 * vulnerability
    )
    confidence = clamp01((0.70 * reliability) + (0.30 if provenance else 0.0))

    return {
        "cause_id": signal.cause_id,
        "region": signal.region,
        "need_score": clamp01(raw_need),
        "funding_gap_score": funding_gap,
        "urgency_score": urgency,
        "population_affected_score": affected,
        "neglect_factor": neglect,
        "time_sensitivity_score": time_sensitivity,
        "preventive_value_score": preventive,
        "regional_vulnerability_score": vulnerability,
        "absorptive_capacity_score": absorb,
        "confidence_score": confidence,
        "telemetry_source_reliability": reliability,
        "provenance": provenance,
        "requires_human_review": confidence < 0.55 or not provenance,
    }
