from __future__ import annotations

from pathlib import Path


HANDOFF = Path("docs/telemetry/EVE_Q_GATE1_HANDOFF_v0_1.md")


def test_handoff_keeps_gate1_pilot_only():
    text = HANDOFF.read_text(encoding="utf-8")

    assert "pilot infrastructure only" in text
    assert "Gate 0 remains active" in text
    assert "Gate 1 remains pilot-only" in text
    assert "Gates 2–6 remain locked" in text
