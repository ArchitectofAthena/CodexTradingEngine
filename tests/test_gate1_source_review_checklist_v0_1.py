from __future__ import annotations

from pathlib import Path


CHECKLIST = Path("docs/telemetry/EVE_Q_GATE1_SOURCE_REVIEW_CHECKLIST_v0_1.md")


def test_source_review_requires_read_only_transport_and_locked_authority():
    text = CHECKLIST.read_text(encoding="utf-8")

    assert "HTTPS only" in text
    assert "`GET` or `HEAD` only" in text
    assert "Exact hostname" in text
    assert "No wallet seed" in text
    assert "cannot generate a live proposal" in text
    assert "cannot execute" in text
    assert "cannot move capital" in text
    assert "Gate 2–6 remain locked" in text
    assert "Explicit human promotion remains required" in text
