from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eve_q.proposal_artifact import sha256_hex
from eve_q.soak_harness import perturbed_routes, run_soak_campaign
from shadow_cycle_runner import run_shadow_cycle


COMMIT = "a" * 40


def test_route_perturbations_are_seeded_variable_and_bounded():
    first = perturbed_routes(7, 424242)
    replay = perturbed_routes(7, 424242)
    neighbor = perturbed_routes(8, 424242)

    assert first == replay
    assert first != neighbor
    assert len(first) == 2
    assert {route["chain"] for route in first} == {"base"}

    for route in first:
        assert route["expected_profit_eth"] > 0
        assert route["gas_cost_eth"] >= 0
        assert route["slippage_eth"] >= 0
        assert route["safety_margin_eth"] >= 0


def test_shadow_cycle_replay_has_identical_canonical_proposal_hash(tmp_path: Path):
    stamp = "2026-07-11T20:30:00Z"
    completed = "2026-07-11T20:30:00.250000Z"
    routes = perturbed_routes(3, 424242)

    first = run_shadow_cycle(
        output_dir=tmp_path,
        cycle_id="deterministic-replay-0003",
        candidate_routes=routes,
        producer_commit=COMMIT,
        impact_category="medical_access",
        created_at=stamp,
        completed_at=completed,
    )
    replay = run_shadow_cycle(
        output_dir=tmp_path,
        cycle_id="deterministic-replay-0003",
        candidate_routes=routes,
        producer_commit=COMMIT,
        impact_category="medical_access",
        created_at=stamp,
        completed_at=completed,
    )

    assert first.validation.valid is True
    assert first.validation.trust_increment_allowed is False
    assert sha256_hex(first.proposal_artifact) == sha256_hex(
        replay.proposal_artifact
    )
    assert first.proposal_artifact["authority"] is False
    assert first.proposal_artifact["autonomous_capital_movement"] is False


@pytest.mark.skipif(
    not os.environ.get("SPIRALBLOOM_OS_ROOT"),
    reason="set SPIRALBLOOM_OS_ROOT for cross-repository soak validation",
)
def test_small_cross_repository_soak_campaign(tmp_path: Path):
    control_plane_root = Path(os.environ["SPIRALBLOOM_OS_ROOT"])
    summary = run_soak_campaign(
        cycles=12,
        seed=424242,
        output_dir=tmp_path / "campaign",
        producer_commit=COMMIT,
        control_plane_root=control_plane_root,
        started_at=datetime.now(timezone.utc),
    )

    assert summary["ok"] is True
    assert summary["results"]["proposal_failures"] == 0
    assert summary["results"]["chain_failures"] == 0
    assert summary["results"]["unauthorized_promotions"] == 0
    assert summary["results"]["replay_failures"] == 0
    assert summary["acceptance"]["route_scores_changed"] is True
    assert all(summary["mutations"].values())
    assert Path(summary["artifacts"]["ledger"]).is_file()
    assert Path(summary["artifacts"]["summary"]).is_file()
