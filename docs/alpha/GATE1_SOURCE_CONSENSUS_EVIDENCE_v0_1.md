# CodexTradingEngine Gate 1 Source Consensus Evidence v0.1

## Purpose

This evaluator tests how Gate 1 handles multiple observations without making any network request.

It separates:

- numerical agreement;
- provenance independence;
- source-review eligibility;
- review expiry;
- observation freshness;
- units and decimal conventions;
- authority.

Agreement alone is not corroboration. Disagreement is not averaged away. Freshness cannot be borrowed. Unknown units stop comparison.

## Command

```bash
codex-gate1-consensus evaluate \
  --packet examples/alpha/source_consensus_independent_agreement_v0_1.json \
  --output-dir artifacts/source-consensus-example
```

Outputs:

```text
artifacts/source-consensus-example/source-consensus-decision.json
artifacts/source-consensus-example/source-consensus-summary.txt
```

Verify an existing decision:

```bash
codex-gate1-consensus verify \
  --decision artifacts/source-consensus-example/source-consensus-decision.json
```

## Decision classes

### `HOLD_CONFLICT`

Two or more admissible observations differ by more than the declared absolute tolerance.

The evaluator records minimum, maximum, and conflict magnitude. It does not calculate an average or selected value.

### `HOLD_CONCENTRATION`

Observations agree within tolerance but two or more share the same provenance group.

Agreement may still be real, but it is not independent corroboration. Mirrored APIs, reseller surfaces, shared node fleets, or one provider exposed through multiple hostnames remain one lineage unless reviewed evidence shows otherwise.

### `HOLD_STALE`

At least one observation has expired at evaluation time.

A fresh observation cannot refresh another source by association.

### `HOLD_UNIT_AMBIGUITY`

At least one observation has unknown decimals, an unknown unit, incompatible comparison units, an invalid conversion, or an identity conversion that silently changes units.

The evaluator allows only explicit identity or decimal-scale conversions.

### `HOLD_SOURCE_REVIEW`

At least one source is missing a review, has `HOLD` or `REJECT` status, or lacks a review expiry.

Historical availability does not constitute review.

### `HOLD_REVIEW_EXPIRED`

At least one source review expired at or before evaluation time.

Continued source availability does not extend eligibility.

### `ACCEPT_OBSERVATION_ONLY`

All observations are:

- reviewed and currently eligible;
- fresh;
- unit-compatible through explicit deterministic conversions;
- within declared tolerance;
- from distinct provenance groups.

Acceptance remains observation-only. It does not choose a trade value, create a proposal, promote a gate, or authorize action.

## Determinism

The receipt is computed over canonical evidence after observations are sorted by source ID.

Therefore:

- identical packets reproduce the same receipt;
- reversing source order does not change the decision or receipt;
- reasons and unresolved questions are stored in deterministic order;
- no runtime timestamp is invented.

## No aggregation contract

Every decision contains:

```text
aggregate_value: null
aggregation_performed: false
```

This remains true even for independent agreement. The evaluator describes an observation interval and conflict magnitude, not a synthetic quote.

## Input contract

Each observation records:

- source ID;
- registry SHA-256;
- provenance group;
- operator;
- original value and unit;
- decimal convention;
- explicit conversion;
- comparison unit;
- observed and expiry times;
- review status and review expiry;
- `authority: false`.

The packet also records one evaluation time, one comparison unit, one absolute tolerance, and unresolved questions.

## Output boundary

Every decision fixes these counts at zero:

```text
live proposals generated: 0
signatures created: 0
transactions submitted: 0
executions performed: 0
capital movements: 0
```

Every authority field remains false. Gate 1B, Gate 2, Gate 3, and Gates 4 through 6 remain locked.

## Relationship to the Sepolia soak

The 25-capture Sepolia campaign proved that one reviewed source preserved transport and replay boundaries across a fixed-count run.

This offline evaluator addresses a different question: whether apparent multi-source confidence can survive scrutiny of lineage, freshness, review state, and units.

No second live source is selected or contacted by this slice.

> A chorus is not independent merely because it has two microphones.
