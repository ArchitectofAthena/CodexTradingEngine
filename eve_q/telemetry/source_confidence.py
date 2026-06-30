from __future__ import annotations

from dataclasses import dataclass


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(slots=True)
class SourceConfidenceInput:
    source_name: str
    historical_accuracy: float = 0.5
    recency_score: float = 0.5
    independence_score: float = 0.5
    provenance_quality: float = 0.0
    conflict_penalty: float = 0.0


def score_source_confidence(signal: SourceConfidenceInput) -> float:
    score = (
        0.30 * clamp01(signal.historical_accuracy)
        + 0.20 * clamp01(signal.recency_score)
        + 0.25 * clamp01(signal.independence_score)
        + 0.25 * clamp01(signal.provenance_quality)
        - 0.35 * clamp01(signal.conflict_penalty)
    )
    return clamp01(score)
