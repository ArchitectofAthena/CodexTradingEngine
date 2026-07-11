from pathlib import Path


def test_hardening_stop_line_blocks_live_proposal_and_execution_surfaces():
    text = Path(
        "docs/telemetry/EVE_Q_GATE1_HARDENING_STOP_LINE_v0_1.md"
    ).read_text(encoding="utf-8")

    assert "No live source is configured" in text
    assert "No live proposal is generated" in text
    assert "No execution or capital surface is introduced" in text
