"""Position sizing and risk management constraints for EVE_Q++.

This module provides multi-layered position size constraints, Kelly criterion optimization,
and risk exposure limits to ensure capital preservation across execution modes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple


class RiskTier(str, Enum):
    """Risk tier classification."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class ExecutionMode(str, Enum):
    """Execution mode affecting risk limits."""

    SHADOW = "shadow"
    DRY_RUN = "dry_run"
    PAPER = "paper"
    SIMULATION = "simulation"
    LIVE = "live"


@dataclass(frozen=True)
class PositionSizeLimit:
    """A position size constraint.

    Attributes:
        name: Constraint name.
        max_notional_usd: Maximum position size in USD.
        max_portfolio_pct: Maximum % of portfolio.
        max_per_chain: Maximum exposure per chain.
        max_per_asset_pair: Maximum per trading pair.
    """

    name: str
    max_notional_usd: Decimal
    max_portfolio_pct: Decimal
    max_per_chain: Decimal
    max_per_asset_pair: Decimal


@dataclass(frozen=True)
class RiskThresholds:
    """Risk thresholds for position management.

    Attributes:
        tier: Risk classification.
        max_daily_loss_pct: Maximum daily loss as % of capital.
        max_drawdown_pct: Maximum drawdown tolerance.
        max_correlation_exposure: Max correlation factor.
        min_profit_threshold_usd: Minimum profit to execute.
    """

    tier: RiskTier
    max_daily_loss_pct: Decimal
    max_drawdown_pct: Decimal
    max_correlation_exposure: Decimal
    min_profit_threshold_usd: Decimal


