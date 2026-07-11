from __future__ import annotations

from pathlib import Path


CHECKLIST = Path("docs/telemetry/EVE_Q_GATE1_OPERATOR_CHECKLIST_v0_1.md")


def test_operator_checklist_preserves_read_only_pilot_posture():
    text = CHECKLIST.read_text(encoding="utf-8")

    assert "EVE_Q_GATE1_PILOT=1" in text
    assert "EVE_Q_GATE1_KILL_SWITCH" in text
    assert "Only `GET` or `HEAD`" in text
    assert "No live proposal is generated" in text
    assert "No execution or capital interface" in text
    assert "Output directory is outside the repository" in text
    assert "Gate 2 or later behavior" in text
