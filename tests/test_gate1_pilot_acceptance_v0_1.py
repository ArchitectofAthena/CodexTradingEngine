from __future__ import annotations

import json
from pathlib import Path


ACCEPTANCE_PATH = Path("docs/testing/EVE_Q_GATE1_PILOT_ACCEPTANCE_v0_1.json")


def test_gate1_pilot_acceptance_contract_preserves_locked_posture():
    document = json.loads(ACCEPTANCE_PATH.read_text(encoding="utf-8"))

    assert document["artifact_is_command"] is False
    assert document["authority"] is False
    assert document["human_promotion_required"] is True
    assert document["may_generate_live_proposal"] is False
    assert document["may_execute"] is False
    assert document["may_move_capital"] is False
    assert document["gate_posture"] == {
        "gate_0": "ACTIVE",
        "gate_1": "PILOT_ONLY",
        "gate_2_through_6": "LOCKED",
    }

    required = set(document["required_checks"])
    assert {
        "https_only",
        "get_or_head_only",
        "exact_host_allowlist",
        "zero_write_capable_secrets",
        "offline_replay_valid",
        "no_live_proposal_surface",
        "no_execution_surface",
        "no_capital_surface",
    } <= required
