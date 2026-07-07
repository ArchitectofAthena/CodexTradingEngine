"""Scroll Protocol registry and versioning system.

Scrolls are Codex-bound trading strategies stored as executable modules or JSON rulesets.
This module provides registration, versioning, validation, and composition for scrolls.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ScrollStatus(str, Enum):
    """Status of a scroll."""
    DRAFT = "draft"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ScrollType(str, Enum):
    """Type of scroll."""
    ARBITRAGE = "arbitrage"
    LIQUIDATION = "liquidation"
    YIELD_FARMING = "yield_farming"
    SWARM_DETECTION = "swarm_detection"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ScrollVersion:
    """A versioned scroll release.
    
    Attributes:
        scroll_id: Unique scroll identifier.
        version: Semantic version (e.g., "1.0.0").
        status: Current status of the scroll.
        checksum: SHA256 checksum of scroll code.
        chain_compatibility: List of compatible chains.
        min_trust_level: Minimum trust level required to execute.
        released_at: Release timestamp.
        deprecated_at: Deprecation timestamp if applicable.
        metadata: Additional metadata.
    """
    scroll_id: str
    version: str
    status: ScrollStatus
    checksum: str
    chain_compatibility: List[str] = field(default_factory=list)
    min_trust_level: int = 1
    released_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deprecated_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_compatible_with_chain(self, chain: str) -> bool:
        """Check if scroll is compatible with a chain.
        
        Args:
            chain: Chain name.
            
        Returns:
            True if compatible.
        """
        return chain in self.chain_compatibility or "*" in self.chain_compatibility

    def is_active(self) -> bool:
        """Check if scroll is active (not deprecated or archived).
        
        Returns:
            True if active.
        """
        return self.status in (ScrollStatus.DRAFT, ScrollStatus.VALIDATED)


@dataclass(frozen=True)
class ScrollMetadata:
    """Metadata for a scroll.
    
    Attributes:
        scroll_id: Unique scroll identifier.
        name: Human-readable name.
        description: Description of what the scroll does.
        scroll_type: Type of scroll.
        author: Author identifier.
        tags: List of tags for categorization.
        risk_level: Risk level (low, medium, high).
    """
    scroll_id: str
    name: str
    description: str
    scroll_type: ScrollType
    author: str
    tags: List[str] = field(default_factory=list)
    risk_level: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scroll_id": self.scroll_id,
            "name": self.name,
            "description": self.description,
            "scroll_type": self.scroll_type.value,
            "author": self.author,
            "tags": self.tags,
            "risk_level": self.risk_level,
        }


class Scroll(ABC):
    """Abstract base class for scrolls.
    
    A scroll represents a trading strategy or bot swarm detection protocol.
    """

    def __init__(
        self,
        scroll_id: str,
        metadata: ScrollMetadata,
        version: str = "1.0.0",
    ) -> None:
        """Initialize a scroll.
        
        Args:
            scroll_id: Unique scroll identifier.
            metadata: Scroll metadata.
            version: Semantic version.
        """
        self.scroll_id = scroll_id
        self.metadata = metadata
        self.version = version
        self.created_at = datetime.now(timezone.utc).isoformat()

    @abstractmethod
    async def execute(
        self,
        signal: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute the scroll strategy.
        
        Args:
            signal: Trading signal or trigger.
            context: Execution context with market data, account state, etc.
            
        Returns:
            Execution result with trades, decisions, or signals.
        """
        pass

    def get_code_hash(self) -> str:
        """Get SHA256 hash of scroll code.
        
        Returns:
            Hexadecimal hash string.
        """
        code = self.__class__.__module__ + self.__class__.__name__
        return hashlib.sha256(code.encode()).hexdigest()


