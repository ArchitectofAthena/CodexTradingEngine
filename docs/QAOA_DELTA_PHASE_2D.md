# QAOA Delta Phase 2D — Market-Derived Perturbation Calibration

## Purpose

Phase 2C-1 proved that a selected triangular candidate can be re-priced across deterministic alternate market states. Phase 2D replaces hand-authored teaching magnitudes with deterministic, source-bound perturbation scenarios derived from historical observations supplied to the engine.

This remains an offline research surface. It does not discover providers, query venues, subscribe to feeds, sign transactions, borrow capital, schedule work, or submit RPC calls.

## Input contract

Each historical observation contains:

- a stable `market-observation:*` identity;
- a non-empty observation time label;
- exactly three edge observations with stable edge identities;
- quoted rate, fee, slippage, and latency assumptions for each edge;
- a gas-log penalty;
- a source SHA-256 binding the observation to its upstream artifact;
- `authority: false`.

The calibrator aligns observations by edge identity rather than tuple position. Candidate rotation, venue naming, and source ordering therefore cannot silently remap the route.

## Calibration method

For each route edge, the engine derives empirical adverse series relative to the declared baseline:

```text
rate adverse magnitude = max(0, -(observed_rate / baseline_rate - 1) * 10_000)
fee increase           = max(0, observed_fee - baseline_fee)
slippage increase      = max(0, observed_slippage - baseline_slippage)
latency increase       = max(0, observed_latency - baseline_latency)
gas increase           = max(0, observed_gas_log - baseline_gas_log)
```

A deterministic linear quantile is then computed for each declared policy quantile. Rate magnitudes are returned as negative shifts. Cost and gas increases remain non-negative.

The default policy emits:

- a zero-shift calibrated baseline;
- empirical 50th-percentile adverse state;
- empirical 80th-percentile adverse state;
- empirical 95th-percentile adverse state.

All outputs are clipped to explicit scenario-contract bounds. Every clip is counted in the receipt.

## Receipt

The calibration receipt binds:

- baseline snapshot SHA-256;
- triangular candidate identity;
- sorted observation identities;
- complete source-bound dataset digest;
- calibration-policy digest;
- generated scenario-set digest;
- observation count;
- clip counters;
- `authority: false`.

The generated `PerturbationScenario` objects can be passed directly into the Phase 2C-1 Rust-backed robustness evaluator.

## Interpretation boundary

The scenarios describe empirical stress magnitudes present in the supplied observation corpus. They are not guaranteed probabilities, forecasts, confidence intervals, or claims about future market behavior.

A small, biased, stale, synthetic, or incomplete corpus produces correspondingly limited evidence. The receipt preserves lineage so those limitations can be audited instead of hidden.

## Design law

```text
History may calibrate pressure.
History may not promise recurrence.
Source hashes bind the evidence.
Quantiles describe the supplied corpus.
Clipping must be visible.
Calibration cannot grant authority.
Rust still verifies every perturbed route.
Human review remains the promotion gate.
```

## Deferred work

- ingestion adapters for independently archived venue snapshots;
- corpus quality and staleness scoring;
- regime segmentation;
- rolling-window comparison receipts;
- benchmark corpus generation;
- canonical simulation-receipt emission;
- fork and testnet shadow observation.