class RiskLevelManager:
    """Manages risk levels and constraints by execution mode.

    Example:
        >>> manager = RiskLevelManager(portfolio_value_usd=Decimal("100000"))
        >>> limits = manager.get_limits(ExecutionMode.SHADOW)
        >>> can_trade = manager.can_execute(
        ...     notional=Decimal("5000"),
        ...     chain="base",
        ...     mode=ExecutionMode.SHADOW
        ... )
    """

    def __init__(
        self,
        portfolio_value_usd: Decimal,
        risk_tier: RiskTier = RiskTier.CONSERVATIVE,
    ) -> None:
        """Initialize risk manager.

        Args:
            portfolio_value_usd: Total portfolio value.
            risk_tier: Risk classification.
        """
        self.portfolio_value = portfolio_value_usd
        self.risk_tier = risk_tier
        self._position_tracking: Dict[str, Decimal] = {}
        self._daily_pnl: Decimal = Decimal("0")
        self._peak_drawdown: Decimal = Decimal("0")

    def get_limits(self, mode: ExecutionMode) -> PositionSizeLimit:
        """Get position limits for execution mode.

        Args:
            mode: Execution mode.

        Returns:
            PositionSizeLimit for the mode.
        """
        # Mode-based multipliers (relative to tier)
        mode_multipliers = {
            ExecutionMode.SHADOW: Decimal("10"),  # 10x normal
            ExecutionMode.DRY_RUN: Decimal("5"),
            ExecutionMode.PAPER: Decimal("2"),
            ExecutionMode.SIMULATION: Decimal("1"),
            ExecutionMode.LIVE: Decimal("0.5"),  # 50% reduction for live
        }
        multiplier = mode_multipliers.get(mode, Decimal("1"))

        # Tier-based base limits
        tier_configs = {
            RiskTier.CONSERVATIVE: {
                "max_notional_pct": Decimal("5"),
                "max_portfolio_pct": Decimal("2"),
                "max_per_chain_pct": Decimal("1"),
                "max_per_pair_pct": Decimal("0.5"),
            },
            RiskTier.MODERATE: {
                "max_notional_pct": Decimal("10"),
                "max_portfolio_pct": Decimal("5"),
                "max_per_chain_pct": Decimal("2"),
                "max_per_pair_pct": Decimal("1"),
            },
            RiskTier.AGGRESSIVE: {
                "max_notional_pct": Decimal("20"),
                "max_portfolio_pct": Decimal("10"),
                "max_per_chain_pct": Decimal("5"),
                "max_per_pair_pct": Decimal("2"),
            },
        }

        config = tier_configs.get(self.risk_tier, tier_configs[RiskTier.CONSERVATIVE])
        max_notional = (
            self.portfolio_value * config["max_notional_pct"] / Decimal("100") * multiplier
        )
        max_portfolio_pct = config["max_portfolio_pct"] * multiplier
        max_per_chain = (
            self.portfolio_value * config["max_per_chain_pct"] / Decimal("100") * multiplier
        )
        max_per_pair = (
            self.portfolio_value * config["max_per_pair_pct"] / Decimal("100") * multiplier
        )

        return PositionSizeLimit(
            name=f"{self.risk_tier.value}_{mode.value}",
            max_notional_usd=max_notional,
            max_portfolio_pct=max_portfolio_pct,
            max_per_chain=max_per_chain,
            max_per_asset_pair=max_per_pair,
        )

    def get_thresholds(self, mode: ExecutionMode) -> RiskThresholds:
        """Get risk thresholds for execution mode.

        Args:
            mode: Execution mode.

        Returns:
            RiskThresholds for the mode.
        """
        tier_thresholds = {
            RiskTier.CONSERVATIVE: {
                "max_daily_loss_pct": Decimal("2"),
                "max_drawdown_pct": Decimal("5"),
                "max_correlation": Decimal("0.5"),
                "min_profit_usd": Decimal("50"),
            },
            RiskTier.MODERATE: {
                "max_daily_loss_pct": Decimal("5"),
                "max_drawdown_pct": Decimal("10"),
                "max_correlation": Decimal("0.7"),
                "min_profit_usd": Decimal("25"),
            },
            RiskTier.AGGRESSIVE: {
                "max_daily_loss_pct": Decimal("10"),
                "max_drawdown_pct": Decimal("20"),
                "max_correlation": Decimal("0.85"),
                "min_profit_usd": Decimal("10"),
            },
        }

        config = tier_thresholds.get(self.risk_tier, tier_thresholds[RiskTier.CONSERVATIVE])
        return RiskThresholds(
            tier=self.risk_tier,
            max_daily_loss_pct=config["max_daily_loss_pct"],
            max_drawdown_pct=config["max_drawdown_pct"],
            max_correlation_exposure=config["max_correlation"],
            min_profit_threshold_usd=config["min_profit_usd"],
        )

    def can_execute(
        self,
        notional: Decimal,
        chain: str,
        asset_pair: Optional[str] = None,
        mode: ExecutionMode = ExecutionMode.SHADOW,
    ) -> Tuple[bool, List[str]]:
        """Check if a position can be executed.

        Args:
            notional: Position size in USD.
            chain: Blockchain chain.
            asset_pair: Trading pair (e.g., "WETH/USDC").
            mode: Execution mode.

        Returns:
            Tuple of (can_execute, list of constraint violations).
        """
        violations: List[str] = []
        limits = self.get_limits(mode)
        thresholds = self.get_thresholds(mode)

        # Check notional limit
        if notional > limits.max_notional_usd:
            violations.append(f"Position {notional} exceeds limit {limits.max_notional_usd}")

        # Check portfolio % limit
        portfolio_pct = (notional / self.portfolio_value) * Decimal("100")
        if portfolio_pct > limits.max_portfolio_pct:
            violations.append(
                f"Position {portfolio_pct}% exceeds portfolio limit {limits.max_portfolio_pct}%"
            )

        # Check per-chain limit
        chain_exposure = self._position_tracking.get(f"chain:{chain}", Decimal("0")) + notional
        if chain_exposure > limits.max_per_chain:
            violations.append(
                f"Chain {chain} exposure {chain_exposure} exceeds limit {limits.max_per_chain}"
            )

        # Check per-pair limit
        if asset_pair:
            pair_exposure = (
                self._position_tracking.get(f"pair:{asset_pair}", Decimal("0")) + notional
            )
            if pair_exposure > limits.max_per_asset_pair:
                violations.append(
                    f"Pair {asset_pair} exposure {pair_exposure} exceeds limit {limits.max_per_asset_pair}"
                )

        # Check daily loss threshold
        if self._daily_pnl < -self.portfolio_value * thresholds.max_daily_loss_pct / Decimal("100"):
            violations.append(
                f"Daily loss {self._daily_pnl} exceeds threshold {thresholds.max_daily_loss_pct}%"
            )

        return len(violations) == 0, violations

    def record_position(
        self,
        position_id: str,
        notional: Decimal,
        chain: str,
        asset_pair: Optional[str] = None,
    ) -> None:
        """Record a position for tracking.

        Args:
            position_id: Unique position identifier.
            notional: Position size in USD.
            chain: Blockchain chain.
            asset_pair: Trading pair.
        """
        self._position_tracking[f"pos:{position_id}"] = notional
        self._position_tracking[f"chain:{chain}"] = (
            self._position_tracking.get(f"chain:{chain}", Decimal("0")) + notional
        )
        if asset_pair:
            self._position_tracking[f"pair:{asset_pair}"] = (
                self._position_tracking.get(f"pair:{asset_pair}", Decimal("0")) + notional
            )

    def record_pnl(self, pnl: Decimal) -> None:
        """Record profit/loss for the day.

        Args:
            pnl: Profit or loss amount.
        """
        self._daily_pnl += pnl
        drawdown = max(Decimal("0"), -self._daily_pnl / self.portfolio_value * Decimal("100"))
        if drawdown > self._peak_drawdown:
            self._peak_drawdown = drawdown

    def reset_daily_tracking(self) -> None:
        """Reset daily PnL and position tracking."""
        self._daily_pnl = Decimal("0")
        self._position_tracking.clear()


