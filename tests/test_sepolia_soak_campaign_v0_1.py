from __future__ import annotations

import copy
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eve_q.gate1_hardening import build_resolution_receipt
from eve_q.gate1_readonly_runtime import SourceSpec, TransportResult, build_snapshot_v2
from eve_q.sepolia_soak_campaign import (
    AUTHORITY_BOUNDARY,
    CAPTURE_COUNT,
    INTERVAL_SECONDS,
    CaptureEvidence,
    SoakCampaignError,
    run_fixed_count_soak,
    verify_summary,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads(
    (ROOT / "registry" / "alpha_testnet_sources_v0_1.json").read_text(
        encoding="utf-8"
    )
)
REGISTRY_SCHEMA = json.loads(
    (ROOT / "schemas" / "alpha_testnet_source_registry_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
SUMMARY_SCHEMA = json.loads(
    (ROOT / "schemas" / "gate1_sepolia_soak_summary_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
SOURCE_SPEC = SourceSpec.from_dict(
    json.loads(
        (
            ROOT
            / "registry"
            / "source_specs"
            / "ethereum_sepolia_blockscout_stats_v0_1.json"
        ).read_text(encoding="utf-8")
    )
)
COMMIT = "b" * 40
START = datetime(2026, 8, 5, 1, 40, tzinfo=timezone.utc)


def environment(index: int) -> dict[str, str]:
    del index
    return {
        "EVE_Q_GATE1_PILOT": "1",
        "EVE_Q_GATE1_KILL_SWITCH": "0",
    }


def clock(index: int) -> datetime:
    return START + timedelta(seconds=index * INTERVAL_SECONDS)


def fake_resolver(*args, **kwargs):
    del args, kwargs
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("8.8.8.8", 443),
        )
    ]


def evidence(index: int, now: datetime) -> CaptureEvidence:
    body = json.dumps(
        {
            "gas_prices": {
                "average": str(10 + index),
                "fast": str(11 + index),
                "slow": str(9 + index),
            },
            "total_blocks": str(1000 + index),
        }
    ).encode("utf-8")
    transport = TransportResult(
        status=200,
        headers={"Content-Type": "application/json"},
        body=body,
        final_url=SOURCE_SPEC.url,
        retrieved_at=now.isoformat().replace("+00:00", "Z"),
    )
    snapshot, raw_bytes, normalized_bytes = build_snapshot_v2(
        SOURCE_SPEC,
        transport,
        producer_commit=COMMIT,
        method="GET",
    )
    resolution = build_resolution_receipt(
        SOURCE_SPEC,
        producer_commit=COMMIT,
        created_at=transport.retrieved_at,
        resolver=fake_resolver,
    )
    return CaptureEvidence(
        snapshot=snapshot,
        raw_bytes=raw_bytes,
        normalized_bytes=normalized_bytes,
        resolution_receipt=resolution,
    )


def adapter(index: int, now: datetime, env: dict[str, str]) -> CaptureEvidence:
    assert env["EVE_Q_GATE1_PILOT"] == "1"
    return evidence(index, now)


def run(tmp_path: Path, **overrides):
    values = {
        "registry": copy.deepcopy(REGISTRY),
        "registry_schema": REGISTRY_SCHEMA,
        "spec": SOURCE_SPEC,
        "output_dir": tmp_path,
        "producer_commit": COMMIT,
        "capture_adapter": adapter,
        "environment_provider": environment,
        "clock": clock,
        "sleep": lambda seconds: None,
    }
    values.update(overrides)
    return run_fixed_count_soak(**values)


def test_successful_campaign_accepts_and_replays_exactly_25(tmp_path: Path) -> None:
    summary = run(tmp_path / "success")

    assert summary["status"] == "PASS"
    assert summary["results"]["captures_requested"] == CAPTURE_COUNT
    assert summary["results"]["captures_attempted"] == CAPTURE_COUNT
    assert summary["results"]["captures_accepted"] == CAPTURE_COUNT
    assert summary["results"]["captures_rejected"] == 0
    assert summary["results"]["rollbacks"] == 0
    assert summary["results"]["corpus_replayed"] == CAPTURE_COUNT
    assert summary["results"]["all_accepted_snapshots_replayed"] is True
    assert len(summary["accepted_evidence"]) == CAPTURE_COUNT
    assert summary["campaign"]["interval_seconds"] == INTERVAL_SECONDS
    assert summary["campaign"]["maximum_requests_per_minute"] == 5
    assert summary["authority"] == AUTHORITY_BOUNDARY
    assert all(value == 0 for value in summary["counts"].values())
    assert verify_summary(summary, SUMMARY_SCHEMA) == ()


def test_identical_evidence_reproduces_the_same_receipt(tmp_path: Path) -> None:
    first = run(tmp_path / "first")
    second = run(tmp_path / "second")

    assert first["receipt_sha256"] == second["receipt_sha256"]
    assert first["results"]["record_ledger_sha256"] == second["results"][
        "record_ledger_sha256"
    ]


def test_partial_outage_stops_and_rolls_back(tmp_path: Path) -> None:
    def outage(index: int, now: datetime, env: dict[str, str]) -> CaptureEvidence:
        if index == 3:
            raise SoakCampaignError("source_outage", "synthetic source outage")
        return adapter(index, now, env)

    summary = run(tmp_path / "outage", capture_adapter=outage)

    assert summary["status"] == "HOLD"
    assert summary["results"]["captures_attempted"] == 4
    assert summary["results"]["captures_accepted"] == 3
    assert summary["results"]["captures_rejected"] == 1
    assert summary["results"]["rollbacks"] == 1
    assert summary["results"]["corpus_replayed"] == 3
    assert len(list((tmp_path / "outage" / "rollbacks").glob("*.json"))) == 1


def test_kill_switch_is_checked_before_every_capture(tmp_path: Path) -> None:
    calls: list[int] = []

    def counted(index: int, now: datetime, env: dict[str, str]) -> CaptureEvidence:
        calls.append(index)
        return adapter(index, now, env)

    def switched(index: int) -> dict[str, str]:
        return {
            "EVE_Q_GATE1_PILOT": "1",
            "EVE_Q_GATE1_KILL_SWITCH": "1" if index == 2 else "0",
        }

    summary = run(
        tmp_path / "kill-switch",
        capture_adapter=counted,
        environment_provider=switched,
    )

    assert calls == [0, 1]
    assert summary["status"] == "HOLD"
    assert summary["results"]["captures_attempted"] == 3
    assert summary["results"]["captures_accepted"] == 2
    assert summary["results"]["rollbacks"] == 1


def test_stale_snapshot_is_rejected_and_rolled_back(tmp_path: Path) -> None:
    def stale(index: int, now: datetime, env: dict[str, str]) -> CaptureEvidence:
        del env
        return evidence(index, now - timedelta(seconds=300))

    summary = run(tmp_path / "stale", capture_adapter=stale)

    assert summary["status"] == "HOLD"
    assert summary["results"]["captures_attempted"] == 1
    assert summary["results"]["captures_accepted"] == 0
    assert summary["results"]["rollbacks"] == 1


def test_final_corpus_replay_detects_persisted_tampering(tmp_path: Path) -> None:
    def tamper(index: int, capture_dir: Path) -> None:
        if index == 0:
            (capture_dir / "raw.bin").write_bytes(b"tampered after acceptance")

    summary = run(tmp_path / "tamper", post_persist_hook=tamper)

    assert summary["status"] == "HOLD"
    assert summary["results"]["captures_accepted"] == CAPTURE_COUNT
    assert summary["results"]["corpus_replayed"] == CAPTURE_COUNT - 1
    assert summary["results"]["all_accepted_snapshots_replayed"] is False
    assert summary["replay_records"][0]["valid"] is False
    assert summary["replay_records"][0]["findings"]


def test_authority_leakage_is_rejected_and_rolled_back(tmp_path: Path) -> None:
    def leaking(index: int, now: datetime, env: dict[str, str]) -> CaptureEvidence:
        result = evidence(index, now)
        snapshot = copy.deepcopy(dict(result.snapshot))
        snapshot["authority"] = True
        return CaptureEvidence(
            snapshot=snapshot,
            raw_bytes=result.raw_bytes,
            normalized_bytes=result.normalized_bytes,
            resolution_receipt=result.resolution_receipt,
        )

    summary = run(tmp_path / "leak", capture_adapter=leaking)

    assert summary["status"] == "HOLD"
    assert summary["results"]["captures_accepted"] == 0
    assert summary["results"]["rollbacks"] == 1
    assert summary["counts"]["live_proposals_generated"] == 0
    assert summary["counts"]["capital_movements"] == 0


def test_noncanonical_count_or_interval_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SoakCampaignError, match="exactly 25"):
        run(tmp_path / "bad-count", capture_count=24)

    with pytest.raises(SoakCampaignError, match="exactly 12"):
        run(tmp_path / "bad-interval", interval_seconds=1)
