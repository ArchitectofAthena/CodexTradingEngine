import json

from eve_q.deployment_gates import (
    DeploymentTier,
    GraduationDecision,
    GraduationStateStore,
)


def decision(
    current_tier: DeploymentTier,
    requested_tier: DeploymentTier,
    *,
    human_approval_required: bool,
) -> GraduationDecision:
    return GraduationDecision(
        eligible=True,
        current_tier=current_tier,
        requested_tier=requested_tier,
        failures=(),
        human_approval_required=human_approval_required,
        authority=False,
    )


def test_testnet_promotion_does_not_require_fake_human_approver(tmp_path):
    path = tmp_path / "graduation-state.json"
    store = GraduationStateStore(path)

    store.record_decision(
        decision(
            DeploymentTier.LOCAL_SIMULATION,
            DeploymentTier.TESTNET,
            human_approval_required=False,
        ),
        approved_by=None,
    )

    state = store.load()
    assert state["current_tier"] == int(DeploymentTier.TESTNET)
    assert state["history"][-1]["promotion_recorded"] is True
    assert state["history"][-1]["approved_by"] is None


def test_real_funds_promotion_requires_nonblank_human_identity(tmp_path):
    path = tmp_path / "graduation-state.json"
    path.write_text(
        json.dumps({"current_tier": int(DeploymentTier.TESTNET), "history": []}),
        encoding="utf-8",
    )
    store = GraduationStateStore(path)
    promote = decision(
        DeploymentTier.TESTNET,
        DeploymentTier.LOW_COST_NETWORK,
        human_approval_required=True,
    )

    store.record_decision(promote, approved_by="   ")
    assert store.load()["current_tier"] == int(DeploymentTier.TESTNET)
    assert store.load()["history"][-1]["promotion_recorded"] is False

    store.record_decision(promote, approved_by="Architect")
    state = store.load()
    assert state["current_tier"] == int(DeploymentTier.LOW_COST_NETWORK)
    assert state["history"][-1]["promotion_recorded"] is True
    assert state["history"][-1]["approved_by"] == "Architect"


def test_stale_decision_cannot_overwrite_persisted_tier(tmp_path):
    path = tmp_path / "graduation-state.json"
    path.write_text(
        json.dumps(
            {
                "current_tier": int(DeploymentTier.LOW_COST_NETWORK),
                "history": [],
            }
        ),
        encoding="utf-8",
    )
    store = GraduationStateStore(path)

    store.record_decision(
        decision(
            DeploymentTier.TESTNET,
            DeploymentTier.LOW_COST_NETWORK,
            human_approval_required=True,
        ),
        approved_by="Architect",
    )

    state = store.load()
    assert state["current_tier"] == int(DeploymentTier.LOW_COST_NETWORK)
    assert state["history"][-1]["state_matches_decision"] is False
    assert state["history"][-1]["promotion_recorded"] is False
