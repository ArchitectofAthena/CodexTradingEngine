from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/run_gate1_read_only_capture_v0_1.sh")


def test_launcher_runs_dns_preflight_postflight_and_rollback_receipts():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--preflight-source" in text
    assert "--verify-resolution-receipt" in text
    assert "resolution_receipt.json" in text
    assert "--write-rollback-receipt" in text
    assert "--validate-rollback-receipt" in text
    assert 'write_rollback "kill_switch"' in text
    assert 'write_rollback "source_outage"' in text
    assert 'write_rollback "dns_policy_failure"' in text
    assert 'BUNDLE="$OUT/snapshot"' in text
    assert "may_execute" not in text
    assert "capital" not in text.lower()
