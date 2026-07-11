from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from eve_q.ttl_lattice import (
    TTLLatticeError,
    evaluate_ttl_lattice,
    load_bounded_authority_manifest,
    validate_manifest_shape,
)


EVALUATED_AT = "2026-07-11T12:00:00Z"


def fresh_snapshot() -> dict:
    return {
        "evaluated_at": EVALUATED_AT,
        "current_state": "bounded_proposal",
        "clocks": {
            "signal": {"observed_at": "2026-07-11T11:59:30Z"},
            "provider_evidence": {"observed_at": "2026-07-11T11:30:00Z"},
            "strategy_packet": {"observed_at": "2026-07-11T11:58:00Z"},
            "autonomy_lease": {"observed_at": "2026-07-11T00:00:00Z"},
        },
        "requested_scope": {
            "assets": ["BTC", "ETH"],
            "venues": ["historical_replay"],
            "order_types": ["proposal", "simulation"],
            "position_notional_usd": 5000,
            "daily_loss_usd": 100,
            "leverage": 1.0,
        },
        "requested_capabilities": [],
        "renewal_requested": False,
    }


def test_manifest_and_schemas_are_well_formed():
    manifest = load_bounded_authority_manifest()
    assert validate_manifest_shape(manifest) == []

    for path in [
        Path("schemas/bounded_authority_manifest_v0_2.schema.json"),
        Path("schemas/ttl_lattice_receipt_v0_1.schema.json"),
    ]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["$schema"].endswith("2020-12/schema")


def test_fresh_required_clocks_preserve_bounded_proposal_without_authority():
    receipt = evaluate_ttl_lattice(fresh_snapshot())

    assert receipt["effective_state"] == "bounded_proposal"
    assert receipt["degraded"] is False
    assert receipt["hard_stop"] is False
    assert receipt["expired_clocks"] == []
    assert receipt["human_approval_required"] is False
    assert receipt["authority"] is False
    assert receipt["execution_authority"] is False
    assert receipt["wallet_authority"] is False
    assert receipt["capital_authority"] is False
    assert receipt["network_calls_made"] is False
    assert receipt["mutation_performed"] is False


def test_exact_expiry_uses_most_restrictive_clock_target():
    snapshot = fresh_snapshot()
    snapshot["clocks"]["signal"]["observed_at"] = "2026-07-11T11:58:30Z"
    snapshot["clocks"]["provider_evidence"]["observed_at"] = "2026-07-11T11:00:00Z"

    receipt = evaluate_ttl_lattice(snapshot)

    assert receipt["expired_clocks"] == ["provider_evidence", "signal"]
    assert receipt["effective_state"] == "local_analysis_only"
    assert receipt["degraded"] is True
    assert receipt["human_approval_required"] is True


def test_missing_required_clock_fails_closed_to_declared_target():
    snapshot = fresh_snapshot()
    del snapshot["clocks"]["strategy_packet"]

    receipt = evaluate_ttl_lattice(snapshot)

    assert receipt["missing_required_clocks"] == ["strategy_packet"]
    assert receipt["effective_state"] == "local_analysis_only"
    missing = [row for row in receipt["clock_results"] if row["clock"] == "strategy_packet"]
    assert missing[0]["status"] == "missing"
    assert missing[0]["expired"] is True


def test_optional_intent_clock_degrades_to_risk_review_only():
    snapshot = fresh_snapshot()
    snapshot["clocks"]["execution_intent"] = {
        "observed_at": "2026-07-11T11:59:00Z"
    }

    receipt = evaluate_ttl_lattice(snapshot)

    assert receipt["expired_clocks"] == ["execution_intent"]
    assert receipt["effective_state"] == "risk_review_only"
    assert receipt["hard_stop"] is False


def test_autonomy_and_credential_expiry_step_down_without_execution():
    autonomy = fresh_snapshot()
    autonomy["clocks"]["autonomy_lease"]["observed_at"] = "2026-07-10T12:00:00Z"
    autonomy_receipt = evaluate_ttl_lattice(autonomy)
    assert autonomy_receipt["effective_state"] == "alert_only"
    assert autonomy_receipt["hard_stop"] is False

    credential = fresh_snapshot()
    credential["clocks"]["credential_lease"] = {
        "observed_at": "2026-07-09T12:00:00Z"
    }
    credential_receipt = evaluate_ttl_lattice(credential)
    assert credential_receipt["effective_state"] == "inert"
    assert credential_receipt["hard_stop"] is False
    assert credential_receipt["authority"] is False


def test_scope_or_denied_capability_violation_hard_stops_inert():
    snapshot = fresh_snapshot()
    snapshot["requested_scope"]["venues"] = ["live_exchange"]
    snapshot["requested_scope"]["leverage"] = 3.0
    snapshot["requested_capabilities"] = ["wallet_signing"]

    receipt = evaluate_ttl_lattice(snapshot)

    assert receipt["hard_stop"] is True
    assert receipt["effective_state"] == "inert"
    assert receipt["denied_capability_hits"] == ["wallet_signing"]
    assert any(item.startswith("scope_not_allowed:venues") for item in receipt["scope_violations"])
    assert any(item.startswith("scope_ceiling_exceeded:leverage") for item in receipt["scope_violations"])
    assert receipt["human_approval_required"] is True


def test_requested_ttl_is_capped_and_cannot_expand_manifest_ceiling():
    snapshot = fresh_snapshot()
    snapshot["clocks"]["signal"]["ttl_seconds"] = 900

    receipt = evaluate_ttl_lattice(snapshot)
    signal = [row for row in receipt["clock_results"] if row["clock"] == "signal"][0]

    assert signal["requested_ttl_seconds"] == 900
    assert signal["effective_ttl_seconds"] == 90
    assert signal["ttl_capped"] is True
    assert signal["expired"] is False
    assert "ttl_capped:signal:900->90" in receipt["reasons"]


def test_renewal_request_never_self_renews():
    snapshot = fresh_snapshot()
    snapshot["renewal_requested"] = True

    receipt = evaluate_ttl_lattice(snapshot)

    assert receipt["renewal_requested"] is True
    assert receipt["renewal_permitted"] is False
    assert receipt["human_approval_required"] is True
    assert receipt["effective_state"] == "bounded_proposal"
    assert "renewal_requires_external_human_approval" in receipt["reasons"]


def test_unknown_clock_future_timestamp_and_manifest_authority_fail_closed():
    unknown = fresh_snapshot()
    unknown["clocks"]["mystery_clock"] = {"observed_at": EVALUATED_AT}
    with pytest.raises(TTLLatticeError, match="unknown clocks"):
        evaluate_ttl_lattice(unknown)

    future = fresh_snapshot()
    future["clocks"]["signal"]["observed_at"] = "2026-07-11T12:00:01Z"
    with pytest.raises(TTLLatticeError, match="cannot be in the future"):
        evaluate_ttl_lattice(future)

    manifest = deepcopy(load_bounded_authority_manifest())
    manifest["authority"]["execution_authority"] = True
    with pytest.raises(TTLLatticeError, match="invalid bounded authority manifest"):
        evaluate_ttl_lattice(fresh_snapshot(), manifest=manifest)
