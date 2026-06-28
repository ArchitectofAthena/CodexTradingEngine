"""
EVE_Q++ CycleReceipt spine.

A CycleReceipt is the canonical proof object for one observed, simulated,
dry-run, or live execution cycle. Trust expansion must be derived from receipt
validation, never from a raw success=True flag.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import json

CHARITY_RATE = Decimal("0.15")
ETH_QUANT = Decimal("0.000000000000000001")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dec(value: Any) -> Decimal:
    """Convert numeric inputs to Decimal using string conversion for float safety."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def q18(value: Any) -> Decimal:
    """Quantize ETH-like values to 18 decimal places."""
    return dec(value).quantize(ETH_QUANT, rounding=ROUND_HALF_UP)


@dataclass
class CycleReceipt:
    cycle_id: str
    mode: str  # shadow | dry_run | paper | live
    chain: str
    selected_route: Optional[str]
    optimizer_used: str
    candidate_routes: List[Dict[str, Any]] = field(default_factory=list)

    expected_profit_eth: Decimal = Decimal("0")
    actual_profit_eth: Decimal = Decimal("0")
    gas_cost_eth: Decimal = Decimal("0")
    slippage_eth: Decimal = Decimal("0")
    safety_margin_eth: Decimal = Decimal("0")

    charity_due_eth: Decimal = Decimal("0")
    charity_distributed_eth: Decimal = Decimal("0")
    charity_allocations: List[Dict[str, Any]] = field(default_factory=list)

    ipfs_cid: Optional[str] = None
    local_log_path: Optional[str] = None
    tx_hashes: List[str] = field(default_factory=list)

    liveness_valid: bool = False
    execution_success: bool = False
    charity_success: bool = False
    ipfs_success: bool = False
    trust_increment_allowed: bool = False

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    completed_at: Optional[str] = None

    def __post_init__(self) -> None:
        for field_name in (
            "expected_profit_eth",
            "actual_profit_eth",
            "gas_cost_eth",
            "slippage_eth",
            "safety_margin_eth",
            "charity_due_eth",
            "charity_distributed_eth",
        ):
            setattr(self, field_name, q18(getattr(self, field_name)))

    @classmethod
    def shadow(
        cls,
        *,
        cycle_id: str,
        chain: str,
        selected_route: Optional[str],
        optimizer_used: str,
        candidate_routes: Optional[List[Dict[str, Any]]] = None,
        expected_profit_eth: Any = Decimal("0"),
        gas_cost_eth: Any = Decimal("0"),
        slippage_eth: Any = Decimal("0"),
        safety_margin_eth: Any = Decimal("0"),
    ) -> "CycleReceipt":
        """Create a non-trust-gaining shadow receipt for observation/simulation."""
        return cls(
            cycle_id=cycle_id,
            mode="shadow",
            chain=chain,
            selected_route=selected_route,
            optimizer_used=optimizer_used,
            candidate_routes=candidate_routes or [],
            expected_profit_eth=expected_profit_eth,
            actual_profit_eth=Decimal("0"),
            gas_cost_eth=gas_cost_eth,
            slippage_eth=slippage_eth,
            safety_margin_eth=safety_margin_eth,
            liveness_valid=False,
            execution_success=False,
            charity_success=False,
            ipfs_success=False,
            trust_increment_allowed=False,
            warnings=["shadow mode cannot gain trust"],
        )

    def compute_charity_due(self, charity_rate: Decimal = CHARITY_RATE) -> Decimal:
        return q18(self.actual_profit_eth * charity_rate)

    def finalize(self) -> "CycleReceipt":
        self.completed_at = utc_now_iso()
        return self

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Decimal):
                data[key] = str(value)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CycleReceipt":
        numeric_fields = {
            "expected_profit_eth",
            "actual_profit_eth",
            "gas_cost_eth",
            "slippage_eth",
            "safety_margin_eth",
            "charity_due_eth",
            "charity_distributed_eth",
        }
        kwargs = dict(data)
        for field_name in numeric_fields:
            if field_name in kwargs:
                kwargs[field_name] = dec(kwargs[field_name])
        return cls(**kwargs)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "CycleReceipt":
        return cls.from_dict(json.loads(payload))
