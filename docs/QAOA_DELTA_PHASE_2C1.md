# QAOA Delta Phase 2C-1 — Perturbed-State Robustness

## Purpose

A profitable point estimate is not yet a durable opportunity. Phase 2C-1 subjects one QAOA-selected, Rust-verified triangular candidate to a bounded family of alternate market states and records whether the verified margin survives.

```text
QAOA candidate
→ exact Rust repricing
→ deterministic perturbation family
→ exact Rust repricing per state
→ robustness receipt
→ human review
```

## Perturbation surface

Each scenario may alter, in candidate edge order:

- quoted-rate basis points, representing reserve or price movement;
- fee basis points;
- slippage basis points;
- latency-penalty basis points;
- gas log penalty.

Scenarios are sorted by stable identifier and limited to 256 states. Duplicate scenario identities are rejected. Every alternate state receives a derived SHA-256 snapshot identity binding the baseline snapshot, scenario parameters, perturbed edge values, candidate identity, and gas assumption.

## Evidence

A `delta-robustness-receipt-v0.1` records:

- baseline snapshot hash;
- QUBO model hash;
- QAOA confidence-receipt identity;
- candidate identity;
- scenario-set hash;
- scenario and survival counts;
- survival rate;
- worst-case and median verified log delta;
- margin-failure reason counts;
- deterministic robustness class;
- every scenario-specific Rust request and result;
- `authority: false` at every layer.

## Classification

| Survival rate | Class |
| --- | --- |
| 1.0 | `robust` |
| at least 0.8 | `resilient` |
| at least 0.5 | `conditional` |
| greater than 0 | `fragile` |
| 0 | `failed` |

These labels summarize a declared scenario family. They do not imply calibrated market probabilities.

## Standard teaching scenarios

The repository includes deterministic baseline, reserve, slippage, latency, gas, and combined-adverse scenarios. Their values are examples for testing the architecture, not claims about realistic market distributions.

Production research must source perturbation magnitudes from measured volatility, liquidity depth, quote age, gas distributions, and venue behavior, with provenance recorded separately.

## Fail-closed rules

The robustness lane rejects:

- malformed or duplicate scenarios;
- non-finite perturbations;
- cost assumptions at or above 10,000 basis points;
- missing candidate edges;
- missing or relative Rust executable paths;
- subprocess timeout, crash, or malformed output;
- candidate, snapshot, model, or receipt identity drift;
- any authority escalation.

## Boundary

This phase performs no wallet signing, transaction construction, RPC submission, borrowing, scheduling, mempool mutation, or capital movement.

```text
A route that survives perturbation earns stronger evidence.
Stronger evidence still does not become authority.
Human promotion remains sovereign.
```
