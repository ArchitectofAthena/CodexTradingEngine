from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/run_gate1_read_only_capture_v0_1.sh")


def test_launcher_requires_explicit_pilot_and_honors_kill_switch():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "set -euo pipefail" in text
    assert "EVE_Q_GATE1_PILOT" in text
    assert "EVE_Q_GATE1_KILL_SWITCH" in text
    assert "--capture" in text
    assert "--replay" in text
    assert "live proposal" not in text.lower()
    assert "wallet" not in text.lower()
    assert "sign" not in text.lower()
    assert "transaction" not in text.lower()
