import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eve_q import alpha_frontdoor

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "codex_alpha_acceptance_v0_1.schema.json"


def git_state():
    return {
        "available": True,
        "commit": "2" * 40,
        "branch": "feat/alpha-frontdoor-v0-1",
        "dirty": False,
    }


def ready_steps():
    return [
        {
            "name": "doctor",
            "returncode": 0,
            "timed_out": False,
            "payload": {"status": "READY_WITH_WARNINGS"},
            "stdout_tail": "",
            "stderr_tail": "",
        },
        {
            "name": "status",
            "returncode": 0,
            "timed_out": False,
            "payload": {
                "result_surface": {
                    "PIPELINE": "READY",
                    "EXECUTION": "LOCKED",
                }
            },
            "stdout_tail": "",
            "stderr_tail": "",
        },
        {
            "name": "demo",
            "returncode": 0,
            "timed_out": False,
            "payload": {
                "summary": {
                    "pipeline": "READY",
                    "execution": "LOCKED",
                },
                "boundary": {
                    "authority": False,
                    "may_execute": False,
                    "may_move_capital": False,
                },
            },
            "stdout_tail": "",
            "stderr_tail": "",
        },
        {
            "name": "verify",
            "returncode": 0,
            "timed_out": False,
            "payload": None,
            "stdout_tail": "tests passed",
            "stderr_tail": "",
        },
    ]


def test_channels_preserve_offline_and_human_gated_posture():
    assert set(alpha_frontdoor.CHANNELS) == {
        "cli",
        "gate1_testnet_read_only",
        "offline_simulation",
        "spiralbloom_mcp",
        "ssh_termius",
        "github",
    }
    assert alpha_frontdoor.CHANNELS["gate1_testnet_read_only"]["automatic_capture"] is False
    assert alpha_frontdoor.CHANNELS["offline_simulation"]["network"] == "none"
    assert alpha_frontdoor.BOUNDARY["authority"] is False
    assert alpha_frontdoor.BOUNDARY["automatic_network_capture"] is False
    assert alpha_frontdoor.BOUNDARY["may_move_capital"] is False


def test_ready_receipt_is_deterministic_schema_valid_and_locked():
    kwargs = {
        "steps": ready_steps(),
        "generated_at": "2026-08-06T13:31:00Z",
        "git_state": git_state(),
    }
    first = alpha_frontdoor.build_acceptance_receipt(**kwargs)
    second = alpha_frontdoor.build_acceptance_receipt(**kwargs)

    assert first == second
    assert first["result"] == "READY"
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(first)
    assert first["boundary"]["authority"] is False
    assert first["boundary"]["automatic_network_capture"] is False
    assert first["boundary"]["may_execute"] is False
    assert first["boundary"]["may_move_capital"] is False
    assert first["boundary"]["human_promotion_required"] is True


@pytest.mark.parametrize(
    "mutator",
    [
        lambda steps: steps[0]["payload"].update({"status": "HOLD"}),
        lambda steps: steps[1]["payload"]["result_surface"].update({"PIPELINE": "HOLD"}),
        lambda steps: steps[2]["payload"]["summary"].update({"execution": "UNLOCKED"}),
        lambda steps: steps[3].update({"returncode": 1}),
    ],
)
def test_acceptance_holds_on_doctor_status_demo_or_verify_failure(mutator):
    steps = deepcopy(ready_steps())
    mutator(steps)
    receipt = alpha_frontdoor.build_acceptance_receipt(
        steps=steps,
        generated_at="2026-08-06T13:31:00Z",
        git_state=git_state(),
    )
    assert receipt["result"] == "HOLD"


def test_compost_is_dry_run_and_confined(monkeypatch, tmp_path):
    allowed = tmp_path / "artifacts" / "alpha-activation"
    monkeypatch.setattr(alpha_frontdoor, "ROOT", tmp_path)
    monkeypatch.setattr(alpha_frontdoor, "DEFAULT_OUTPUT", allowed)
    allowed.mkdir(parents=True)
    (allowed / "alpha.json").write_text("{}\n", encoding="utf-8")

    preview = alpha_frontdoor.compost(allowed, apply=False)
    assert preview["applied"] is False
    assert preview["files"] == ["artifacts/alpha-activation/alpha.json"]
    assert allowed.exists()

    applied = alpha_frontdoor.compost(allowed, apply=True)
    assert applied["removed"] is True
    assert not allowed.exists()

    with pytest.raises(ValueError):
        alpha_frontdoor.compost(tmp_path / "outside", apply=True)


def test_frontdoor_exposes_recursive_lifecycle_and_full_verify_switch():
    for command in ("ingest", "renew", "regenerate", "compost", "repeat"):
        parsed = alpha_frontdoor.parser().parse_args([command])
        assert parsed.command == command

    focused = alpha_frontdoor.verify_command(full=False)
    full = alpha_frontdoor.verify_command(full=True)
    assert "tests/test_alpha_doctor_v0_1.py" in focused
    assert "not live" in full