class KellyCriterionOptimizer:
    """Kelly criterion-based position sizing optimizer.

    Example:
        >>> optimizer = KellyCriterionOptimizer(
        ...     win_rate=Decimal("0.55"),
        ...     avg_win=Decimal("1.5"),
        ...     avg_loss=Decimal("1.0")
        ... )
        >>> kelly_fraction = optimizer.optimal_fraction
        >>> position_size = optimizer.size_position(
        ...     capital=Decimal("100000"),
        ...     kelly_fraction=kelly_fraction,
        ...     fractional_kelly=Decimal("0.5")  # Half-Kelly for safety
        ... )
    """

    def __init__(
        self,
        win_rate: Decimal,
        avg_win: Decimal,
        avg_loss: Decimal,
    ) -> None:
        """Initialize Kelly optimizer.

        Args:
            win_rate: Historical win rate (0-1).
            avg_win: Average win amount.
            avg_loss: Average loss amount.
        """
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss

    @property
    def optimal_fraction(self) -> Decimal:
        """Calculate optimal Kelly fraction.

        Kelly % = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win

        Returns:
            Optimal Kelly fraction (0-1).
        """
        if self.avg_win <= 0:
            return Decimal("0")

        numerator = self.win_rate * self.avg_win - (Decimal("1") - self.win_rate) * self.avg_loss
        denominator = self.avg_win
        kelly = numerator / denominator

        # Clamp to [0, 1]
        return max(Decimal("0"), min(Decimal("1"), kelly))

    def size_position(
        self,
        capital: Decimal,
        kelly_fraction: Optional[Decimal] = None,
        fractional_kelly: Decimal = Decimal("0.5"),
    ) -> Decimal:
        """Calculate position size using Kelly criterion.

        Args:
            capital: Available capital.
            kelly_fraction: Specific Kelly fraction to use (uses optimal if None).
            fractional_kelly: Fraction of Kelly to use (e.g., 0.5 = half-Kelly, safer).

        Returns:
            Recommended position size.
        """
        if kelly_fraction is None:
            kelly_fraction = self.optimal_fraction

        # Apply fractional Kelly for safety
        safe_fraction = kelly_fraction * fractional_kelly
        return capital * safe_fraction

    def probability_of_ruin(
        self,
        trades: int,
        kelly_fraction: Optional[Decimal] = None,
    ) -> Decimal:
        """Estimate probability of ruin over N trades.

        Args:
            trades: Number of trades to simulate.
            kelly_fraction: Kelly fraction to use.

        Returns:
            Probability of ruin (0-1).
        """
        if kelly_fraction is None:
            kelly_fraction = self.optimal_fraction

        if kelly_fraction == 0:
            return Decimal("0")

        # Simplified ruin probability: (loss_rate / win_rate) ^ trades
        loss_rate = Decimal("1") - self.win_rate
        if self.win_rate == 0:
            return Decimal("1")

        ratio = loss_rate / self.win_rate
        ruin_prob = ratio**trades

        # Clamp to [0, 1]
        return max(Decimal("0"), min(Decimal("1"), ruin_prob))
