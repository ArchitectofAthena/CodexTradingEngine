"""Declarative Scroll Protocol registry and proposal composer.

A scroll is a versioned JSON ruleset describing a simulation or observation
strategy. The registry never imports arbitrary implementations and never calls
an ``execute`` method. It can only emit non-authoritative proposal artifacts for
separate simulation and human review.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SCROLL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
ALLOWED_RULE_KEYS = frozenset(
    {
        "description",
        "inputs",
        "filters",
        "scoring",
        "constraints",
        "outputs",
        "assumptions",
    }
)
FORBIDDEN_RULE_KEYS = frozenset(
    {
        "execute",
        "callable",
        "command",
        "shell",
        "subprocess",
        "wallet",
        "private_key",
        "sign",
        "broadcast",
        "transaction",
        "order_submission",
        "move_capital",
    }
)


def utc_now_iso() -> str:
    """Return an offset-aware UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(document: Any) -> bytes:
    """Serialize a JSON-compatible document deterministically."""

    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_document(document: Any) -> str:
    """Hash a JSON-compatible document."""

    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def semver_key(version: str) -> tuple[int, int, int]:
    """Return a numeric semantic-version ordering key."""

    match = SEMVER_RE.fullmatch(version)
    if match is None:
        raise ValueError("version must be strict MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in match.groups())


def _validate_json_value(value: Any, path: str = "rules") -> None:
    """Reject callables and non-JSON values recursively."""

    if callable(value):
        raise TypeError(f"{path} may not contain callables")
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            normalized = key.casefold()
            if normalized in FORBIDDEN_RULE_KEYS:
                raise ValueError(f"{path} contains forbidden capability key: {key}")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise TypeError(f"{path} must contain JSON-compatible values only")


class ScrollStatus(str, Enum):
    """Lifecycle state for a declarative scroll."""

    DRAFT = "draft"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ScrollType(str, Enum):
    """Research classification for a scroll."""

    ARBITRAGE = "arbitrage"
    LIQUIDATION = "liquidation"
    YIELD_FARMING = "yield_farming"
    SWARM_DETECTION = "swarm_detection"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ScrollMetadata:
    """Human-readable metadata for one scroll family."""

    scroll_id: str
    name: str
    description: str
    scroll_type: ScrollType
    author: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    risk_level: str = "medium"

    def __post_init__(self) -> None:
        if not SCROLL_ID_RE.fullmatch(self.scroll_id):
            raise ValueError("scroll_id must use lowercase letters, digits, '.', '_' or '-'")
        if not self.name.strip() or not self.description.strip() or not self.author.strip():
            raise ValueError("name, description, and author are required")
        if self.risk_level not in {"low", "medium", "high"}:
            raise ValueError("risk_level must be low, medium, or high")
        if any(not isinstance(tag, str) or not tag.strip() for tag in self.tags):
            raise ValueError("tags must be non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scroll_id": self.scroll_id,
            "name": self.name,
            "description": self.description,
            "scroll_type": self.scroll_type.value,
            "author": self.author,
            "tags": list(self.tags),
            "risk_level": self.risk_level,
        }


@dataclass(frozen=True)
class ScrollDefinition:
    """Immutable declarative ruleset admitted to the registry."""

    metadata: ScrollMetadata
    version: str
    rules: Mapping[str, Any]
    chain_compatibility: tuple[str, ...] = ("*",)

    def __post_init__(self) -> None:
        semver_key(self.version)
        if not isinstance(self.rules, Mapping):
            raise TypeError("rules must be a mapping")
        unknown = set(self.rules) - ALLOWED_RULE_KEYS
        if unknown:
            raise ValueError(f"unsupported top-level rule keys: {sorted(unknown)}")
        _validate_json_value(dict(self.rules))
        if not self.chain_compatibility or any(
            not isinstance(chain, str) or not chain.strip()
            for chain in self.chain_compatibility
        ):
            raise ValueError("chain_compatibility must contain non-empty strings")
        canonical_json_bytes(self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "version": self.version,
            "rules": dict(self.rules),
            "chain_compatibility": list(self.chain_compatibility),
        }

    @property
    def checksum(self) -> str:
        return sha256_document(self.to_payload())

    def is_compatible_with_chain(self, chain: str) -> bool:
        return chain in self.chain_compatibility or "*" in self.chain_compatibility


@dataclass(frozen=True)
class ScrollVersion:
    """Registry receipt for an admitted declarative scroll."""

    scroll_id: str
    version: str
    status: ScrollStatus
    checksum: str
    chain_compatibility: tuple[str, ...] = field(default_factory=tuple)
    min_trust_level: int = 1
    released_at: str = field(default_factory=utc_now_iso)
    deprecated_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        semver_key(self.version)
        if self.min_trust_level < 0:
            raise ValueError("min_trust_level may not be negative")
        if not re.fullmatch(r"[0-9a-f]{64}", self.checksum):
            raise ValueError("checksum must be a lowercase SHA-256 hex digest")

    def is_active(self) -> bool:
        return self.status in {ScrollStatus.DRAFT, ScrollStatus.VALIDATED}

    def is_compatible_with_chain(self, chain: str) -> bool:
        return chain in self.chain_compatibility or "*" in self.chain_compatibility


@dataclass(frozen=True)
class ScrollProposal:
    """Non-authoritative proposal emitted from declarative scrolls."""

    proposal_id: str
    scroll_refs: tuple[dict[str, str], ...]
    signal: str
    context: Mapping[str, Any]
    proposed_steps: tuple[dict[str, Any], ...]
    created_at: str = field(default_factory=utc_now_iso)
    authority: bool = False
    human_promotion_required: bool = True
    may_execute: bool = False
    may_sign: bool = False
    may_broadcast: bool = False
    may_move_capital: bool = False

    def __post_init__(self) -> None:
        if not self.proposal_id.strip() or not self.signal.strip():
            raise ValueError("proposal_id and signal are required")
        _validate_json_value(dict(self.context), "context")
        _validate_json_value(list(self.proposed_steps), "proposed_steps")
        if any(
            (
                self.authority,
                not self.human_promotion_required,
                self.may_execute,
                self.may_sign,
                self.may_broadcast,
                self.may_move_capital,
            )
        ):
            raise ValueError("scroll proposals must remain non-authoritative")

    def to_dict(self) -> dict[str, Any]:
        document = {
            "artifact_type": "ScrollProposal",
            "proposal_id": self.proposal_id,
            "scroll_refs": list(self.scroll_refs),
            "signal": self.signal,
            "context": dict(self.context),
            "proposed_steps": list(self.proposed_steps),
            "created_at": self.created_at,
            "authority": self.authority,
            "human_promotion_required": self.human_promotion_required,
            "may_execute": self.may_execute,
            "may_sign": self.may_sign,
            "may_broadcast": self.may_broadcast,
            "may_move_capital": self.may_move_capital,
        }
        document["artifact_sha256"] = sha256_document(document)
        return document


class ScrollRegistry:
    """Version declarative scrolls and emit pure proposal artifacts."""

    def __init__(self) -> None:
        self._definitions: dict[str, ScrollDefinition] = {}
        self._versions: dict[str, list[ScrollVersion]] = {}

    def register(self, definition: ScrollDefinition) -> ScrollVersion:
        """Register one immutable declarative definition."""

        if not isinstance(definition, ScrollDefinition):
            raise TypeError("register accepts ScrollDefinition only, never a class or callable")
        key = f"{definition.metadata.scroll_id}:{definition.version}"
        if key in self._definitions:
            raise ValueError(f"scroll version already registered: {key}")
        receipt = ScrollVersion(
            scroll_id=definition.metadata.scroll_id,
            version=definition.version,
            status=ScrollStatus.DRAFT,
            checksum=definition.checksum,
            chain_compatibility=definition.chain_compatibility,
            metadata=definition.metadata.to_dict(),
        )
        self._definitions[key] = definition
        self._versions.setdefault(definition.metadata.scroll_id, []).append(receipt)
        return receipt

    def get(self, scroll_id: str, version: str | None = None) -> ScrollDefinition | None:
        """Retrieve an active definition, choosing the highest numeric semver."""

        versions = [item for item in self._versions.get(scroll_id, []) if item.is_active()]
        if not versions:
            return None
        chosen = version or max(versions, key=lambda item: semver_key(item.version)).version
        candidate = self._definitions.get(f"{scroll_id}:{chosen}")
        if candidate is None:
            return None
        if not any(item.version == chosen and item.is_active() for item in versions):
            return None
        return candidate

    def validate(self, scroll_id: str, version: str, min_trust_level: int = 1) -> bool:
        """Mark one registered scroll as reviewed for proposal generation."""

        key = f"{scroll_id}:{version}"
        if key not in self._definitions:
            return False
        for index, current in enumerate(self._versions.get(scroll_id, [])):
            if current.version == version:
                self._versions[scroll_id][index] = ScrollVersion(
                    scroll_id=current.scroll_id,
                    version=current.version,
                    status=ScrollStatus.VALIDATED,
                    checksum=current.checksum,
                    chain_compatibility=current.chain_compatibility,
                    min_trust_level=min_trust_level,
                    released_at=current.released_at,
                    metadata=current.metadata,
                )
                return True
        return False

    def deprecate(self, scroll_id: str, version: str) -> bool:
        """Deprecate one version without deleting its provenance."""

        for index, current in enumerate(self._versions.get(scroll_id, [])):
            if current.version == version:
                self._versions[scroll_id][index] = ScrollVersion(
                    scroll_id=current.scroll_id,
                    version=current.version,
                    status=ScrollStatus.DEPRECATED,
                    checksum=current.checksum,
                    chain_compatibility=current.chain_compatibility,
                    min_trust_level=current.min_trust_level,
                    released_at=current.released_at,
                    deprecated_at=utc_now_iso(),
                    metadata=current.metadata,
                )
                return True
        return False

    def propose(
        self,
        scroll_id: str,
        signal: str,
        context: Mapping[str, Any],
        version: str | None = None,
    ) -> ScrollProposal:
        """Convert one ruleset into a review proposal without executing it."""

        definition = self.get(scroll_id, version)
        if definition is None:
            raise KeyError(f"active scroll not found: {scroll_id}:{version or 'latest'}")
        step = {
            "scroll_id": definition.metadata.scroll_id,
            "version": definition.version,
            "checksum": definition.checksum,
            "rules": dict(definition.rules),
        }
        proposal_seed = {
            "scroll": f"{definition.metadata.scroll_id}:{definition.version}",
            "signal": signal,
            "context": dict(context),
            "step": step,
        }
        return ScrollProposal(
            proposal_id=f"scroll-proposal-{sha256_document(proposal_seed)[:24]}",
            scroll_refs=(
                {
                    "scroll_id": definition.metadata.scroll_id,
                    "version": definition.version,
                    "checksum": definition.checksum,
                },
            ),
            signal=signal,
            context=dict(context),
            proposed_steps=(step,),
        )

    def compose(self, composition_id: str, scroll_ids: Sequence[str]) -> "CompositeScroll":
        """Compose definitions into a pure proposal sequence."""

        definitions: list[ScrollDefinition] = []
        for scroll_id in scroll_ids:
            definition = self.get(scroll_id)
            if definition is None:
                raise KeyError(f"active scroll not found: {scroll_id}")
            definitions.append(definition)
        return CompositeScroll(composition_id, tuple(definitions))

    def list_by_type(self, scroll_type: ScrollType) -> list[ScrollMetadata]:
        seen: dict[str, ScrollMetadata] = {}
        for definition in self._definitions.values():
            if definition.metadata.scroll_type == scroll_type:
                seen[definition.metadata.scroll_id] = definition.metadata
        return sorted(seen.values(), key=lambda item: item.scroll_id)

    def list_by_chain(self, chain: str) -> list[ScrollMetadata]:
        compatible: dict[str, ScrollMetadata] = {}
        for scroll_id in self._versions:
            definition = self.get(scroll_id)
            if definition is not None and definition.is_compatible_with_chain(chain):
                compatible[scroll_id] = definition.metadata
        return sorted(compatible.values(), key=lambda item: item.scroll_id)


@dataclass(frozen=True)
class CompositeScroll:
    """Ordered declarative composition that emits one combined proposal."""

    composition_id: str
    scrolls: tuple[ScrollDefinition, ...]

    def __post_init__(self) -> None:
        if not self.composition_id.strip():
            raise ValueError("composition_id is required")
        if not self.scrolls:
            raise ValueError("a composite scroll requires at least one definition")

    def propose(self, signal: str, context: Mapping[str, Any]) -> ScrollProposal:
        steps = tuple(
            {
                "sequence": index,
                "scroll_id": definition.metadata.scroll_id,
                "version": definition.version,
                "checksum": definition.checksum,
                "rules": dict(definition.rules),
            }
            for index, definition in enumerate(self.scrolls, start=1)
        )
        refs = tuple(
            {
                "scroll_id": definition.metadata.scroll_id,
                "version": definition.version,
                "checksum": definition.checksum,
            }
            for definition in self.scrolls
        )
        seed = {
            "composition_id": self.composition_id,
            "signal": signal,
            "context": dict(context),
            "steps": list(steps),
        }
        return ScrollProposal(
            proposal_id=f"scroll-composite-{sha256_document(seed)[:24]}",
            scroll_refs=refs,
            signal=signal,
            context=dict(context),
            proposed_steps=steps,
        )
