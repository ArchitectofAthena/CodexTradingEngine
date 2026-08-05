from __future__ import annotations

import copy
import json
from pathlib import Path

from eve_q.alpha_doctor import (
    AUTHORITY_BOUNDARY,
    DoctorFacts,
    RegistrySummary,
    evaluate_facts,
    render_text,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "alpha_testnet_source_registry_v0_1.schema.json"
REGISTRY_PATH = ROOT / "registry" / "alpha_testnet_sources_v0_1.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _eligible_source() -> dict:
    return {
        "source_id": "reviewed-sepolia-example",
        "disposition": "ELIGIBLE",
        "network_name": "Ethereum Sepolia",
        "network_class": "testnet",
        "chain_id": "11155111",
        "host": "api-sepolia.example.org",
        "url": "https://api-sepolia.example.org/read-only/snapshot",
        "endpoint_class": "explorer_api",
        "source_operator": "Example reviewed operator",
        "allowed_methods": ["GET"],
        "freshness_ttl_seconds": 300,
        "max_response_bytes": 1048576,
        "units": {
            "quantity": "testnet observation",
            "decimals": None,
            "notes": "Provider-specific fields require explicit translation review.",
        },
        "terms_review": {
            "status": "reviewed",
            "reference": "review-receipt:example",
            "reviewed_at": "2026-08-05T00:20:00Z",
        },
        "rate_limit_notes": "Bounded manual alpha use only.",
        "provenance_group": "example-independent-provider",
        "concentration_risk_note": "One provider is insufficient for production claims.",
        "review_evidence": ["review-receipt:example"],
        "reviewed_at": "2026-08-05T00:20:00Z",
        "authority": False,
        "mainnet": False,
        "wallet_required": False,
        "signing_required": False,
        "transaction_submission": False,
        "capital_movement": False,
    }


def _registry_summary(*, eligible: bool = False, valid: bool = True) -> RegistrySummary:
    return RegistrySummary(
        valid=valid,
        errors=() if valid else ("invalid registry",),
        eligible_source_ids=("reviewed-sepolia-example",) if eligible else (),
        hold_source_ids=(),
        rejected_source_ids=(),
        registry_sha256="a" * 64,
    )


def _facts(**overrides: object) -> DoctorFacts:
    root = ROOT.resolve()
    values: dict[str, object] = {
        "repo_root": str(root),
        "commit_sha": "a" * 40,
        "git_error": None,
        "dirty_paths": (),
        "python_version": "3.13.0",
        "package_origin": str(root / "eve_q" / "__init__.py"),
        "kill_switch_active": False,
        "dangerous_secret_names": (),
        "rust_verifier_path": None,
        "rust_verifier_expected_sha256": None,
        "rust_verifier_actual_sha256": None,
        "rust_verifier_state": "NOT_CONFIGURED",
        "registry": _registry_summary(),
    }
    values.update(overrides)
    return DoctorFacts(**values)  # type: ignore[arg-type]


def test_empty_canonical_registry_is_valid_and_explicitly_has_no_eligible_source() -> None:
    result = validate_registry(_registry(), _schema())

    assert result.valid is True
    assert result.eligible_source_ids == ()
    assert len(result.registry_sha256) == 64


def test_reviewed_testnet_source_can_be_eligible_without_gaining_authority() -> None:
    document = _registry()
    document["sources"] = [_eligible_source()]

    result = validate_registry(document, _schema())

    assert result.valid is True
    assert result.eligible_source_ids == ("reviewed-sepolia-example",)
    assert document["sources"][0]["authority"] is False
    assert document["sources"][0]["transaction_submission"] is False
    assert document["sources"][0]["capital_movement"] is False


def test_mainnet_label_or_write_method_is_rejected() -> None:
    document = _registry()
    source = _eligible_source()
    source["network_name"] = "Ethereum Mainnet"
    source["allowed_methods"] = ["POST"]
    document["sources"] = [source]

    result = validate_registry(document, _schema())

    assert result.valid is False
    assert any("mainnet" in error.lower() for error in result.errors)
    assert any("GET and HEAD" in error for error in result.errors)


def test_exact_host_mismatch_and_ip_literal_are_rejected() -> None:
    mismatch = _registry()
    source = _eligible_source()
    source["host"] = "other.example.org"
    mismatch["sources"] = [source]
    mismatch_result = validate_registry(mismatch, _schema())
    assert mismatch_result.valid is False
    assert any("exact host" in error for error in mismatch_result.errors)

    ip_literal = _registry()
    source = _eligible_source()
    source["host"] = "203.0.113.5"
    source["url"] = "https://203.0.113.5/read-only/snapshot"
    ip_literal["sources"] = [source]
    ip_result = validate_registry(ip_literal, _schema())
    assert ip_result.valid is False
    assert any("IP-literal" in error for error in ip_result.errors)


def test_zero_eligible_sources_is_ready_with_clear_warnings() -> None:
    result = evaluate_facts(_facts())

    assert result.status == "READY_WITH_WARNINGS"
    assert any("no public testnet source" in warning for warning in result.warnings)
    assert any("no Rust verifier" in warning for warning in result.warnings)
    assert result.authority == AUTHORITY_BOUNDARY
    assert result.authority["may_execute"] is False
    assert result.authority["may_move_capital"] is False


def test_clean_explained_environment_with_eligible_source_is_ready() -> None:
    result = evaluate_facts(
        _facts(
            rust_verifier_state="CHECKOUT_LOCAL",
            rust_verifier_path=str(ROOT / "rust" / "verifier"),
            registry=_registry_summary(eligible=True),
        )
    )

    assert result.status == "READY"
    assert result.holds == ()
    assert result.warnings == ()


def test_dirty_tree_holds_unless_explicitly_acknowledged() -> None:
    facts = _facts(dirty_paths=(" M eve_q/alpha_doctor.py",))

    held = evaluate_facts(facts)
    acknowledged = evaluate_facts(facts, acknowledge_dirty=True)

    assert held.status == "HOLD"
    assert any("unexplained changes" in item for item in held.holds)
    assert acknowledged.status == "READY_WITH_WARNINGS"
    assert any("explicitly acknowledged" in item for item in acknowledged.warnings)


def test_kill_switch_and_dangerous_secret_names_hold_without_exposing_values() -> None:
    result = evaluate_facts(
        _facts(
            kill_switch_active=True,
            dangerous_secret_names=("TRADING_API_KEY", "WALLET_SEED"),
        )
    )

    assert result.status == "HOLD"
    text = render_text(result)
    assert "Gate 1 kill switch is active" in text
    assert "TRADING_API_KEY" in text
    assert "WALLET_SEED" in text
    assert "secret-value" not in text


def test_unexplained_package_or_rust_origin_holds() -> None:
    outside = Path("/tmp/unrelated/eve_q/__init__.py")
    package_result = evaluate_facts(_facts(package_origin=str(outside)))
    rust_result = evaluate_facts(
        _facts(
            rust_verifier_state="HOLD_UNEXPLAINED",
            rust_verifier_path="/tmp/unreviewed-verifier",
        )
    )

    assert package_result.status == "HOLD"
    assert any("outside" in item for item in package_result.holds)
    assert rust_result.status == "HOLD"
    assert any("Rust verifier" in item for item in rust_result.holds)


def test_invalid_registry_or_unexplained_git_state_holds() -> None:
    registry_result = evaluate_facts(_facts(registry=_registry_summary(valid=False)))
    git_result = evaluate_facts(
        _facts(commit_sha=None, git_error="git unavailable")
    )

    assert registry_result.status == "HOLD"
    assert git_result.status == "HOLD"
    assert any("cannot be explained" in item for item in git_result.holds)
    assert any("commit" in item for item in git_result.holds)


def test_result_json_separates_readiness_from_authority() -> None:
    result = evaluate_facts(_facts())
    payload = result.as_dict()

    assert payload["status"] == "READY_WITH_WARNINGS"
    assert payload["gate_posture"]["gate_1a"] == "ACTIVE_FOR_APPROVED_ALPHA_RUNS"
    assert payload["gate_posture"]["gate_2"] == "LOCKED"
    assert payload["authority"]["authority"] is False
    assert payload["authority"]["network_capture_allowed"] is False
    assert payload["authority"]["may_generate_live_proposal"] is False
    assert payload["authority"]["may_execute"] is False
    assert payload["authority"]["may_sign"] is False
    assert payload["authority"]["may_submit_transaction"] is False
    assert payload["authority"]["may_move_capital"] is False
