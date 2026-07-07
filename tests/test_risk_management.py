from decimal import Decimal

from eve_q.risk_management import ExecutionMode, KellyCriterionOptimizer, RiskLevelManager, RiskTier


def test_live_limits_are_stricter_than_shadow_and_simulation_limits():
    manager = RiskLevelManager(
        portfolio_value_usd=Decimal("100000"),
        risk_tier=RiskTier.CONSERVATIVE,
    )

    shadow = manager.get_limits(ExecutionMode.SHADOW)
    simulation = manager.get_limits(ExecutionMode.SIMULATION)
    live = manager.get_limits(ExecutionMode.LIVE)

    assert live.max_notional_usd < simulation.max_notional_usd < shadow.max_notional_usd
    assert live.max_portfolio_pct < simulation.max_portfolio_pct < shadow.max_portfolio_pct
    assert live.max_per_chain < simulation.max_per_chain < shadow.max_per_chain
    assert live.max_per_asset_pair < simulation.max_per_asset_pair < shadow.max_per_asset_pair


def test_shadow_sized_position_cannot_be_promoted_into_live_mode():
    manager = RiskLevelManager(
        portfolio_value_usd=Decimal("100000"),
        risk_tier=RiskTier.CONSERVATIVE,
    )

    # $2,000 is acceptable in shadow mode under conservative settings, but live mode
    # caps portfolio exposure at 1% ($1,000) after the live safety multiplier.
    notional = Decimal("2000")

    shadow_ok, shadow_violations = manager.can_execute(
        notional=notional,
        chain="base",
        asset_pair="WETH/USDC",
        mode=ExecutionMode.SHADOW,
    )
    live_ok, live_violations = manager.can_execute(
        notional=notional,
        chain="base",
        asset_pair="WETH/USDC",
        mode=ExecutionMode.LIVE,
    )

    assert shadow_ok is True
    assert shadow_violations == []
    assert live_ok is False
    assert live_violations


def test_daily_loss_blocks_execution_even_when_position_size_is_small():
    manager = RiskLevelManager(
        portfolio_value_usd=Decimal("100000"),
        risk_tier=RiskTier.CONSERVATIVE,
    )
    manager.record_pnl(Decimal("-3000"))

    ok, violations = manager.can_execute(
        notional=Decimal("100"),
        chain="base",
        asset_pair="WETH/USDC",
        mode=ExecutionMode.LIVE,
    )

    assert ok is False
    assert any("Daily loss" in violation for violation in violations)


def test_kelly_optimizer_clamps_to_safe_bounds():
    high_edge = KellyCriterionOptimizer(
        win_rate=Decimal("0.99"),
        avg_win=Decimal("100"),
        avg_loss=Decimal("1"),
    )
    bad_edge = KellyCriterionOptimizer(
        win_rate=Decimal("0.10"),
        avg_win=Decimal("1"),
        avg_loss=Decimal("100"),
    )

    assert Decimal("0") <= high_edge.optimal_fraction <= Decimal("1")
    assert bad_edge.optimal_fraction == Decimal("0")
    assert high_edge.size_position(Decimal("1000"), fractional_kelly=Decimal("0.5")) <= Decimal(
        "500"
    )
