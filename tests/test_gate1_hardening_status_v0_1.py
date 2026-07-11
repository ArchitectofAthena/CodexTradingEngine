from __future__ import annotations

from pathlib import Path


STATUS = Path("docs/telemetry/EVE_Q_GATE1_HARDENING_STATUS_v0_1.md")


def test_hardening_status_keeps_gate1_unactivated_and_gate2_locked():
    text = STATUS.read_text(encoding="utf-8")

    assert "Gate 0 SIMULATION_ONLY: ACTIVE" in text
    assert "Gate 1 LIVE_READ_ONLY_TELEMETRY: PILOT HARDENING UNDER REVIEW" in text
    assert "Gate 2–6: LOCKED" in text
    assert "No gate is activated by this branch." in text
    assert "transport-level IP pinning" in text
    assert "explicit human promotion" in text
