from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(slots=True)
class ImpactSignal:
    charity_id: str
    receipt_quality: float = 0.0
    historical_delivery_score: float = 0.0
    cost_effectiveness_score: float = 0.0
    transparency_score: float = 0.0
    telemetry_source_reliability: float = 0.0
    provenance: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score_impact(signal: ImpactSignal) -> Dict[str, Any]:
    receipt = clamp01(signal.receipt_quality)
    delivery = clamp01(signal.historical_delivery_score)
    cost_effectiveness = clamp01(signal.cost_effectiveness_score)
    transparency = clamp01(signal.transparency_score)
    reliability = clamp01(signal.telemetry_source_reliability)
    provenance = signal.provenance or []
    impact = clamp01(
        0.30 * receipt + 0.30 * delivery + 0.25 * cost_effectiveness + 0.15 * transparency
    )
    confidence = clamp01((0.70 * reliability) + (0.30 if provenance else 0.0))
    return {
        "charity_id": signal.charity_id,
        "impact_score": impact,
        "receipt_quality": receipt,
        "historical_delivery_score": delivery,
        "cost_effectiveness_score": cost_effectiveness,
        "transparency_score": transparency,
        "confidence_score": confidence,
        "telemetry_source_reliability": reliability,
        "provenance": provenance,
        "requires_human_review": confidence < 0.55 or not provenance,
    }
