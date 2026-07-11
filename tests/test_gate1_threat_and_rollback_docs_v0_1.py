from __future__ import annotations

from pathlib import Path


THREAT_MODEL = Path("docs/security/EVE_Q_GATE1_THREAT_MODEL_DRAFT_v0_1.md")
ROLLBACK_PLAN = Path("docs/governance/EVE_Q_GATE1_ROLLBACK_PLAN_DRAFT_v0_1.md")


def test_threat_model_preserves_gate_and_authority_boundaries():
    text = THREAT_MODEL.read_text(encoding="utf-8")

    assert "Gate 1 activation: NOT AUTHORIZED" in text
    assert "Gates 2–6 remain locked" in text
    assert "may_generate_live_proposal=false" in text
    assert "may_execute=false" in text
    assert "may_move_capital=false" in text


def test_rollback_plan_returns_to_simulation_only():
    text = ROLLBACK_PLAN.read_text(encoding="utf-8")

    assert "Gate 0 SIMULATION_ONLY: ACTIVE" in text
    assert "Gate 1 LIVE_READ_ONLY_TELEMETRY: DISABLED" in text
    assert "Gate 2–6: LOCKED" in text
    assert "EVE_Q_GATE1_KILL_SWITCH=1" in text
    assert "no live observation is converted into a live proposal" in text
