from __future__ import annotations

from pathlib import Path


NON_GOALS = Path("docs/telemetry/EVE_Q_GATE1_NON_GOALS_v0_1.md")


def test_gate1_non_goals_exclude_execution_and_later_gates():
    text = NON_GOALS.read_text(encoding="utf-8")

    for phrase in (
        "live proposal generation",
        "wallet discovery or access",
        "signing",
        "order construction or submission",
        "transaction construction or broadcast",
        "capital movement",
        "autonomous promotion",
        "Gate 2 or later activation",
    ):
        assert phrase in text
