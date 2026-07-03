"""Enhanced receipt models with Pydantic v2 validation.

This module provides validated data models for cycle receipts, routes, and related
trading engine data using Pydantic v2.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, ConfigDict


def utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


class RouteCandidate(BaseModel):
    """Validated arbitrage route candidate.
    
    Attributes:
        route: Human-readable route description (e.g., "base-weth-usdc-weth").
        chain: Blockchain chain name (e.g., "base", "ethereum", "arbitrum").
        expected_profit_eth: Estimated profit in ETH.
        gas_cost_eth: Estimated gas cost in ETH.
        slippage_eth: Estimated slippage in ETH.
        safety_margin_eth: Safety margin buffer in ETH.
        score_eth: Calculated composite score.
    """

    model_config = ConfigDict(str_strip_whitespace=True, validate_default=True)

    route: str = Field(..., min_length=1, description="Route identifier")
    chain: str = Field(..., min_length=1, description="Chain name")
    expected_profit_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Expected profit in ETH",
    )
    gas_cost_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Gas cost in ETH",
    )
    slippage_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Slippage in ETH",
    )
    safety_margin_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Safety margin in ETH",
    )
    score_eth: Decimal = Field(
        Decimal("0"),
        description="Composite score after cost deduction",
    )

    @field_validator("expected_profit_eth", "gas_cost_eth", "slippage_eth", "safety_margin_eth", "score_eth", mode="before")
    @classmethod
    def coerce_decimal(cls, v: Any) -> Decimal:
        """Coerce input to Decimal."""
        if isinstance(v, Decimal):
            return v
        if v is None:
            return Decimal("0")
        return Decimal(str(v))


class CharityAllocation(BaseModel):
    """Charity fund allocation record.
    
    Attributes:
        recipient: Charity wallet or organization identifier.
        amount_eth: Amount allocated in ETH.
        tx_hash: Transaction hash if already disbursed.
        status: Allocation status (pending, confirmed, failed).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    recipient: str = Field(..., min_length=1, description="Recipient identifier")
    amount_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Amount in ETH",
    )
    tx_hash: Optional[str] = Field(None, description="Transaction hash if disbursed")
    status: str = Field("pending", pattern="^(pending|confirmed|failed)$")

    @field_validator("amount_eth", mode="before")
    @classmethod
    def coerce_amount(cls, v: Any) -> Decimal:
        """Coerce input to Decimal."""
        if isinstance(v, Decimal):
            return v
        if v is None:
            return Decimal("0")
        return Decimal(str(v))


class CycleReceiptModel(BaseModel):
    """Validated cycle receipt for trading engine.
    
    This model represents one complete observation/execution cycle of the EVE_Q
    trading engine, including route selection, execution, and proof.
    
    Attributes:
        cycle_id: Unique cycle identifier.
        mode: Execution mode (shadow, dry_run, paper, simulation, live).
        chain: Blockchain chain used.
        selected_route: Selected arbitrage route.
        optimizer_used: Optimizer algorithm identifier.
        candidate_routes: All evaluated route candidates.
        expected_profit_eth: Expected profit before execution.
        actual_profit_eth: Actual profit after execution.
        gas_cost_eth: Actual gas cost.
        slippage_eth: Actual slippage.
        safety_margin_eth: Safety margin used.
        charity_due_eth: 15% charity allocation due.
        charity_distributed_eth: Amount actually distributed.
        charity_allocations: Charity distribution records.
        proof_type: Proof adapter type used.
        proof_production_trust_eligible: Whether proof is production-grade.
        ipfs_cid: IPFS content identifier.
        local_log_path: Local filesystem path to receipt.
        tx_hashes: Transaction hashes from execution.
        execution_success: Whether execution succeeded.
        charity_success: Whether charity distribution succeeded.
        ipfs_success: Whether IPFS upload succeeded.
        trust_increment_allowed: Whether trust level can be incremented.
        errors: List of errors encountered.
        warnings: List of warnings.
        created_at: Receipt creation timestamp.
        completed_at: Receipt completion timestamp.
    """

    model_config = ConfigDict(str_strip_whitespace=True, validate_default=True)

    cycle_id: str = Field(
        default_factory=lambda: f"cycle-{uuid4().hex[:12]}",
        description="Unique cycle identifier",
    )
    mode: str = Field(
        "shadow",
        pattern="^(shadow|dry_run|paper|simulation|live)$",
        description="Execution mode",
    )
    chain: str = Field(..., min_length=1, description="Blockchain chain")
    selected_route: Optional[str] = Field(None, description="Selected route identifier")
    optimizer_used: str = Field(..., min_length=1, description="Optimizer identifier")
    candidate_routes: List[RouteCandidate] = Field(
        default_factory=list,
        description="Evaluated route candidates",
    )
    expected_profit_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Expected profit in ETH",
    )
    actual_profit_eth: Decimal = Field(
        Decimal("0"),
        description="Actual profit in ETH (can be negative)",
    )
    gas_cost_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Gas cost in ETH",
    )
    slippage_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Slippage in ETH",
    )
    safety_margin_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Safety margin in ETH",
    )
    charity_due_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="15% charity allocation",
    )
    charity_distributed_eth: Decimal = Field(
        Decimal("0"),
        ge=Decimal("0"),
        description="Actually distributed charity amount",
    )
    charity_allocations: List[CharityAllocation] = Field(
        default_factory=list,
        description="Charity allocation records",
    )
    proof_type: Optional[str] = Field(None, description="Proof adapter type")
    proof_production_trust_eligible: bool = Field(
        False,
        description="Whether proof is production-grade",
    )
    ipfs_cid: Optional[str] = Field(None, description="IPFS content identifier")
    local_log_path: Optional[str] = Field(None, description="Local log file path")
    tx_hashes: List[str] = Field(
        default_factory=list,
        description="Transaction hashes",
    )
    execution_success: bool = Field(False, description="Execution success flag")
    charity_success: bool = Field(False, description="Charity distribution success")
    ipfs_success: bool = Field(False, description="IPFS upload success")
    trust_increment_allowed: bool = Field(
        False,
        description="Whether trust level can be incremented",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Error messages",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warning messages",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="Receipt creation time",
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="Receipt completion time",
    )

    @field_validator(
        "expected_profit_eth",
        "actual_profit_eth",
        "gas_cost_eth",
        "slippage_eth",
        "safety_margin_eth",
        "charity_due_eth",
        "charity_distributed_eth",
        mode="before",
    )
    @classmethod
    def coerce_decimal(cls, v: Any) -> Decimal:
        """Coerce input to Decimal."""
        if isinstance(v, Decimal):
            return v
        if v is None:
            return Decimal("0")
        return Decimal(str(v))

    def add_error(self, error: str) -> None:
        """Add an error message."""
        if error not in self.errors:
            self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        if warning not in self.warnings:
            self.warnings.append(warning)

    def mark_completed(self) -> None:
        """Mark receipt as completed."""
        self.completed_at = utc_now()

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return self.model_dump(mode="json")
