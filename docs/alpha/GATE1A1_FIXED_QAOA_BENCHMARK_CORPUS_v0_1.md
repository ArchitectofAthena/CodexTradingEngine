# Gate 1A.1 Fixed Classical/QAOA Benchmark Corpus v0.1

## Purpose

Implement issue #145 Workstream B with one immutable, machine-checked comparison surface:

```text
same QUBO
+ same constraints
+ same economics-assumption digests
+ exact classical optimum
+ fixed QAOA backend, depth, optimizer, shots, and seeds
+ repeated-seed stability
+ verifier agreement
+ precommitted promotion thresholds
→ HOLD | QAOA_RESEARCH_ONLY | QAOA_ADDS_NO_MEASURABLE_VALUE | QAOA_CANDIDATE_FOR_FURTHER_TESTING
```

The corpus is research evidence only. It grants no proposal, wallet, signing, transaction, execution, Gate 1B, charity-transfer, or capital authority.

## Corpus

Canonical input:

```text
benchmarks/gate1a1_fixed_benchmark_corpus_v0_1.json
```

Expected report:

```text
benchmarks/gate1a1_fixed_benchmark_expected_report_v0_1.json
```

The v0.1 corpus contains three bounded QUBO cases:

1. one route from three candidates;
2. one source and one sink under exact-one constraints;
3. a route pair that must preserve an explicit safety variable.

Every case binds six independent assumption digests covering fees, gas, latency, slippage, liquidity, and failure posture. A QAOA run cannot silently change any of those assumptions because the complete QUBO payload is content-addressed.

## Classical truth

The validator reconstructs every binary assignment, applies the declared constraints, evaluates the immutable QUBO, and selects the deterministic exact optimum. The stored classical baseline must match both the optimum objective and lexicographic tie-break assignment.

```text
claimed classical answer
→ exact enumeration replay
→ objective and feasibility check
→ PASS or HOLD
```

## QAOA pairing

Each QAOA record declares:

- sampler;
- backend and version;
- depth;
- optimizer and version;
- shots;
- the exact shared QUBO SHA-256;
- at least three unique seeds;
- assignment, objective, feasibility, runtime, resources, verifier result, and run digest for every seed.

The current fixtures use a deterministic local precomputed-statevector evidence lane. They are not hardware advantage claims.

## Precommitted policy

```yaml
same_qubo_hash_required: true
feasibility_not_worse: true
objective_tolerance: 1.0e-12
candidate_min_runtime_improvement_fraction: 0.20
candidate_max_resource_ratio: 1.0
repeated_seed_stability_required: true
minimum_seed_count: 3
maximum_objective_spread: 1.0e-12
verifier_agreement_required: true
human_review_required: true
```

A result cannot be promoted by narrative interpretation. The policy is part of the corpus identity.

## Current honest result

All three QAOA fixture lanes reproduce the exact classical solution, but use materially more recorded runtime and resource units. Therefore the deterministic v0.1 result is:

```text
QAOA_ADDS_NO_MEASURABLE_VALUE
```

This result is useful. It prevents novelty, prestige, or quantum branding from outranking measured value.

At the Gate 1A.1 decision layer, this remains compatible with `QAOA_RESEARCH_ONLY`. It does not loosen any gate.

## Refusal posture

The validator forces `HOLD` for:

- QUBO digest drift;
- changed constraints or economics assumptions;
- non-optimal or infeasible classical baseline;
- QAOA/classical QUBO mismatch;
- altered or unverified run evidence;
- duplicate seeds or insufficient seed coverage;
- feasibility regression;
- unstable repeated-seed objectives;
- authority drift;
- expected-outcome repainting.

## Operator command

```bash
codex-gate1a1-benchmark \
  benchmarks/gate1a1_fixed_benchmark_corpus_v0_1.json \
  --summary \
  --output artifacts/gate1a1/benchmark-report.json
```

Expected summary:

```text
GATE1A1_BENCHMARK=QAOA_ADDS_NO_MEASURABLE_VALUE
CASES=3
HOLDS=0
AUTHORITY=false
GATE1B_ACTIVATED=false
HUMAN_PROMOTION_REQUIRED=true
```

## Boundary

```yaml
artifact_is_command: false
authority: false
automatic_gate_promotion: false
gate1b_activated: false
may_execute: false
may_sign: false
may_submit_transaction: false
may_access_wallet: false
may_move_capital: false
human_promotion_required: true
```

> Exact pairing before interpretation. Measured value before prestige. Human review before promotion.
