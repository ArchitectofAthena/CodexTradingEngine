from pathlib import Path


def test_gate1_stop_line_keeps_gate2_locked():
    text = Path("docs/telemetry/EVE_Q_GATE1_STOP_LINE_v0_1.md").read_text(encoding="utf-8")
    assert "ends before proposal generation" in text
    assert "Gate 2 remains locked" in text
