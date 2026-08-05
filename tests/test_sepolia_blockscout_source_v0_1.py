from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from eve_q.alpha_doctor import validate_registry
from eve_q.gate1_readonly_runtime import SourceSpec, validate_source_spec_v2


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "registry" / "alpha_testnet_sources_v0_1.json"
REGISTRY_SCHEMA_PATH = (
    ROOT / "schemas" / "alpha_testnet_source_registry_v0_1.schema.json"
)
SOURCE_SPEC_PATH = (
    ROOT
    / "registry"
    / "source_specs"
    / "ethereum_sepolia_blockscout_stats_v0_1.json"
)
MAPPING_PATH = (
    ROOT / "examples" / "alpha" / "sepolia_blockscout_stats_mapping_v0_1.json"
)
MAPPING_SCHEMA_PATH = ROOT / "schemas" / "telemetry_fixture_mapping_v0_1.schema.json"
ASSUMPTIONS_PATH = (
    ROOT / "examples" / "alpha" / "sepolia_blockscout_stats_assumptions_v0_1.json"
)
REVIEW_PATH = (
    ROOT
    / "docs"
    / "source-reviews"
    / "ETHEREUM_SEPOLIA_BLOCKSCOUT_STATS_v0_1.md"
)
SOURCE_ID = "ethereum-sepolia-blockscout-stats-v0-1"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_registry_contains_one_time_bounded_eligible_source() -> None:
    registry = load(REGISTRY_PATH)
    schema = load(REGISTRY_SCHEMA_PATH)
    result = validate_registry(registry, schema)

    assert result.valid is True
    assert result.eligible_source_ids == (SOURCE_ID,)
    assert result.hold_source_ids == ()
    assert result.rejected_source_ids == ()

    source = registry["sources"][0]
    reviewed_at = datetime.fromisoformat(source["reviewed_at"].replace("Z", "+00:00"))
    expires_at = datetime.fromisoformat(
        source["review_expires_at"].replace("Z", "+00:00")
    )
    assert expires_at > reviewed_at
    assert (expires_at - reviewed_at).days == 30
    assert source["authority"] is False
    assert source["mainnet"] is False
    assert source["wallet_required"] is False
    assert source["signing_required"] is False
    assert source["transaction_submission"] is False
    assert source["capital_movement"] is False


def test_source_spec_matches_registry_and_gate1_transport() -> None:
    registry = load(REGISTRY_PATH)
    source = registry["sources"][0]
    specification = load(SOURCE_SPEC_PATH)
    spec = SourceSpec.from_dict(specification)

    validate_source_spec_v2(spec)
    assert spec.source_id == source["source_id"]
    assert spec.url == source["url"]
    assert spec.allowed_hosts == (source["host"],)
    assert spec.freshness_ttl_seconds == source["freshness_ttl_seconds"]
    assert spec.max_response_bytes == source["max_response_bytes"]
    assert spec.timeout_seconds == 10.0
    assert source["allowed_methods"] == ["GET"]


def test_mapping_is_strict_and_preserves_observation_separation() -> None:
    mapping = load(MAPPING_PATH)
    schema = load(MAPPING_SCHEMA_PATH)
    errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(mapping),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )

    assert errors == []
    assert mapping["source_id"] == SOURCE_ID
    assert mapping["network_name"] == "Ethereum Sepolia"
    assert mapping["chain_id"] == "11155111"
    assert mapping["observations"] == [
        {
            "target_field": "observed_average_gas_price_gwei",
            "source_pointer": "/normalized_payload/gas_prices/average",
            "source_unit": "provider-reported gwei",
            "target_unit": "provider-reported gwei",
            "transform": {"kind": "identity"},
        }
    ]
    assert mapping["authority"] is False
    assert mapping["may_generate_live_proposal"] is False
    assert mapping["may_execute"] is False
    assert mapping["may_sign"] is False
    assert mapping["may_submit_transaction"] is False
    assert mapping["may_move_capital"] is False


def test_route_economics_remain_explicit_test_only_assumptions() -> None:
    assumptions = load(ASSUMPTIONS_PATH)["assumptions"]
    fields = {item["field"] for item in assumptions}

    assert {
        "expected_profit_eth",
        "gas_cost_eth",
        "fee_cost_eth",
        "liquidity_eth",
        "latency_ms",
        "slippage_eth",
        "bridge_cost_eth",
        "safety_margin_eth",
    } == fields
    assert "observed_average_gas_price_gwei" not in fields
    assert all("Test-only" in item["basis"] for item in assumptions)


def test_review_receipt_records_deprecation_and_hold_triggers() -> None:
    review = REVIEW_PATH.read_text(encoding="utf-8")

    assert "2026-09-04T01:12:00Z" in review
    assert "deprecat" in review.lower()
    assert "returns to `HOLD`" in review
    assert "not an executable market-data feed" in review
    assert "may_move_capital: false" in review
