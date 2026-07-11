from pathlib import Path


def test_hardening_review_note_preserves_locked_gate_posture():
    text = Path(
        "docs/telemetry/EVE_Q_GATE1_HARDENING_REVIEW_NOTE_v0_1.md"
    ).read_text(encoding="utf-8")

    assert "does not activate Gate 1" in text
    assert "does not claim transport-level IP pinning" in text
    assert "does not unlock live proposal generation" in text
    assert "Gate 2–6 remain locked" in text
