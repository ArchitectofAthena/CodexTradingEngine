from __future__ import annotations

from pathlib import Path


STATUS_PATH = Path("docs/telemetry/EVE_Q_GATE1_PILOT_STATUS_v0_1.md")


def test_gate1_pilot_status_opens_only_scoped_alpha_lane():
    text = STATUS_PATH.read_text(encoding="utf-8")

    assert "Gate 0  SIMULATION_ONLY: ACTIVE" in text
    assert (
        "Gate 1A TESTNET_READ_ONLY_ALPHA: ACTIVE FOR APPROVED ALPHA RUNS"
        in text
    )
    assert (
        "Gate 1B MAINNET_READ_ONLY_TELEMETRY: LOCKED PENDING #68 / #76"
        in text
    )
    assert "Gate 2  LIVE_PROPOSAL_GENERATION: LOCKED" in text
    assert "Gate 3  TESTNET_MANUAL_EXTERNAL: LOCKED" in text
    assert "Gate 4–6: LOCKED" in text
    assert '"mainnet_allowed": false' in text
    assert '"may_generate_live_proposal": false' in text
    assert '"may_execute": false' in text
    assert '"may_move_capital": false' in text
    assert '"testnet_read_only_alpha_allowed": true' in text
    assert "does not open the cockpit door to execution" in text
