from pathlib import Path


def test_boundary_note_blocks_authority_cascade():
    text = Path("docs/telemetry/EVE_Q_GATE1_NOTE_v0_1.md").read_text(encoding="utf-8")
    assert "may observe" in text
    assert "may not decide, promote, execute, or move capital" in text
