from __future__ import annotations

from pathlib import Path


STATUS_PATH = Path("docs/telemetry/EVE_Q_GATE1_PILOT_STATUS_v0_1.md")


def test_gate1_pilot_status_keeps_later_gates_locked():
    text = STATUS_PATH.read_text(encoding="utf-8")

    assert "Gate 0 SIMULATION_ONLY: ACTIVE" in text
    assert "Gate 1 LIVE_READ_ONLY_TELEMETRY: PILOT CODE UNDER REVIEW" in text
    assert "Gate 2 LIVE_PROPOSAL_GENERATION: LOCKED" in text
    assert "Gate 3–6: LOCKED" in text
    assert '"may_generate_live_proposal": false' in text
    assert '"may_execute": false' in text
    assert '"may_move_capital": false' in text
    assert "It does not lower Gate 1" in text
