from __future__ import annotations

from pathlib import Path


PROMPT = Path("docs/telemetry/EVE_Q_GATE1_FINAL_REVIEW_PROMPT_v0_1.md")


def test_final_review_prompt_preserves_all_gate_boundaries():
    text = PROMPT.read_text(encoding="utf-8")

    assert "pilot infrastructure, not as a gate activation" in text
    assert "Gate 0 remains active" in text
    assert "Gate 1 remains pilot-only" in text
    assert "Gate 2–6 remain locked" in text
    assert "cannot generate proposals, execute, or move capital" in text
