from eve_q.ttl_policy import (
    evaluate_ttl_state,
    load_ttl_policy,
    validate_ttl_policy_shape,
)


def test_ttl_policy_shape_is_valid():
    assert validate_ttl_policy_shape(load_ttl_policy()) == []


def test_expired_ttl_degrades_to_declared_target():
    result = evaluate_ttl_state(
        {
            "mode": "human_gated_execution",
            "ttl_expired": True,
            "current_ttl_minutes": 30,
            "signals": [],
        }
    )

    assert result["valid"] is True
    assert result["hard_stop"] is False
    assert result["effective_mode"] == "shadow_live_market_data"
    assert result["degraded_to"] == "shadow_live_market_data"
    assert result["human_approval_required"] is True
    assert "ttl_expired" in result["reasons"]


def test_hard_stop_claim_emits_safe_artifact_only():
    policy = load_ttl_policy()
    result = evaluate_ttl_state(
        {
            "mode": "human_gated_execution",
            "current_ttl_minutes": 30,
            "requested_capabilities": ["wallet_signing"],
            "signals": [],
        },
        policy=policy,
    )

    assert result["valid"] is True
    assert result["hard_stop"] is True
    assert result["effective_mode"] == "artifact_only"
    assert result["degraded_to"] == "artifact_only"
    assert result["human_approval_required"] is True
    assert result["reverse_execution_channel_opened"] is False
    assert result["safe_outputs"] == policy["safe_outputs_after_degradation"]
    assert "hard_stop:wallet_signing" in result["reasons"]


def test_ttl_shortening_signal_reduces_active_window():
    result = evaluate_ttl_state(
        {
            "mode": "shadow_live_market_data",
            "current_ttl_minutes": 60,
            "signals": ["market_volatility_spike"],
        }
    )

    assert result["valid"] is True
    assert result["hard_stop"] is False
    assert result["ttl_shortened"] is True
    assert result["ttl_minutes"] < 60
    assert result["ttl_minutes"] >= 1
    assert result["effective_mode"] == "shadow_live_market_data"


def test_unknown_mode_is_invalid():
    result = evaluate_ttl_state({"mode": "god_mode"})

    assert result["valid"] is False
    assert result["effective_mode"] is None
    assert result["errors"] == ["unknown TTL mode: god_mode"]


def test_missing_ttl_for_ttl_required_mode_degrades():
    result = evaluate_ttl_state(
        {
            "mode": "testnet",
            "signals": [],
        }
    )

    assert result["valid"] is True
    assert result["effective_mode"] == "simulation"
    assert result["degraded_to"] == "simulation"
    assert result["human_approval_required"] is True
    assert "ttl_required_but_missing" in result["reasons"]


def test_degradation_never_increases_authority():
    policy = load_ttl_policy()
    ranks = policy["authority_rank"]

    for mode, mode_policy in policy["modes"].items():
        result = evaluate_ttl_state(
            {
                "mode": mode,
                "ttl_expired": True,
                "current_ttl_minutes": mode_policy["max_ttl_minutes"],
                "signals": [],
            },
            policy=policy,
        )

        assert result["valid"] is True
        assert ranks[result["effective_mode"]] <= ranks[mode]


def test_no_trigger_preserves_safe_mode():
    result = evaluate_ttl_state(
        {
            "mode": "simulation",
            "signals": [],
        }
    )

    assert result["valid"] is True
    assert result["hard_stop"] is False
    assert result["effective_mode"] == "simulation"
    assert result["degraded_to"] is None
    assert result["human_approval_required"] is False
    assert result["safe_outputs"] == []
