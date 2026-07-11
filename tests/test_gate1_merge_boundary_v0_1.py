from __future__ import annotations

from pathlib import Path


BOUNDARY = Path("docs/telemetry/EVE_Q_GATE1_MERGE_BOUNDARY_v0_1.md")


def test_merge_boundary_requires_later_human_promoted_activation():
    text = BOUNDARY.read_text(encoding="utf-8")

    assert "Gate 1 is active" in text
    assert "It does not mean" in text
    assert "live data may generate proposals" in text
    assert "any execution capability exists" in text
    assert "later human-promoted transition" in text