class ScrollRegistry:
    """Registry for managing scrolls and versions.
    
    Example:
        >>> registry = ScrollRegistry()
        >>> registry.register(scroll_metadata, scroll_class)
        >>> scroll = registry.get("scroll-arbitrage-v1", "1.0.0")
        >>> result = await scroll.execute("ETH", context)
    """

    def __init__(self) -> None:
        """Initialize scroll registry."""
        self.scrolls: Dict[str, ScrollMetadata] = {}
        self.versions: Dict[str, List[ScrollVersion]] = {}
        self.implementations: Dict[str, Scroll] = {}

    def register(
        self,
        metadata: ScrollMetadata,
        implementation: type,
        version: str = "1.0.0",
        chain_compatibility: Optional[List[str]] = None,
    ) -> ScrollVersion:
        """Register a new scroll.
        
        Args:
            metadata: Scroll metadata.
            implementation: Scroll implementation class.
            version: Semantic version.
            chain_compatibility: List of compatible chains.
            
        Returns:
            ScrollVersion for the registered scroll.
        """
        scroll_id = metadata.scroll_id
        key = f"{scroll_id}:{version}"

        # Instantiate to get code hash
        instance = implementation(scroll_id, metadata, version)
        checksum = instance.get_code_hash()

        scroll_version = ScrollVersion(
            scroll_id=scroll_id,
            version=version,
            status=ScrollStatus.DRAFT,
            checksum=checksum,
            chain_compatibility=chain_compatibility or ["*"],
            metadata=metadata.to_dict(),
        )

        self.scrolls[scroll_id] = metadata
        if scroll_id not in self.versions:
            self.versions[scroll_id] = []
        self.versions[scroll_id].append(scroll_version)
        self.implementations[key] = instance

        return scroll_version

    def get(
        self,
        scroll_id: str,
        version: Optional[str] = None,
    ) -> Optional[Scroll]:
        """Retrieve a scroll by ID and version.
        
        Args:
            scroll_id: Scroll identifier.
            version: Semantic version (latest if not specified).
            
        Returns:
            Scroll instance or None if not found.
        """
        if scroll_id not in self.versions:
            return None

        if version is None:
            # Get latest active version
            versions = [
                v for v in self.versions[scroll_id]
                if v.is_active()
            ]
            if not versions:
                return None
            version = max(versions, key=lambda v: v.version).version

        key = f"{scroll_id}:{version}"
        return self.implementations.get(key)

    def validate(
        self,
        scroll_id: str,
        version: str,
        min_trust_level: int = 1,
    ) -> bool:
        """Validate and mark a scroll as validated.
        
        Args:
            scroll_id: Scroll identifier.
            version: Semantic version.
            min_trust_level: Minimum required trust level.
            
        Returns:
            True if validation successful.
        """
        key = f"{scroll_id}:{version}"
        if key not in self.implementations:
            return False

        # Update version status
        for idx, v in enumerate(self.versions.get(scroll_id, [])):
            if v.version == version:
                self.versions[scroll_id][idx] = ScrollVersion(
                    scroll_id=v.scroll_id,
                    version=v.version,
                    status=ScrollStatus.VALIDATED,
                    checksum=v.checksum,
                    chain_compatibility=v.chain_compatibility,
                    min_trust_level=min_trust_level,
                    released_at=v.released_at,
                    metadata=v.metadata,
                )
                return True

        return False

    def deprecate(self, scroll_id: str, version: str) -> bool:
        """Deprecate a scroll version.
        
        Args:
            scroll_id: Scroll identifier.
            version: Semantic version.
            
        Returns:
            True if deprecation successful.
        """
        for idx, v in enumerate(self.versions.get(scroll_id, [])):
            if v.version == version:
                self.versions[scroll_id][idx] = ScrollVersion(
                    scroll_id=v.scroll_id,
                    version=v.version,
                    status=ScrollStatus.DEPRECATED,
                    checksum=v.checksum,
                    chain_compatibility=v.chain_compatibility,
                    min_trust_level=v.min_trust_level,
                    released_at=v.released_at,
                    deprecated_at=datetime.now(timezone.utc).isoformat(),
                    metadata=v.metadata,
                )
                return True

        return False

    def compose(
        self,
        composition_id: str,
        scroll_ids: List[str],
    ) -> Optional[CompositeScroll]:
        """Create a composite scroll from multiple scrolls.
        
        Args:
            composition_id: Unique composition identifier.
            scroll_ids: List of scroll IDs to compose.
            
        Returns:
            CompositeScroll or None if any scroll not found.
        """
        scrolls: List[Scroll] = []
        for scroll_id in scroll_ids:
            scroll = self.get(scroll_id)
            if scroll is None:
                return None
            scrolls.append(scroll)

        return CompositeScroll(
            composition_id=composition_id,
            scrolls=scrolls,
        )

    def list_by_type(self, scroll_type: ScrollType) -> List[ScrollMetadata]:
        """List all scrolls of a given type.
        
        Args:
            scroll_type: Type of scroll to filter.
            
        Returns:
            List of matching scroll metadata.
        """
        return [
            m for m in self.scrolls.values()
            if m.scroll_type == scroll_type
        ]

    def list_by_chain(self, chain: str) -> List[ScrollMetadata]:
        """List all scrolls compatible with a chain.
        
        Args:
            chain: Chain name.
            
        Returns:
            List of compatible scroll metadata.
        """
        compatible = []
        for scroll_id, versions in self.versions.items():
            for v in versions:
                if v.is_compatible_with_chain(chain) and v.is_active():
                    if self.scrolls.get(scroll_id):
                        compatible.append(self.scrolls[scroll_id])
                    break
        return compatible


class CompositeScroll(Scroll):
    """Composite scroll that chains multiple scrolls.
    
    Example:
        >>> scrolls = [scroll1, scroll2, scroll3]
        >>> composite = CompositeScroll("composite-1", scrolls)
        >>> result = await composite.execute(signal, context)
    """

    def __init__(
        self,
        composition_id: str,
        scrolls: List[Scroll],
    ) -> None:
        """Initialize composite scroll.
        
        Args:
            composition_id: Unique composition identifier.
            scrolls: List of scrolls to compose.
        """
        self.composition_id = composition_id
        self.scrolls = scrolls
        metadata = ScrollMetadata(
            scroll_id=composition_id,
            name=f"Composite[{len(scrolls)}]",
            description=f"Composition of {len(scrolls)} scrolls",
            scroll_type=ScrollType.CUSTOM,
            author="composite",
        )
        super().__init__(composition_id, metadata, "1.0.0")

    async def execute(
        self,
        signal: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute all scrolls in sequence.
        
        Args:
            signal: Trading signal.
            context: Execution context.
            
        Returns:
            Aggregated results from all scrolls.
        """
        results: Dict[str, Any] = {
            "composition_id": self.composition_id,
            "steps": [],
        }

        current_context = context.copy()
        for i, scroll in enumerate(self.scrolls):
            result = await scroll.execute(signal, current_context)
            results["steps"].append({
                "scroll_id": scroll.scroll_id,
                "version": scroll.version,
                "result": result,
            })
            # Update context with results for next scroll
            current_context["previous_result"] = result

        return results
