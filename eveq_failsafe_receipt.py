"""Receipt-gated failsafe spine for EVE_Q++."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

CHARITY_RATE = Decimal("0.15")
ETH_QUANT = Decimal("0.000000000000000001")
TRUSTABLE_MODES = {"live"}
SIMULATION_MODES = {"shadow", "dry_run", "paper", "simulation"}
NON_PRODUCTION_CID_PREFIXES = ("mock:", "QmMock", "bafyMock", "local-mock:", "local:")
MOCK_CID_PREFIXES = NON_PRODUCTION_CID_PREFIXES


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def q18(value: Any) -> Decimal:
    return dec(value).quantize(ETH_QUANT, rounding=ROUND_HALF_UP)


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def is_non_production_cid(cid: Optional[str]) -> bool:
    if not cid:
        return False
    return cid.startswith(NON_PRODUCTION_CID_PREFIXES)


@dataclass
class CycleReceipt:
    cycle_id: str
    mode: str
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
    proof_type: Optional[str] = None
    proof_production_trust_eligible: bool = False
    proof_metadata: Dict[str, Any] = field(default_factory=dict)
    proof_error: Optional[str] = None
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
            warnings=["shadow mode cannot gain trust"],
        )

    def compute_charity_due(self, charity_rate: Decimal = CHARITY_RATE) -> Decimal:
        return q18(self.actual_profit_eth * charity_rate)

    def finalize(self) -> "CycleReceipt":
        self.completed_at = utc_now_iso()
        return self

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))

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


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    trust_increment_allowed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    computed_charity_due_eth: Decimal = Decimal("0")

    def raise_for_errors(self) -> None:
        if self.errors:
            raise ValueError("; ".join(self.errors))


def _is_mock_cid(cid: Optional[str]) -> bool:
    return is_non_production_cid(cid)


def _close_enough(a: Any, b: Any, tolerance: Decimal) -> bool:
    return abs(dec(a) - dec(b)) <= tolerance


def validate_receipt(
    receipt: CycleReceipt,
    *,
    production_mode: bool = False,
    charity_rate: Decimal = CHARITY_RATE,
    tolerance_eth: Decimal = Decimal("0.000000000000000001"),
) -> ValidationResult:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(receipt, CycleReceipt):
        return ValidationResult(
            valid=False,
            trust_increment_allowed=False,
            errors=["receipt must be a CycleReceipt instance"],
            warnings=warnings,
        )

    mode = (receipt.mode or "").lower().strip()
    actual_profit = q18(receipt.actual_profit_eth)
    computed_charity_due = q18(actual_profit * charity_rate)

    if not receipt.cycle_id:
        errors.append("missing cycle_id")
    if not mode:
        errors.append("missing mode")
    if not receipt.chain:
        errors.append("missing chain")
    if not receipt.optimizer_used:
        errors.append("missing optimizer_used")
    if actual_profit < 0:
        errors.append("actual_profit_eth cannot be negative")
    if not receipt.liveness_valid:
        errors.append("liveness_valid is false")
    if not receipt.execution_success:
        errors.append("execution_success is false")
    if not receipt.charity_success:
        errors.append("charity_success is false")
    if not receipt.ipfs_success:
        errors.append("ipfs_success is false")
    if not receipt.ipfs_cid:
        errors.append("missing ipfs_cid")
    if receipt.proof_error:
        errors.append(f"proof error: {receipt.proof_error}")

    if mode in SIMULATION_MODES:
        warnings.append(f"{mode} mode cannot gain trust")
    elif mode not in TRUSTABLE_MODES:
        warnings.append(f"unrecognized/non-trustable mode: {receipt.mode!r}")

    if production_mode:
        if not receipt.proof_type:
            errors.append("production proof requires proof_type")
        if not receipt.proof_production_trust_eligible:
            errors.append("production proof is not trust eligible")
        if is_non_production_cid(receipt.ipfs_cid):
            errors.append("non-production proof CID cannot be used as production proof")

    charity_due_matches = _close_enough(
        receipt.charity_due_eth,
        computed_charity_due,
        tolerance_eth,
    )
    if not charity_due_matches:
        errors.append("charity_due_eth must equal actual_profit_eth * charity_rate")
    if dec(receipt.charity_distributed_eth) < computed_charity_due:
        errors.append("charity_distributed_eth is less than charity_due_eth")
    if receipt.charity_success and not receipt.charity_allocations:
        errors.append("charity_success is true but charity_allocations is empty")
    if receipt.execution_success and mode == "live" and not receipt.tx_hashes:
        errors.append("live execution receipt requires tx_hashes")

    production_proof_allowed = (
        not production_mode
        or (
            receipt.proof_type is not None
            and receipt.proof_production_trust_eligible
            and not is_non_production_cid(receipt.ipfs_cid)
        )
    )
    computed_trust_allowed = (
        len(errors) == 0
        and mode in TRUSTABLE_MODES
        and receipt.liveness_valid
        and receipt.execution_success
        and actual_profit >= 0
        and charity_due_matches
        and dec(receipt.charity_distributed_eth) >= computed_charity_due
        and receipt.charity_success
        and receipt.ipfs_success
        and receipt.ipfs_cid is not None
        and production_proof_allowed
    )

    if receipt.trust_increment_allowed and not computed_trust_allowed:
        errors.append("receipt claimed trust_increment_allowed=True but proof gates failed")
        computed_trust_allowed = False

    return ValidationResult(
        valid=len(errors) == 0,
        trust_increment_allowed=computed_trust_allowed,
        errors=errors,
        warnings=warnings,
        computed_charity_due_eth=computed_charity_due,
    )


def can_update_trust(receipt: CycleReceipt, *, production_mode: bool = False) -> bool:
    return validate_receipt(receipt, production_mode=production_mode).trust_increment_allowed


class FailsafeStateError(RuntimeError):
    pass


@dataclass
class FailsafeConfig:
    ttl_hours: float = 24.0
    max_ttl_hours: float = 48.0
    trust_level: float = 0.0
    consecutive_failures: int = 0
    last_liveness_at: Optional[str] = None
    state_file: Optional[str] = None

    def snapshot(self) -> Dict[str, Any]:
        return asdict(self)


def _state_payload(cfg: FailsafeConfig) -> Dict[str, Any]:
    data = cfg.snapshot()
    data.pop("state_file", None)
    return data


def _checksum(data: Dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def save_state(cfg: FailsafeConfig, path: Optional[str] = None) -> Path:
    target = Path(path or cfg.state_file or "failsafe_state.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _state_payload(cfg)
    wrapped = {"state": payload, "checksum": _checksum(payload)}
    fd, temp_path = tempfile.mkstemp(
        prefix=target.name,
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(wrapped, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return target


def load_state(path: str) -> FailsafeConfig:
    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        wrapped = json.load(handle)
    state = wrapped.get("state")
    checksum = wrapped.get("checksum")
    if not isinstance(state, dict) or not checksum:
        raise FailsafeStateError("invalid failsafe state envelope")
    if _checksum(state) != checksum:
        raise FailsafeStateError("failsafe state checksum mismatch")
    state["state_file"] = str(target)
    return FailsafeConfig(**state)


def progressive_trust_increment(
    failsafe_cfg: FailsafeConfig,
    *,
    success: bool,
    increment_hours: float = 1.0,
    trust_increment: float = 0.05,
    failure_decay_threshold: int = 3,
    logger: Optional[Callable[[str], None]] = None,
) -> FailsafeConfig:
    if success:
        failsafe_cfg.ttl_hours = min(
            float(failsafe_cfg.max_ttl_hours),
            float(failsafe_cfg.ttl_hours) + increment_hours,
        )
        failsafe_cfg.trust_level = min(
            1.0,
            float(failsafe_cfg.trust_level) + trust_increment,
        )
        failsafe_cfg.consecutive_failures = 0
        failsafe_cfg.last_liveness_at = utc_now_iso()
        if logger:
            logger("validated receipt allowed trust increment")
    else:
        failsafe_cfg.consecutive_failures += 1
        if failsafe_cfg.consecutive_failures >= failure_decay_threshold:
            failsafe_cfg.trust_level = max(
                0.0,
                float(failsafe_cfg.trust_level) - trust_increment,
            )
            if logger:
                logger("repeated receipt failures caused small trust decay")
        elif logger:
            logger("receipt did not validate; preserving grace")

    if failsafe_cfg.state_file:
        save_state(failsafe_cfg)
    return failsafe_cfg


def progressive_trust_increment_from_receipt(
    failsafe_cfg: FailsafeConfig,
    receipt: CycleReceipt,
    *,
    production_mode: bool = False,
    logger: Optional[Callable[[str], None]] = None,
) -> ValidationResult:
    result = validate_receipt(receipt, production_mode=production_mode)

    if not result.trust_increment_allowed and logger:
        for error in result.errors:
            logger(f"receipt validation error: {error}")
        for warning in result.warnings:
            logger(f"receipt validation warning: {warning}")

    progressive_trust_increment(
        failsafe_cfg,
        success=result.trust_increment_allowed,
        logger=logger,
    )
    return result
