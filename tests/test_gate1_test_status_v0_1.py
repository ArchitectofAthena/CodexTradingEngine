from __future__ import annotations

from pathlib import Path


STATUS = Path("docs/testing/EVE_Q_GATE1_TEST_STATUS_v0_1.md")


def test_gate1_test_status_blocks_activation_until_evidence_exists():
    text = STATUS.read_text(encoding="utf-8")

    assert "Synthetic boundary tests and CI are pending" in text
    assert "Gate 1 remains pilot-only" in text
    assert "not eligible for activation" in text
