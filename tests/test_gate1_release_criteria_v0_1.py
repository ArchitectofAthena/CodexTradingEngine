from __future__ import annotations

from pathlib import Path


CRITERIA = Path("docs/telemetry/EVE_Q_GATE1_RELEASE_CRITERIA_v0_1.md")


def test_release_criteria_do_not_activate_gate1():
    text = CRITERIA.read_text(encoding="utf-8")

    assert "Gate 0 remains active" in text
    assert "Gate 1 remains pilot-only" in text
    assert "Gate 2–6 remain locked" in text
    assert "does not activate Gate 1" in text
    assert "explicit human promotion" in text
