from __future__ import annotations

from pathlib import Path


MATRIX = Path("docs/testing/EVE_Q_GATE1_SYNTHETIC_TEST_MATRIX_v0_1.md")


def test_synthetic_matrix_covers_core_fail_closed_cases():
    text = MATRIX.read_text(encoding="utf-8")

    for phrase in (
        "Valid HTTPS JSON",
        "Equivalent JSON key order",
        "`POST`",
        "Non-allowlisted host",
        "Redirect to non-allowlisted host",
        "Kill switch active",
        "Write-capable secret",
        "Malformed JSON",
        "Response over byte cap",
        "Stale snapshot",
        "Raw-byte hash mismatch",
        "Authority or Gate 2 leakage",
    ):
        assert phrase in text

    assert "without selecting or contacting a live source" in text
