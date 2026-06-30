from eve_q.telemetry.need_score import NeedSignal, score_need
from eve_q.telemetry.impact_score import ImpactSignal, score_impact


def test_need_score_requires_review_without_provenance():
    result = score_need(NeedSignal(cause_id="famine", urgency_score=1.0, telemetry_source_reliability=0.9))
    assert result["need_score"] > 0
    assert result["requires_human_review"] is True


def test_impact_score_uses_receipt_and_delivery():
    result = score_impact(
        ImpactSignal(
            charity_id="kitchen",
            receipt_quality=0.9,
            historical_delivery_score=0.8,
            cost_effectiveness_score=0.7,
            transparency_score=0.9,
            telemetry_source_reliability=0.9,
            provenance=["receipt:abc"],
        )
    )
    assert result["impact_score"] > 0.75
    assert result["requires_human_review"] is False
