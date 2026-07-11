from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eve_q.hybrid_benchmark import load_benchmark_case
from eve_q.strategy_packet_uplift import (
    StrategyPacketError,
    consume_strategy_packet,
    run_seeded_planning_uplift,
    sha256_json,
    write_uplift_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "benchmarks" / "seeded_market_v0_1.json"
PACKET_PATH = ROOT / "examples" / "seeded_strategy_packet_v0_1.json"
MANIFEST_CID = "bafkreifllgyxq2dluftpa5y6qtalomjonpe3tuwv5g2jnyd4luas52yvna"
EXPECTED_COMMITS = {
    "ArchitectofAthena/CodexTradingEngine": "17d0107ded1148a4b7d118d68068b1664400d3eb",
    "ArchitectofAthena/spiralbloom-os": "b64c3753fca90f869302dca45850256936d80e0f",
}
REPLAY_NOW = datetime(2026, 7, 11, 3, 0, tzinfo=timezone.utc)


def _load_packet() -> dict[str, object]:
    return json.loads(PACKET_PATH.read_text(encoding="utf-8"))


def _rehash(packet: dict[str, object]) -> None:
    core = {key: value for key, value in packet.items() if key != "packet_id"}
    packet["packet_id"] = sha256_json(core)


def test_seeded_packet_crosses_only_after_local_candidate_reconstruction() -> None:
    consumed = consume_strategy_packet(
        _load_packet(),
        load_benchmark_case(CASE_PATH),
        now=REPLAY_NOW,
        expected_manifest_cid=MANIFEST_CID,
        expected_repository_commits=EXPECTED_COMMITS,
    )

    assert consumed.packet_id
    assert consumed.source_snapshot_manifest_cid == MANIFEST_CID
    assert dict(consumed.source_repository_commits) == EXPECTED_COMMITS
    assert consumed.successful_evidence_count == 1
    assert len(consumed.hints) == 1
    assert consumed.hints[0].route_candidate_id == "triangle:c75caa8d3b0d0a5134bd"
    assert consumed.as_dict()["remote_dependency"] is False
    assert consumed.as_dict()["human_promotion_required"] is True
    assert consumed.authority is False


def test_packet_hash_tamper_is_rejected() -> None:
    packet = _load_packet()
    packet["task"]["objective"] = "tampered objective"  # type: ignore[index]

    with pytest.raises(StrategyPacketError, match="hash mismatch"):
        consume_strategy_packet(packet, load_benchmark_case(CASE_PATH), now=REPLAY_NOW)


def test_stale_packet_is_rejected() -> None:
    with pytest.raises(StrategyPacketError, match="expired"):
        consume_strategy_packet(
            _load_packet(),
            load_benchmark_case(CASE_PATH),
            now=datetime(2026, 7, 12, tzinfo=timezone.utc),
        )


def test_unknown_local_candidate_is_rejected_even_with_valid_packet_hash() -> None:
    packet = _load_packet()
    proposal = packet["proposals"][0]  # type: ignore[index]
    proposal["codex_evaluation"]["route_candidate_id"] = "triangle:" + "f" * 20  # type: ignore[index]
    _rehash(packet)

    with pytest.raises(StrategyPacketError, match="unknown local route"):
        consume_strategy_packet(packet, load_benchmark_case(CASE_PATH), now=REPLAY_NOW)


def test_authority_escalation_and_raw_response_retention_are_rejected() -> None:
    authority_packet = _load_packet()
    authority_packet["authority"] = True
    _rehash(authority_packet)

    with pytest.raises(StrategyPacketError, match="authority"):
        consume_strategy_packet(
            authority_packet, load_benchmark_case(CASE_PATH), now=REPLAY_NOW
        )

    raw_packet = _load_packet()
    raw_packet["stores_raw_provider_responses"] = True
    _rehash(raw_packet)

    with pytest.raises(StrategyPacketError, match="Raw provider responses"):
        consume_strategy_packet(raw_packet, load_benchmark_case(CASE_PATH), now=REPLAY_NOW)


def test_manifest_and_commit_lineage_must_match_expected_local_state() -> None:
    packet = _load_packet()
    case = load_benchmark_case(CASE_PATH)

    with pytest.raises(StrategyPacketError, match="manifest CID mismatch"):
        consume_strategy_packet(
            packet,
            case,
            now=REPLAY_NOW,
            expected_manifest_cid="bafywrong",
        )

    with pytest.raises(StrategyPacketError, match="source commit mismatch"):
        consume_strategy_packet(
            packet,
            case,
            now=REPLAY_NOW,
            expected_repository_commits={
                "ArchitectofAthena/CodexTradingEngine": "f" * 40
            },
        )


def test_real_rust_uplift_replay_is_deterministic_and_non_authoritative(
    tmp_path: Path,
) -> None:
    route_binary = os.environ.get("CODEX_DELTA_VERIFIER_BIN")
    flash_binary = os.environ.get("CODEX_FLASH_LIQUIDITY_VERIFIER_BIN")
    if not route_binary or not flash_binary:
        pytest.skip("Rust verifier binaries not provided")

    kwargs = {
        "route_executable": Path(route_binary).resolve(),
        "flash_executable": Path(flash_binary).resolve(),
        "now": REPLAY_NOW,
        "expected_manifest_cid": MANIFEST_CID,
        "expected_repository_commits": EXPECTED_COMMITS,
    }
    packet = _load_packet()
    case = load_benchmark_case(CASE_PATH)

    first = run_seeded_planning_uplift(packet, case, **kwargs)
    second = run_seeded_planning_uplift(packet, case, **kwargs)

    assert first == second
    assert first["overall_uplift_class"] == "neutral"
    assert first["historical_replay"] is True
    assert first["remote_dependency"] is False
    assert first["human_promotion_required"] is True
    assert first["authority"] is False
    assert len(first["packet_guided_evaluations"]) == 1
    assert first["packet_guided_evaluations"][0]["locally_verified"] is True
    assert first["comparisons"][0]["route_energy_gap_to_local_exact"] == pytest.approx(
        0.0, abs=1e-15
    )
    assert first["comparisons"][0]["repayment_feasible"] is True
    assert first["comparisons"][0]["uplift_class"] == "neutral"

    output = tmp_path / "planning_uplift_receipt.json"
    write_uplift_receipt(first, output)
    reloaded = json.loads(output.read_text(encoding="utf-8"))
    assert reloaded == first
