from __future__ import annotations

from pathlib import Path


CHECKLIST = Path("docs/telemetry/EVE_Q_GATE1_PR_CHECKLIST_v0_1.md")


def test_pr_checklist_keeps_network_and_later_gates_closed():
    text = CHECKLIST.read_text(encoding="utf-8")

    assert "CI performs no network capture" in text
    assert "Gate 0 remains active" in text
    assert "Gate 1 remains pilot-only" in text
    assert "Gate 2–6 remain locked" in text
    assert "No proposal, execution, or capital surface" in text
