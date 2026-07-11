from pathlib import Path


def test_gate1_pr_summary_does_not_unlock_gate2():
    text = Path("docs/telemetry/EVE_Q_GATE1_PR_SUMMARY_v0_1.md").read_text(encoding="utf-8")
    assert "does not activate Gate 1" in text
    assert "unlock Gate 2" in text
