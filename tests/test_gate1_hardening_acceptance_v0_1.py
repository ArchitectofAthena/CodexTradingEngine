from __future__ import annotations

import json
from pathlib import Path


ACCEPTANCE_PATH = Path(
    "docs/testing/EVE_Q_GATE1_HARDENING_ACCEPTANCE_v0_1.json"
)


def test_gate1_hardening_acceptance_contract_is_fail_closed():
    document = json.loads(ACCEPTANCE_PATH.read_text(encoding="utf-8"))

    assert document["contract_version"] == "eve_q_gate1_hardening_v0.1"
    assert document["status"] == "implementation_under_review"
    assert all(document["acceptance"].values())
    assert document["gate_posture"] == {
        "gate_0": "ACTIVE",
        "gate_1": "PILOT_ONLY",
        "gate_2_through_6": "LOCKED",
    }
    assert document["artifact_is_command"] is False
    assert document["authority"] is False
    assert document["human_promotion_required"] is True
    assert document["may_generate_live_proposal"] is False
    assert document["may_execute"] is False
    assert document["may_move_capital"] is False
