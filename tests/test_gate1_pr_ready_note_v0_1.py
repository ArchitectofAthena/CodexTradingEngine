from pathlib import Path


def test_gate1_pr_ready_note_separates_pilot_from_activation():
    text = Path("docs/telemetry/EVE_Q_GATE1_PR_READY_NOTE_v0_1.md").read_text(encoding="utf-8")
    assert "automated synthetic validation" in text
    assert "Gate 1 activation remain future" in text
