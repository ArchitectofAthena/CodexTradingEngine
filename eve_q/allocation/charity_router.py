"""Charity allocation router with portfolio diversity safeguards.

The router proposes allocation weights only. It does not release funds,
execute transfers, sign transactions, touch wallets, or authorize capital movement.

Core law:
Verified impact bends the gradient.
It does not own the gradient.
No single charity may become the whole definition of good.
"""

from __future__ import annotations

from dataclasses import dataclass

from eve_q.allocation.geodesic_policy import score_allocation

EPSILON = 1e-12


@dataclass(frozen=True)
class AllocationDiversityPolicy:
    """Policy envelope for graceful allocation degradation.

    The policy does not punish a high-impact charity. It caps concentration,
    reserves exploration budget, and routes concentrated proposals toward
    human review instead of allowing a monoculture.
    """

    max_single_charity_weight: float = 0.45
    exploration_budget: float = 0.10
    concentration_review_threshold: float = 0.40


DEFAULT_POLICY = AllocationDiversityPolicy()


def _validate_policy(policy: AllocationDiversityPolicy) -> None:
    if not 0.0 <= policy.max_single_charity_weight <= 1.0:
        raise ValueError("max_single_charity_weight must be between 0 and 1")
    if not 0.0 <= policy.exploration_budget <= 1.0:
        raise ValueError("exploration_budget must be between 0 and 1")
    if not 0.0 <= policy.concentration_review_threshold <= 1.0:
        raise ValueError("concentration_review_threshold must be between 0 and 1")


def _safe_weight(decision: dict) -> float:
    return max(0.0, float(decision.get("recommended_weight", 0.0)))


def _raw_normalized_weights(decisions: list[dict]) -> list[float]:
    weights = [_safe_weight(decision) for decision in decisions]
    total = sum(weights)
    if total <= EPSILON:
        return [0.0 for _ in weights]
    return [weight / total for weight in weights]


def _capped_guarded_weights(
    normalized_weights: list[float],
    policy: AllocationDiversityPolicy,
) -> tuple[list[float], float]:
    """Apply graceful concentration cap and reserve exploration budget.

    Returns:
      guarded weights assigned to current candidates
      unallocated residual caused by caps
    """

    allocation_pool = max(0.0, 1.0 - policy.exploration_budget)
    base_weights = [weight * allocation_pool for weight in normalized_weights]
    guarded = [min(weight, policy.max_single_charity_weight) for weight in base_weights]

    leftover = allocation_pool - sum(guarded)

    while leftover > EPSILON:
        eligible = [
            index
            for index, weight in enumerate(guarded)
            if weight < policy.max_single_charity_weight - EPSILON and base_weights[index] > EPSILON
        ]
        if not eligible:
            break

        eligible_base_total = sum(base_weights[index] for index in eligible)
        if eligible_base_total <= EPSILON:
            break

        previous_leftover = leftover

        for index in eligible:
            share = base_weights[index] / eligible_base_total
            proposed = guarded[index] + previous_leftover * share
            guarded[index] = min(proposed, policy.max_single_charity_weight)

        leftover = allocation_pool - sum(guarded)
        if abs(previous_leftover - leftover) <= EPSILON:
            break

    return guarded, max(0.0, leftover)


def _add_review_reason(decision: dict, reason: str) -> None:
    reasons = decision.setdefault("human_review_reasons", [])
    if reason not in reasons:
        reasons.append(reason)
    decision["requires_human_review"] = True


def propose_allocations(
    signals,
    policy: AllocationDiversityPolicy = DEFAULT_POLICY,
):
    """Return ranked allocation proposals with graceful degradation metadata.

    This function proposes weights only. It keeps transfer posture held and
    review-first. Concentration is degraded gracefully by capping recommended
    weights and reserving exploration budget instead of hard-stopping the
    entire allocation process.
    """

    _validate_policy(policy)

    decisions = [score_allocation(signal).to_dict() for signal in signals]
    normalized_weights = _raw_normalized_weights(decisions)
    guarded_weights, unallocated_due_to_caps = _capped_guarded_weights(
        normalized_weights,
        policy,
    )

    allocation_pool = max(0.0, 1.0 - policy.exploration_budget)

    for decision, normalized, guarded in zip(
        decisions,
        normalized_weights,
        guarded_weights,
        strict=True,
    ):
        decision["normalized_recommended_weight"] = normalized
        decision["guarded_recommended_weight"] = guarded
        decision["reserved_exploration_weight"] = policy.exploration_budget
        decision["portfolio_guard"] = {
            "max_single_charity_weight": policy.max_single_charity_weight,
            "exploration_budget_reserved": policy.exploration_budget,
            "allocation_pool": allocation_pool,
            "unallocated_due_to_caps": unallocated_due_to_caps,
            "human_review_required_for_promotion": True,
        }

        # Proposals remain review-first. This router never authorizes transfer.
        decision["hold_transfer"] = True

        if normalized >= policy.concentration_review_threshold:
            _add_review_reason(decision, "concentration_review_required")

        if guarded + EPSILON < normalized * allocation_pool:
            _add_review_reason(decision, "single_charity_cap_applied")

    return sorted(
        decisions,
        key=lambda decision: decision.get("allocation_priority", 0.0),
        reverse=True,
    )
