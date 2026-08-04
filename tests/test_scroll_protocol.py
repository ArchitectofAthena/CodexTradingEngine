from __future__ import annotations

import pytest

from eve_q.scroll_protocol import (
    ScrollDefinition,
    ScrollMetadata,
    ScrollRegistry,
    ScrollStatus,
    ScrollType,
)


def definition(scroll_id: str, version: str = "1.0.0") -> ScrollDefinition:
    return ScrollDefinition(
        metadata=ScrollMetadata(
            scroll_id=scroll_id,
            name=f"{scroll_id} research",
            description="A declarative simulation-only scoring ruleset.",
            scroll_type=ScrollType.ARBITRAGE,
            author="ArchitectofAthena",
            tags=("simulation", "proposal-only"),
            risk_level="medium",
        ),
        version=version,
        rules={
            "inputs": ["market_snapshot"],
            "filters": {"min_liquidity_usd": "100000"},
            "scoring": {"objective": "expected_profit_minus_costs"},
            "constraints": ["authority_false", "human_promotion_required"],
            "outputs": ["simulation_summary"],
        },
        chain_compatibility=("base",),
    )


def test_registry_rejects_classes_and_callables():
    registry = ScrollRegistry()

    class ArbitraryImplementation:
        pass

    with pytest.raises(TypeError, match="ScrollDefinition only"):
        registry.register(ArbitraryImplementation)  # type: ignore[arg-type]


def test_definition_rejects_callable_and_execution_keys():
    metadata = definition("safe-scroll").metadata

    with pytest.raises(TypeError, match="callables"):
        ScrollDefinition(
            metadata=metadata,
            version="1.0.0",
            rules={"scoring": {"function": lambda value: value}},
        )

    with pytest.raises(ValueError, match="forbidden capability key"):
        ScrollDefinition(
            metadata=metadata,
            version="1.0.0",
            rules={"constraints": {"execute": True}},
        )


def test_registered_scroll_emits_non_authoritative_proposal():
    registry = ScrollRegistry()
    receipt = registry.register(definition("base-triangle"))
    assert receipt.status is ScrollStatus.DRAFT
    assert registry.validate("base-triangle", "1.0.0") is True

    proposal = registry.propose(
        "base-triangle",
        signal="ETH/USDC observation",
        context={"snapshot_sha256": "a" * 64},
    ).to_dict()

    assert proposal["artifact_type"] == "ScrollProposal"
    assert proposal["authority"] is False
    assert proposal["human_promotion_required"] is True
    assert proposal["may_execute"] is False
    assert proposal["may_sign"] is False
    assert proposal["may_broadcast"] is False
    assert proposal["may_move_capital"] is False
    assert len(proposal["artifact_sha256"]) == 64


def test_composite_scroll_is_pure_proposal_composition():
    registry = ScrollRegistry()
    registry.register(definition("route-filter"))
    registry.register(definition("risk-score"))

    proposal = registry.compose(
        "route-plus-risk",
        ["route-filter", "risk-score"],
    ).propose("snapshot", {"source": "fixture"}).to_dict()

    assert [step["sequence"] for step in proposal["proposed_steps"]] == [1, 2]
    assert [ref["scroll_id"] for ref in proposal["scroll_refs"]] == [
        "route-filter",
        "risk-score",
    ]
    assert proposal["may_execute"] is False


def test_latest_version_uses_numeric_semver_ordering():
    registry = ScrollRegistry()
    registry.register(definition("versioned", "1.9.0"))
    registry.register(definition("versioned", "1.10.0"))

    latest = registry.get("versioned")

    assert latest is not None
    assert latest.version == "1.10.0"


def test_deprecated_definition_is_not_selected():
    registry = ScrollRegistry()
    registry.register(definition("lifecycle", "1.0.0"))
    assert registry.deprecate("lifecycle", "1.0.0") is True

    assert registry.get("lifecycle") is None
    with pytest.raises(KeyError):
        registry.propose("lifecycle", "signal", {})


def test_duplicate_version_is_rejected():
    registry = ScrollRegistry()
    registry.register(definition("duplicate"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition("duplicate"))
