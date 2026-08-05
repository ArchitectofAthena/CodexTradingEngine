from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eve_q.gate1_readonly_runtime import (
    SourceSpec,
    TransportResult,
    build_snapshot_v2,
)
from eve_q.telemetry_draft_fixture import (
    AUTHORITY_BOUNDARY,
    DraftFixtureError,
    build_draft,
    review_draft,
)


ROOT = Path(__file__).resolve().parents[1]
MAPPING_SCHEMA = json.loads(
    (ROOT / "schemas" / "telemetry_fixture_mapping_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
DRAFT_SCHEMA = json.loads(
    (ROOT / "schemas" / "telemetry_draft_fixture_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
SNAPSHOT_SCHEMA = json.loads(
    (ROOT / "schemas" / "live_read_only_telemetry_snapshot_v0_2.schema.json").read_text(
        encoding="utf-8"
    )
)
REGISTRY_SCHEMA = json.loads(
    (ROOT / "schemas" / "alpha_testnet_source_registry_v0_1.schema.json").read_text(
        encoding="utf-8"
    )
)
NOW = datetime(2026, 8, 5, 0, 31, tzinfo=timezone.utc)


def source_entry() -> dict:
    return {
        "source_id": "reviewed-sepolia-source",
        "disposition": "ELIGIBLE",
        "network_name": "Ethereum Sepolia",
        "network_class": "testnet",
        "chain_id": "11155111",
        "host": "api-sepolia.example.org",
        "url": "https://api-sepolia.example.org/read-only/snapshot",
        "endpoint_class": "explorer_api",
        "source_operator": "Reviewed example operator",
        "allowed_methods": ["GET"],
        "freshness_ttl_seconds": 300,
        "max_response_bytes": 1048576,
        "units": {
            "quantity": "route quote",
            "decimals": 18,
            "notes": "test fixture",
        },
        "terms_review": {
            "status": "reviewed",
            "reference": "receipt:terms",
            "reviewed_at": "2026-08-05T00:20:00Z",
        },
        "rate_limit_notes": "manual alpha only",
        "provenance_group": "example-provider",
        "concentration_risk_note": "single source",
        "review_evidence": ["receipt:source-review"],
        "reviewed_at": "2026-08-05T00:20:00Z",
        "authority": False,
        "mainnet": False,
        "wallet_required": False,
        "signing_required": False,
        "transaction_submission": False,
        "capital_movement": False,
    }


def registry() -> dict:
    return {
        "registry_id": "codex.gate1a.testnet-source-registry.v0.1",
        "schema_version": "0.1",
        "reviewed_at": "2026-08-05T00:20:00Z",
        "producer_commit": "a" * 40,
        "review_note": "Reviewed test fixture only.",
        "authority": False,
        "gate_posture": {
            "gate_0": "ACTIVE",
            "gate_1a": "ACTIVE_FOR_APPROVED_ALPHA_RUNS",
            "gate_1b": "LOCKED",
            "gate_2": "LOCKED",
            "gate_3": "LOCKED",
            "gate_4_through_6": "LOCKED",
        },
        "sources": [source_entry()],
    }


def snapshot_bundle() -> tuple[dict, bytes, bytes]:
    body = json.dumps(
        {"quote": {"expected_profit_wei": "20000000000000000"}}
    ).encode("utf-8")
    spec = SourceSpec(
        source_id="reviewed-sepolia-source",
        source_kind="market_snapshot",
        url="https://api-sepolia.example.org/read-only/snapshot",
        allowed_hosts=("api-sepolia.example.org",),
        freshness_ttl_seconds=300,
    )
    transport = TransportResult(
        status=200,
        headers={"Content-Type": "application/json"},
        body=body,
        final_url=spec.url,
        retrieved_at="2026-08-05T00:30:00Z",
    )
    return build_snapshot_v2(spec, transport, producer_commit="b" * 40)


def mapping() -> dict:
    return {
        "mapping_id": "sepolia-quote-to-route-v0-1",
        "schema_version": "0.1",
        "source_id": "reviewed-sepolia-source",
        "network_name": "Ethereum Sepolia",
        "chain_id": "11155111",
        "route_id": "testnet-weth-usdc-weth",
        "observations": [
            {
                "target_field": "expected_profit_eth",
                "source_pointer": "/normalized_payload/quote/expected_profit_wei",
                "source_unit": "wei",
                "target_unit": "ETH",
                "transform": {
                    "kind": "decimal_scale",
                    "factor": "0.000000000000000001",
                },
            }
        ],
        "authority": False,
        "may_generate_live_proposal": False,
        "may_execute": False,
        "may_sign": False,
        "may_submit_transaction": False,
        "may_move_capital": False,
    }


def assumptions(*, complete: bool = True) -> dict:
    values = {
        "gas_cost_eth": ("0.005", "ETH"),
        "fee_cost_eth": ("0.001", "ETH"),
        "liquidity_eth": ("1.0", "ETH"),
        "latency_ms": ("250", "ms"),
        "slippage_eth": ("0.001", "ETH"),
        "bridge_cost_eth": ("0", "ETH"),
        "safety_margin_eth": ("0.002", "ETH"),
    }
    if not complete:
        values.pop("gas_cost_eth")
    return {
        "assumptions": [
            {
                "field": field,
                "value": value,
                "unit": unit,
                "basis": "operator-supplied test fixture",
            }
            for field, (value, unit) in values.items()
        ]
    }


def build(**overrides):
    snapshot, raw, normalized = snapshot_bundle()
    args = {
        "snapshot": snapshot,
        "raw_bytes": raw,
        "normalized_bytes": normalized,
        "registry": registry(),
        "registry_schema": REGISTRY_SCHEMA,
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "mapping": mapping(),
        "mapping_schema": MAPPING_SCHEMA,
        "assumptions": assumptions(),
        "draft_schema": DRAFT_SCHEMA,
        "now": NOW,
    }
    args.update(overrides)
    return build_draft(**args)


def test_build_separates_observation_transformation_and_assumptions() -> None:
    result = build()
    material = result.draft["draft_material"]

    assert material["observed_fields"][0]["original_value"] == "20000000000000000"
    assert material["transformed_fields"][0]["output_value"] == "0.02"
    assert material["local_route_fixture"]["expected_profit_eth"] == "0.02"
    assert len(material["inferred_assumptions"]) == 7
    assert material["missing_assumptions"] == []
    assert result.draft["operator_review"]["state"] == "DRAFT_UNREVIEWED"
    assert result.draft["local_simulation_eligible"] is False
    assert result.draft["authority"] == AUTHORITY_BOUNDARY


def test_identical_inputs_reproduce_identical_draft_hash() -> None:
    assert build().draft["draft_hash"] == build().draft["draft_hash"]


def test_raw_hash_mismatch_fails_closed() -> None:
    snapshot, _, normalized = snapshot_bundle()
    with pytest.raises(DraftFixtureError, match="raw payload hash mismatch"):
        build(
            snapshot=snapshot,
            raw_bytes=b"tampered",
            normalized_bytes=normalized,
        )


def test_stale_snapshot_fails_closed() -> None:
    with pytest.raises(DraftFixtureError, match="stale"):
        build(now=datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc))


def test_noneligible_source_fails_closed() -> None:
    document = registry()
    document["sources"][0]["disposition"] = "HOLD"
    with pytest.raises(DraftFixtureError, match="ELIGIBLE"):
        build(registry=document)


def test_source_id_or_host_mismatch_fails_closed() -> None:
    bad_mapping = mapping()
    bad_mapping["source_id"] = "other-source"
    with pytest.raises(DraftFixtureError, match="exactly one source"):
        build(mapping=bad_mapping)

    document = registry()
    document["sources"][0]["host"] = "other.example.org"
    document["sources"][0]["url"] = "https://other.example.org/read-only/snapshot"
    with pytest.raises(DraftFixtureError, match="exact host"):
        build(registry=document)


def test_mainnet_identifier_fails_closed() -> None:
    document = registry()
    document["sources"][0]["network_name"] = "Ethereum Mainnet"
    bad_mapping = mapping()
    bad_mapping["network_name"] = "Ethereum Mainnet"
    with pytest.raises(DraftFixtureError, match="mainnet"):
        build(registry=document, mapping=bad_mapping)


def test_assumption_cannot_overwrite_observed_value() -> None:
    document = assumptions()
    document["assumptions"].append(
        {
            "field": "expected_profit_eth",
            "value": "99",
            "unit": "ETH",
            "basis": "overwrite",
        }
    )
    with pytest.raises(DraftFixtureError, match="overwrite observed"):
        build(assumptions=document)


def test_missing_assumptions_remain_explicit() -> None:
    result = build(assumptions=assumptions(complete=False))
    assert result.draft["draft_material"]["missing_assumptions"] == [
        "gas_cost_eth"
    ]


def test_exact_hash_review_enables_only_local_simulation_eligibility() -> None:
    result = build()
    reviewed = review_draft(
        result.draft,
        expected_draft_hash=result.draft["draft_hash"],
        decision="REVIEWED_FOR_LOCAL_SIMULATION",
        reviewer="Architect",
        reviewed_at="2026-08-05T00:32:00Z",
        note="Exact draft reviewed for local simulation only.",
        draft_schema=DRAFT_SCHEMA,
    )

    assert reviewed.draft["local_simulation_eligible"] is True
    assert (
        reviewed.draft["operator_review"]["reviewed_draft_hash"]
        == result.draft["draft_hash"]
    )
    assert reviewed.draft["draft_hash"] == result.draft["draft_hash"]
    assert reviewed.draft["authority"]["may_execute"] is False
    assert reviewed.draft["authority"]["may_move_capital"] is False


def test_review_hash_mismatch_or_missing_assumption_fails_closed() -> None:
    result = build()
    with pytest.raises(DraftFixtureError, match="exact draft hash"):
        review_draft(
            result.draft,
            expected_draft_hash="0" * 64,
            decision="REVIEWED_FOR_LOCAL_SIMULATION",
            reviewer="Architect",
            reviewed_at="2026-08-05T00:32:00Z",
            note="No.",
            draft_schema=DRAFT_SCHEMA,
        )

    incomplete = build(assumptions=assumptions(complete=False))
    with pytest.raises(DraftFixtureError, match="missing economic assumptions"):
        review_draft(
            incomplete.draft,
            expected_draft_hash=incomplete.draft["draft_hash"],
            decision="REVIEWED_FOR_LOCAL_SIMULATION",
            reviewer="Architect",
            reviewed_at="2026-08-05T00:32:00Z",
            note="Insufficient evidence.",
            draft_schema=DRAFT_SCHEMA,
        )


def test_return_for_evidence_preserves_false_authority() -> None:
    result = build(assumptions=assumptions(complete=False))
    reviewed = review_draft(
        result.draft,
        expected_draft_hash=result.draft["draft_hash"],
        decision="RETURN_FOR_EVIDENCE",
        reviewer="Architect",
        reviewed_at="2026-08-05T00:32:00Z",
        note="Supply the missing gas model.",
        draft_schema=DRAFT_SCHEMA,
    )

    assert reviewed.draft["local_simulation_eligible"] is False
    assert reviewed.draft["authority"]["authority"] is False
