from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from eve_q.deployment_gates import (
    CircuitBreaker,
    CostBreakdown,
    DeploymentTier,
    GraduationEvaluator,
    MetricsAggregator,
    NetworkCapabilities,
    OpportunityRecord,
    RiskGovernor,
    StabilityEvidence,
    TierPolicy,
)


def policy(**overrides):
    values = {
        "min_detection_accuracy": Decimal("0.80"),
        "min_execution_success_rate": Decimal("0.80"),
        "max_false_positive_rate": Decimal("0.20"),
        "min_expected_net_profit_usd": Decimal("1"),
        "max_drawdown_pct": Decimal("25"),
        "max_failed_attempt_cost_usd": Decimal("5"),
        "max_daily_gas_burn_usd": Decimal("20"),
        "min_sample_size": 2,
        "min_observation_hours": 1,
        "min_restart_recoveries": 1,
        "min_network_interruption_recoveries": 1,
        "max_consecutive_failures": 2,
        "max_attempts_per_hour": 10,
        "daily_loss_ceiling_usd": Decimal("25"),
        "reserve_fund_usd": Decimal("100"),
        "min_surplus_cash_flow_usd": Decimal("50"),
        "requires_human_approval": True,
    }
    values.update(overrides)
    return TierPolicy(**values)


def capabilities():
    return NetworkCapabilities(
        flash_liquidity_supported=True,
        liquidity_depth_sufficient=True,
        dex_available=True,
        fee_model_supported=True,
        reliable=True,
        slippage_model_supported=True,
        tooling_ready=True,
        bridge_exposure_accepted=True,
    )


def record(identifier, when, *, success=True, real=True, net=Decimal("2")):
    return OpportunityRecord(
        opportunity_id=identifier,
        detected=True,
        was_real=real,
        submitted=True,
        execution_succeeded=success,
        gross_opportunity_value_usd=Decimal("10"),
        costs=CostBreakdown(gas_usd=Decimal("1")),
        realized_net_profit_usd=net,
        failed_attempt_cost_usd=Decimal("0") if success else Decimal("1"),
        gas_burn_usd=Decimal("1"),
        lead_time_ms=500,
        prediction_hit=real,
        timestamp=when,
    )


def test_metrics_include_profitability_false_positives_and_stability_window():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    metrics = MetricsAggregator.aggregate(
        [
            record("a", start, success=True, real=True, net=Decimal("4")),
            record(
                "b",
                start + timedelta(hours=2),
                success=False,
                real=False,
                net=Decimal("-1"),
            ),
        ]
    )
    assert metrics.sample_size == 2
    assert metrics.observation_hours == Decimal("2")
    assert metrics.detection_accuracy == Decimal("0.5")
    assert metrics.false_positive_rate == Decimal("0.5")
    assert metrics.execution_success_rate == Decimal("0.5")
    assert metrics.expected_net_profit_usd == Decimal("1.5")
    assert metrics.consecutive_failures == 1


def test_risk_governor_rejects_high_win_but_negative_economics():
    decision = RiskGovernor().evaluate_entry(
        expected_gross_profit_usd=Decimal("10"),
        costs=CostBreakdown(
            flash_loan_premium_usd=Decimal("1"),
            dex_fees_usd=Decimal("2"),
            gas_usd=Decimal("4"),
            priority_fees_usd=Decimal("1"),
            slippage_usd=Decimal("2"),
            expected_revert_cost_usd=Decimal("1"),
        ),
        safety_margin_usd=Decimal("1"),
        daily_loss_usd=Decimal("0"),
        daily_gas_burn_usd=Decimal("0"),
        attempts_last_hour=0,
        consecutive_failures=0,
        policy=policy(),
        circuit_breaker=CircuitBreaker(),
        global_kill_switch=False,
        network_enabled=True,
        strategy_enabled=True,
        live_mode=False,
        human_approved=False,
    )
    assert decision.submit is False
    assert "expected gross profit" in decision.reasons[0]


def test_live_submission_requires_human_approval():
    kwargs = dict(
        expected_gross_profit_usd=Decimal("20"),
        costs=CostBreakdown(gas_usd=Decimal("1")),
        safety_margin_usd=Decimal("2"),
        daily_loss_usd=Decimal("0"),
        daily_gas_burn_usd=Decimal("0"),
        attempts_last_hour=0,
        consecutive_failures=0,
        policy=policy(),
        circuit_breaker=CircuitBreaker(),
        global_kill_switch=False,
        network_enabled=True,
        strategy_enabled=True,
        live_mode=True,
    )
    rejected = RiskGovernor().evaluate_entry(**kwargs, human_approved=False)
    approved = RiskGovernor().evaluate_entry(**kwargs, human_approved=True)
    assert rejected.submit is False
    assert approved.submit is True


def test_ethereum_gate_requires_surplus_cash_flow_and_explicit_approval():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    metrics = MetricsAggregator.aggregate(
        [record("a", start), record("b", start + timedelta(hours=2))]
    )
    evaluator = GraduationEvaluator()
    decision = evaluator.evaluate(
        current_tier=DeploymentTier.LOW_COST_NETWORK,
        requested_tier=DeploymentTier.ETHEREUM_MAINNET,
        policy=policy(),
        metrics=metrics,
        stability=StabilityEvidence(
            restart_recoveries=1,
            network_interruption_recoveries=1,
            unresolved_critical_bugs=0,
        ),
        reserve_fund_usd=Decimal("100"),
        surplus_cash_flow_usd=Decimal("49"),
        capabilities=capabilities(),
        human_approved=False,
    )
    assert decision.eligible is False
    assert any("ongoing surplus cash flow" in item for item in decision.failures)
    assert any("explicit human approval" in item for item in decision.failures)
    assert decision.authority is False


def test_circuit_breaker_requires_human_reset():
    breaker = CircuitBreaker()
    breaker.trip("failure threshold")
    with pytest.raises(PermissionError):
        breaker.reset(human_approved=False)
    breaker.reset(human_approved=True)
    assert breaker.tripped is False
