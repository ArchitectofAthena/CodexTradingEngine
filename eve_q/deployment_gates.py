"""Configurable deployment gates for CodexTradingEngine.

This module is intentionally non-authoritative: it evaluates eligibility, records
risk decisions, and requires explicit human approval for any real-funds tier.
It does not sign, submit, borrow, or move capital.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import IntEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


class DeploymentTier(IntEnum):
    LOCAL_SIMULATION = 0
    TESTNET = 1
    LOW_COST_NETWORK = 2
    ETHEREUM_MAINNET = 3


@dataclass(frozen=True)
class TierPolicy:
    min_detection_accuracy: Decimal
    min_execution_success_rate: Decimal
    max_false_positive_rate: Decimal
    min_expected_net_profit_usd: Decimal
    max_drawdown_pct: Decimal
    max_failed_attempt_cost_usd: Decimal
    max_daily_gas_burn_usd: Decimal
    min_sample_size: int
    min_observation_hours: int
    min_restart_recoveries: int
    min_network_interruption_recoveries: int
    max_consecutive_failures: int
    max_attempts_per_hour: int
    daily_loss_ceiling_usd: Decimal
    reserve_fund_usd: Decimal
    min_surplus_cash_flow_usd: Decimal = Decimal("0")
    requires_human_approval: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TierPolicy":
        decimal_fields = {
            "min_detection_accuracy",
            "min_execution_success_rate",
            "max_false_positive_rate",
            "min_expected_net_profit_usd",
            "max_drawdown_pct",
            "max_failed_attempt_cost_usd",
            "max_daily_gas_burn_usd",
            "daily_loss_ceiling_usd",
            "reserve_fund_usd",
            "min_surplus_cash_flow_usd",
        }
        values = dict(raw)
        for name in decimal_fields:
            values[name] = Decimal(str(values.get(name, "0")))
        return cls(**values)


@dataclass(frozen=True)
class CostBreakdown:
    flash_loan_premium_usd: Decimal = Decimal("0")
    dex_fees_usd: Decimal = Decimal("0")
    gas_usd: Decimal = Decimal("0")
    priority_fees_usd: Decimal = Decimal("0")
    slippage_usd: Decimal = Decimal("0")
    expected_revert_cost_usd: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return sum(asdict(self).values(), Decimal("0"))


@dataclass(frozen=True)
class OpportunityRecord:
    opportunity_id: str
    detected: bool
    was_real: bool
    submitted: bool
    execution_succeeded: bool
    gross_opportunity_value_usd: Decimal
    costs: CostBreakdown
    realized_net_profit_usd: Decimal
    failed_attempt_cost_usd: Decimal
    gas_burn_usd: Decimal
    lead_time_ms: int
    prediction_hit: bool
    timestamp: datetime


@dataclass(frozen=True)
class StabilityEvidence:
    restart_recoveries: int = 0
    network_interruption_recoveries: int = 0
    unresolved_critical_bugs: int = 0


@dataclass(frozen=True)
class AggregatedMetrics:
    sample_size: int
    observation_hours: Decimal
    detection_accuracy: Decimal
    execution_success_rate: Decimal
    false_positive_rate: Decimal
    expected_net_profit_usd: Decimal
    max_drawdown_pct: Decimal
    max_failed_attempt_cost_usd: Decimal
    daily_gas_burn_usd: Decimal
    consecutive_failures: int
    prediction_hit_rate: Decimal


class MetricsAggregator:
    @staticmethod
    def aggregate(records: Sequence[OpportunityRecord]) -> AggregatedMetrics:
        if not records:
            return AggregatedMetrics(
                sample_size=0,
                observation_hours=Decimal("0"),
                detection_accuracy=Decimal("0"),
                execution_success_rate=Decimal("0"),
                false_positive_rate=Decimal("0"),
                expected_net_profit_usd=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
                max_failed_attempt_cost_usd=Decimal("0"),
                daily_gas_burn_usd=Decimal("0"),
                consecutive_failures=0,
                prediction_hit_rate=Decimal("0"),
            )

        ordered = sorted(records, key=lambda item: item.timestamp)
        opportunities = [item for item in ordered if item.detected]
        submitted = [item for item in ordered if item.submitted]
        true_predictions = sum(1 for item in opportunities if item.was_real)
        false_positives = sum(1 for item in opportunities if not item.was_real)
        successes = sum(1 for item in submitted if item.execution_succeeded)
        prediction_hits = sum(1 for item in ordered if item.prediction_hit)

        equity = Decimal("0")
        peak = Decimal("0")
        max_drawdown = Decimal("0")
        consecutive = 0
        max_consecutive = 0
        daily_gas: dict[str, Decimal] = {}
        for item in ordered:
            equity += item.realized_net_profit_usd
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak * Decimal("100"))
            if item.submitted and not item.execution_succeeded:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            elif item.submitted:
                consecutive = 0
            day = item.timestamp.astimezone(UTC).date().isoformat()
            daily_gas[day] = daily_gas.get(day, Decimal("0")) + item.gas_burn_usd

        elapsed = ordered[-1].timestamp - ordered[0].timestamp
        divisor = Decimal(len(ordered))
        return AggregatedMetrics(
            sample_size=len(ordered),
            observation_hours=Decimal(str(elapsed.total_seconds())) / Decimal("3600"),
            detection_accuracy=Decimal(true_predictions) / Decimal(len(opportunities)) if opportunities else Decimal("0"),
            execution_success_rate=Decimal(successes) / Decimal(len(submitted)) if submitted else Decimal("0"),
            false_positive_rate=Decimal(false_positives) / Decimal(len(opportunities)) if opportunities else Decimal("0"),
            expected_net_profit_usd=sum((item.realized_net_profit_usd for item in ordered), Decimal("0")) / divisor,
            max_drawdown_pct=max_drawdown,
            max_failed_attempt_cost_usd=max((item.failed_attempt_cost_usd for item in ordered), default=Decimal("0")),
            daily_gas_burn_usd=max(daily_gas.values(), default=Decimal("0")),
            consecutive_failures=max_consecutive,
            prediction_hit_rate=Decimal(prediction_hits) / divisor,
        )


@dataclass(frozen=True)
class NetworkCapabilities:
    flash_liquidity_supported: bool
    liquidity_depth_sufficient: bool
    dex_available: bool
    fee_model_supported: bool
    reliable: bool
    slippage_model_supported: bool
    tooling_ready: bool
    bridge_exposure_accepted: bool

    @property
    def ready(self) -> bool:
        return all(asdict(self).values())


@dataclass(frozen=True)
class GraduationDecision:
    eligible: bool
    current_tier: DeploymentTier
    requested_tier: DeploymentTier
    failures: tuple[str, ...]
    human_approval_required: bool
    authority: bool = False


class GraduationEvaluator:
    def evaluate(
        self,
        *,
        current_tier: DeploymentTier,
        requested_tier: DeploymentTier,
        policy: TierPolicy,
        metrics: AggregatedMetrics,
        stability: StabilityEvidence,
        reserve_fund_usd: Decimal,
        surplus_cash_flow_usd: Decimal,
        capabilities: NetworkCapabilities | None,
        human_approved: bool,
    ) -> GraduationDecision:
        failures: list[str] = []
        if requested_tier != current_tier + 1:
            failures.append("tier transitions must advance exactly one level")
        checks = {
            "detection accuracy below minimum": metrics.detection_accuracy >= policy.min_detection_accuracy,
            "execution success rate below minimum": metrics.execution_success_rate >= policy.min_execution_success_rate,
            "false-positive rate above maximum": metrics.false_positive_rate <= policy.max_false_positive_rate,
            "expected net profitability below minimum": metrics.expected_net_profit_usd >= policy.min_expected_net_profit_usd,
            "drawdown above maximum": metrics.max_drawdown_pct <= policy.max_drawdown_pct,
            "failed-attempt cost above maximum": metrics.max_failed_attempt_cost_usd <= policy.max_failed_attempt_cost_usd,
            "daily gas burn above maximum": metrics.daily_gas_burn_usd <= policy.max_daily_gas_burn_usd,
            "sample size below minimum": metrics.sample_size >= policy.min_sample_size,
            "observation period below minimum": metrics.observation_hours >= Decimal(policy.min_observation_hours),
            "restart recovery evidence insufficient": stability.restart_recoveries >= policy.min_restart_recoveries,
            "network interruption recovery evidence insufficient": stability.network_interruption_recoveries >= policy.min_network_interruption_recoveries,
            "unresolved critical bugs remain": stability.unresolved_critical_bugs == 0,
            "consecutive failures above maximum": metrics.consecutive_failures <= policy.max_consecutive_failures,
            "reserve fund below requirement": reserve_fund_usd >= policy.reserve_fund_usd,
        }
        for message, passed in checks.items():
            if not passed:
                failures.append(message)
        if requested_tier >= DeploymentTier.LOW_COST_NETWORK and (capabilities is None or not capabilities.ready):
            failures.append("network adapter capability checks failed")
        if requested_tier is DeploymentTier.ETHEREUM_MAINNET and surplus_cash_flow_usd < policy.min_surplus_cash_flow_usd:
            failures.append("ongoing surplus cash flow below Ethereum requirement")
        if requested_tier >= DeploymentTier.LOW_COST_NETWORK and policy.requires_human_approval and not human_approved:
            failures.append("explicit human approval is required for real-funds promotion")
        return GraduationDecision(
            eligible=not failures,
            current_tier=current_tier,
            requested_tier=requested_tier,
            failures=tuple(failures),
            human_approval_required=policy.requires_human_approval,
            authority=False,
        )


@dataclass
class CircuitBreaker:
    tripped: bool = False
    reasons: list[str] = field(default_factory=list)

    def trip(self, reason: str) -> None:
        self.tripped = True
        self.reasons.append(reason)

    def reset(self, *, human_approved: bool) -> None:
        if not human_approved:
            raise PermissionError("human approval required to reset circuit breaker")
        self.tripped = False
        self.reasons.clear()


@dataclass(frozen=True)
class RiskDecision:
    submit: bool
    reasons: tuple[str, ...]
    expected_net_profit_usd: Decimal


class RiskGovernor:
    def evaluate_entry(
        self,
        *,
        expected_gross_profit_usd: Decimal,
        costs: CostBreakdown,
        safety_margin_usd: Decimal,
        daily_loss_usd: Decimal,
        daily_gas_burn_usd: Decimal,
        attempts_last_hour: int,
        consecutive_failures: int,
        policy: TierPolicy,
        circuit_breaker: CircuitBreaker,
        global_kill_switch: bool,
        network_enabled: bool,
        strategy_enabled: bool,
        live_mode: bool,
        human_approved: bool,
    ) -> RiskDecision:
        expected_net = expected_gross_profit_usd - costs.total
        reasons: list[str] = []
        if expected_gross_profit_usd <= costs.total + safety_margin_usd:
            reasons.append("expected gross profit does not exceed total costs plus safety margin")
        if daily_loss_usd >= policy.daily_loss_ceiling_usd:
            reasons.append("daily loss ceiling reached")
        if daily_gas_burn_usd >= policy.max_daily_gas_burn_usd:
            reasons.append("daily gas-burn ceiling reached")
        if attempts_last_hour >= policy.max_attempts_per_hour:
            reasons.append("maximum attempts per hour reached")
        if consecutive_failures >= policy.max_consecutive_failures:
            reasons.append("maximum consecutive failures reached")
        if circuit_breaker.tripped:
            reasons.append("circuit breaker is tripped")
        if global_kill_switch:
            reasons.append("global kill switch is active")
        if not network_enabled:
            reasons.append("network is disabled")
        if not strategy_enabled:
            reasons.append("strategy is disabled")
        if live_mode and not human_approved:
            reasons.append("explicit human approval is required for live submission")
        return RiskDecision(submit=not reasons, reasons=tuple(reasons), expected_net_profit_usd=expected_net)


class AuditSink(Protocol):
    def append(self, record: Mapping[str, Any]) -> None: ...


class JsonlAuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "timestamp": datetime.now(UTC).isoformat(),
            "authority": False,
            **record,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True, default=str) + "\n")


class GraduationStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"current_tier": int(DeploymentTier.LOCAL_SIMULATION), "history": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def record_decision(self, decision: GraduationDecision, *, approved_by: str | None) -> None:
        state = self.load()
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "decision": {
                "eligible": decision.eligible,
                "current_tier": int(decision.current_tier),
                "requested_tier": int(decision.requested_tier),
                "failures": list(decision.failures),
                "authority": False,
            },
            "approved_by": approved_by,
        }
        state.setdefault("history", []).append(event)
        if decision.eligible and approved_by:
            state["current_tier"] = int(decision.requested_tier)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.path)


def load_tier_policies(path: Path) -> dict[DeploymentTier, TierPolicy]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {DeploymentTier(int(key)): TierPolicy.from_mapping(value) for key, value in raw["tiers"].items()}
