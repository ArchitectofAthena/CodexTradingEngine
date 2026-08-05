from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable
from urllib.parse import urlparse


class GateOutcome(str, Enum):
    ALLOW = "allow"
    HOLD = "hold"
    RETURN = "return"


class FindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HazardCode(str, Enum):
    SOURCE_NOT_ALLOWLISTED = "source_not_allowlisted"
    PROVENANCE_MISSING = "provenance_missing"
    STALE_SIGNAL = "stale_signal"
    FUTURE_TIMESTAMP = "future_timestamp"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    DUPLICATE_REPLAY = "duplicate_replay"
    SECRET_SHAPE = "secret_shape"
    PROMPT_INJECTION = "prompt_injection"
    AUTHORITY_ESCALATION = "authority_escalation"
    NETWORK_EXPANSION = "network_expansion"
    COHERENCE_LOW = "coherence_low"
    AFFECT_UNSTABLE = "affect_unstable"
    READINESS_LOW = "readiness_low"
    ROUTE_UNSAFE = "route_unsafe"


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _require_probability(value: float, field_name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")


@dataclass(frozen=True)
class InputEnvelope:
    envelope_id: str
    source_id: str
    observed_at: str
    payload: str
    provenance: tuple[str, ...] = ()
    route: str = "road_runner"
    requested_capabilities: tuple[str, ...] = ()
    network_targets: tuple[str, ...] = ()
    destination_public: bool = False
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.envelope_id.strip():
            raise ValueError("envelope_id is required")
        if not self.source_id.strip():
            raise ValueError("source_id is required")
        if not self.payload.strip():
            raise ValueError("payload is required")
        if not self.route.strip():
            raise ValueError("route is required")
        _parse_timestamp(self.observed_at)
        if len(self.provenance) != len(set(self.provenance)):
            raise ValueError("provenance entries must be unique")
        if len(self.requested_capabilities) != len(set(self.requested_capabilities)):
            raise ValueError("requested_capabilities must be unique")
        if len(self.network_targets) != len(set(self.network_targets)):
            raise ValueError("network_targets must be unique")
        if self.authority:
            raise ValueError("input envelopes cannot grant authority")

    @property
    def payload_hash(self) -> str:
        return sha256(self.payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GateContext:
    coherence: float
    affect_stability: float
    readiness: float
    route_safe: bool
    known_payload_hashes: tuple[str, ...] = ()
    reviewed_network_targets: tuple[str, ...] = ()
    downstream_execution_enabled: bool = False

    def __post_init__(self) -> None:
        _require_probability(self.coherence, "coherence")
        _require_probability(self.affect_stability, "affect_stability")
        _require_probability(self.readiness, "readiness")
        if len(self.known_payload_hashes) != len(set(self.known_payload_hashes)):
            raise ValueError("known_payload_hashes must be unique")
        if len(self.reviewed_network_targets) != len(set(self.reviewed_network_targets)):
            raise ValueError("reviewed_network_targets must be unique")


@dataclass(frozen=True)
class HecateGateConfig:
    max_payload_bytes: int = 65_536
    max_age_seconds: int = 300
    future_skew_seconds: int = 30
    maturation_seconds: int = 60
    coherence_threshold: float = 0.65
    affect_stability_threshold: float = 0.60
    readiness_threshold: float = 0.60
    require_provenance: bool = True
    allowed_sources: tuple[str, ...] = ()
    forbidden_capabilities: tuple[str, ...] = (
        "credential_access",
        "deploy",
        "execute",
        "external_write",
        "merge",
        "move_capital",
        "repository_write",
        "sign",
        "broadcast",
        "wallet",
    )

    def __post_init__(self) -> None:
        if self.max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be positive")
        if self.max_age_seconds < 0:
            raise ValueError("max_age_seconds cannot be negative")
        if self.future_skew_seconds < 0:
            raise ValueError("future_skew_seconds cannot be negative")
        if self.maturation_seconds < 0:
            raise ValueError("maturation_seconds cannot be negative")
        _require_probability(self.coherence_threshold, "coherence_threshold")
        _require_probability(self.affect_stability_threshold, "affect_stability_threshold")
        _require_probability(self.readiness_threshold, "readiness_threshold")


@dataclass(frozen=True)
class GateFinding:
    code: HazardCode
    severity: FindingSeverity
    disposition: GateOutcome
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "disposition": self.disposition.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class HecateGateReceipt:
    receipt_id: str
    envelope_id: str
    source_id: str
    route: str
    payload_hash: str
    evaluated_at: str
    outcome: GateOutcome
    findings: tuple[GateFinding, ...]
    held_until: str | None
    admitted_to_field: bool
    authority: bool = False
    artifact_is_command: bool = False
    human_promotion_required: bool = True
    may_execute: bool = False
    may_deploy: bool = False
    may_sign: bool = False
    may_broadcast: bool = False
    may_move_capital: bool = False

    def __post_init__(self) -> None:
        if self.authority:
            raise ValueError("Hecate receipts cannot grant authority")
        if self.artifact_is_command:
            raise ValueError("Hecate receipts cannot become commands")
        protected = (
            self.may_execute,
            self.may_deploy,
            self.may_sign,
            self.may_broadcast,
            self.may_move_capital,
        )
        if any(protected):
            raise ValueError("Hecate receipts cannot grant external authority")
        if self.admitted_to_field is not (self.outcome is GateOutcome.ALLOW):
            raise ValueError("field admission must exactly match ALLOW")

    def to_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "envelope_id": self.envelope_id,
            "source_id": self.source_id,
            "route": self.route,
            "payload_hash": self.payload_hash,
            "evaluated_at": self.evaluated_at,
            "outcome": self.outcome.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "held_until": self.held_until,
            "admitted_to_field": self.admitted_to_field,
            "authority": False,
            "artifact_is_command": False,
            "human_promotion_required": True,
            "may_execute": False,
            "may_deploy": False,
            "may_sign": False,
            "may_broadcast": False,
            "may_move_capital": False,
        }

    @property
    def content_hash(self) -> str:
        return _stable_hash(self.to_dict())


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*"
        r"['\"]?[A-Za-z0-9_./+=-]{12,}",
        re.IGNORECASE,
    ),
)

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore\s+(?:all|any|the)\s+previous\s+instructions\b", re.IGNORECASE),
    re.compile(r"\boverride\s+(?:the\s+)?(?:safety|policy|gate|system)\b", re.IGNORECASE),
    re.compile(r"\b(?:system|developer)\s+prompt\s*:", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+(?:inspect|analyze|question|refuse)\b", re.IGNORECASE),
)

_AUTHORITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bauthority\s*[:=]\s*true\b", re.IGNORECASE),
    re.compile(
        r"\bmay_(?:execute|deploy|sign|broadcast|move_capital|write_repository)"
        r"\s*[:=]\s*true\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:execute|deploy|sign|broadcast|merge)\s+(?:now|immediately|without review)\b",
        re.IGNORECASE,
    ),
)


class HecateInputGate:
    """Anticipatory, deterministic input membrane. It inspects; it never executes."""

    def __init__(self, config: HecateGateConfig | None = None) -> None:
        self.config = config or HecateGateConfig()

    def evaluate(
        self,
        envelope: InputEnvelope,
        *,
        context: GateContext,
        now: str | datetime | None = None,
    ) -> HecateGateReceipt:
        evaluation_time = self._resolve_now(now)
        findings: list[GateFinding] = []

        self._check_source(envelope, findings)
        self._check_provenance(envelope, findings)
        self._check_time(envelope, evaluation_time, findings)
        self._check_payload(envelope, context, findings)
        self._check_capabilities(envelope, context, findings)
        self._check_network(envelope, context, findings)
        self._check_field_state(context, findings)

        outcome = self._outcome(findings)
        held_until = (
            (evaluation_time + timedelta(seconds=self.config.maturation_seconds)).isoformat()
            if outcome is GateOutcome.HOLD
            else None
        )
        receipt_basis = {
            "envelope_id": envelope.envelope_id,
            "source_id": envelope.source_id,
            "route": envelope.route,
            "payload_hash": envelope.payload_hash,
            "evaluated_at": evaluation_time.isoformat(),
            "outcome": outcome.value,
            "findings": [finding.to_dict() for finding in findings],
            "held_until": held_until,
        }
        return HecateGateReceipt(
            receipt_id=f"hecate:{_stable_hash(receipt_basis)[:24]}",
            envelope_id=envelope.envelope_id,
            source_id=envelope.source_id,
            route=envelope.route,
            payload_hash=envelope.payload_hash,
            evaluated_at=evaluation_time.isoformat(),
            outcome=outcome,
            findings=tuple(findings),
            held_until=held_until,
            admitted_to_field=outcome is GateOutcome.ALLOW,
        )

    @staticmethod
    def require_allow(receipt: HecateGateReceipt) -> None:
        if receipt.outcome is not GateOutcome.ALLOW:
            raise PermissionError(
                f"input did not cross Hecate gate: outcome={receipt.outcome.value}"
            )

    @staticmethod
    def _resolve_now(value: str | datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, str):
            return _parse_timestamp(value)
        if value.tzinfo is None:
            raise ValueError("now must include a timezone")
        return value.astimezone(timezone.utc)

    def _check_source(self, envelope: InputEnvelope, findings: list[GateFinding]) -> None:
        if self.config.allowed_sources and envelope.source_id not in self.config.allowed_sources:
            findings.append(
                GateFinding(
                    HazardCode.SOURCE_NOT_ALLOWLISTED,
                    FindingSeverity.MEDIUM,
                    GateOutcome.HOLD,
                    "Source is not in the reviewed source set.",
                )
            )

    def _check_provenance(self, envelope: InputEnvelope, findings: list[GateFinding]) -> None:
        if self.config.require_provenance and not envelope.provenance:
            findings.append(
                GateFinding(
                    HazardCode.PROVENANCE_MISSING,
                    FindingSeverity.MEDIUM,
                    GateOutcome.HOLD,
                    "Input lacks provenance and must mature outside the field.",
                )
            )

    def _check_time(
        self,
        envelope: InputEnvelope,
        now: datetime,
        findings: list[GateFinding],
    ) -> None:
        observed = _parse_timestamp(envelope.observed_at)
        age = (now - observed).total_seconds()
        if age > self.config.max_age_seconds:
            findings.append(
                GateFinding(
                    HazardCode.STALE_SIGNAL,
                    FindingSeverity.MEDIUM,
                    GateOutcome.HOLD,
                    "Input is outside the configured freshness window.",
                )
            )
        if age < -self.config.future_skew_seconds:
            findings.append(
                GateFinding(
                    HazardCode.FUTURE_TIMESTAMP,
                    FindingSeverity.HIGH,
                    GateOutcome.HOLD,
                    "Input timestamp exceeds the permitted future skew.",
                )
            )

    def _check_payload(
        self,
        envelope: InputEnvelope,
        context: GateContext,
        findings: list[GateFinding],
    ) -> None:
        if len(envelope.payload.encode("utf-8")) > self.config.max_payload_bytes:
            findings.append(
                GateFinding(
                    HazardCode.PAYLOAD_TOO_LARGE,
                    FindingSeverity.HIGH,
                    GateOutcome.RETURN,
                    "Payload exceeds the bounded input membrane.",
                )
            )
        if envelope.payload_hash in context.known_payload_hashes:
            findings.append(
                GateFinding(
                    HazardCode.DUPLICATE_REPLAY,
                    FindingSeverity.HIGH,
                    GateOutcome.RETURN,
                    "Payload hash has already crossed or been reviewed.",
                )
            )
        if any(pattern.search(envelope.payload) for pattern in _SECRET_PATTERNS):
            findings.append(
                GateFinding(
                    HazardCode.SECRET_SHAPE,
                    FindingSeverity.CRITICAL,
                    GateOutcome.RETURN,
                    "Secret-shaped material must not enter the field.",
                )
            )
        if any(pattern.search(envelope.payload) for pattern in _INJECTION_PATTERNS):
            findings.append(
                GateFinding(
                    HazardCode.PROMPT_INJECTION,
                    FindingSeverity.HIGH,
                    GateOutcome.RETURN,
                    "Instruction-overriding content is inert at the boundary.",
                )
            )
        if any(pattern.search(envelope.payload) for pattern in _AUTHORITY_PATTERNS):
            findings.append(
                GateFinding(
                    HazardCode.AUTHORITY_ESCALATION,
                    FindingSeverity.CRITICAL,
                    GateOutcome.RETURN,
                    "Payload attempts to convert content into authority.",
                )
            )

    def _check_capabilities(
        self,
        envelope: InputEnvelope,
        context: GateContext,
        findings: list[GateFinding],
    ) -> None:
        forbidden = set(self.config.forbidden_capabilities)
        requested = {item.strip().lower() for item in envelope.requested_capabilities}
        blocked = sorted(requested & forbidden)
        if blocked or context.downstream_execution_enabled:
            details = ", ".join(blocked) if blocked else "downstream execution enabled"
            findings.append(
                GateFinding(
                    HazardCode.AUTHORITY_ESCALATION,
                    FindingSeverity.CRITICAL,
                    GateOutcome.RETURN,
                    f"Forbidden authority request detected: {details}.",
                )
            )

    @staticmethod
    def _canonical_target(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        return value.strip().lower()

    def _check_network(
        self,
        envelope: InputEnvelope,
        context: GateContext,
        findings: list[GateFinding],
    ) -> None:
        reviewed = {
            self._canonical_target(target) for target in context.reviewed_network_targets
        }
        unreviewed = [
            target
            for target in envelope.network_targets
            if self._canonical_target(target) not in reviewed
        ]
        if envelope.destination_public or unreviewed:
            detail = ", ".join(unreviewed) if unreviewed else "public destination"
            findings.append(
                GateFinding(
                    HazardCode.NETWORK_EXPANSION,
                    FindingSeverity.HIGH,
                    GateOutcome.RETURN,
                    f"Unreviewed network expansion detected: {detail}.",
                )
            )

    def _check_field_state(
        self,
        context: GateContext,
        findings: list[GateFinding],
    ) -> None:
        if context.coherence < self.config.coherence_threshold:
            findings.append(
                GateFinding(
                    HazardCode.COHERENCE_LOW,
                    FindingSeverity.MEDIUM,
                    GateOutcome.HOLD,
                    "Coherence is below the crossing threshold.",
                )
            )
        if context.affect_stability < self.config.affect_stability_threshold:
            findings.append(
                GateFinding(
                    HazardCode.AFFECT_UNSTABLE,
                    FindingSeverity.MEDIUM,
                    GateOutcome.HOLD,
                    "Affect stability is below the crossing threshold.",
                )
            )
        if context.readiness < self.config.readiness_threshold:
            findings.append(
                GateFinding(
                    HazardCode.READINESS_LOW,
                    FindingSeverity.MEDIUM,
                    GateOutcome.HOLD,
                    "Readiness is below the crossing threshold.",
                )
            )
        if not context.route_safe:
            findings.append(
                GateFinding(
                    HazardCode.ROUTE_UNSAFE,
                    FindingSeverity.HIGH,
                    GateOutcome.RETURN,
                    "The proposed route is not safe for field admission.",
                )
            )

    @staticmethod
    def _outcome(findings: Iterable[GateFinding]) -> GateOutcome:
        dispositions = {finding.disposition for finding in findings}
        if GateOutcome.RETURN in dispositions:
            return GateOutcome.RETURN
        if GateOutcome.HOLD in dispositions:
            return GateOutcome.HOLD
        return GateOutcome.ALLOW
