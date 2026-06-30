from __future__ import annotations

from typing import Any, Dict, Iterable, List

from eve_q.allocation.geodesic_policy import GeodesicInput, score_allocation


def propose_allocations(signals: Iterable[GeodesicInput]) -> List[Dict[str, Any]]:
    decisions = [score_allocation(signal).to_dict() for signal in signals]
    total = sum(d["recommended_weight"] for d in decisions)
    for decision in decisions:
        decision["normalized_recommended_weight"] = (
            decision["recommended_weight"] / total if total > 0 else 0.0
        )
    return sorted(decisions, key=lambda d: d["allocation_priority"], reverse=True)
