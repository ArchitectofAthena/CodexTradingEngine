# QAOA Delta Phase 2E — Reproducible Benchmark Spine

## Purpose

Phase 2E turns the hybrid delta lane into a repeatable experimental instrument. A versioned seeded corpus reconstructs the same route and flash-liquidity QUBOs, compares each model against an exact classical baseline, sends selected geometry through the isolated Rust verifiers, calibrates adverse scenarios, evaluates robustness, and emits one canonical simulation receipt.

The benchmark is historical replay and research evidence. It does not discover markets, subscribe to feeds, borrow capital, sign transactions, submit RPC calls, schedule execution, or grant authority.

## Deterministic chain

```text
seeded benchmark case
→ canonical snapshot and corpus hashes
→ triangular-cycle enumeration
→ route QUBO
→ exact classical baseline distribution
→ confidence receipt bound to the identical QUBO hash
→ Rust exact route repricing
→ source-bound perturbation calibration
→ Rust-backed robustness evaluation
→ route/provider/amount-bucket expansion
→ flash-liquidity QUBO
→ exact classical baseline distribution
→ confidence receipt bound to the identical QUBO hash
→ Rust capacity and repayment verification
→ deterministic benchmark receipt
→ canonical artifact-only simulation-summary envelope
```

## Seeded corpus

`benchmarks/seeded_market_v0_1.json` contains:

- one deterministic market snapshot;
- route fee, slippage, latency, gas, and minimum-margin assumptions;
- source-hash-bound historical observations;
- explicit calibration policy and quantiles;
- modeled flash-liquidity providers and amount buckets;
- a minimum net-profit requirement;
- `authority: false` on every surface.

Array order is not identity. The loader canonicalizes edges, observations, providers, and buckets by stable identifiers before hashing or receipt construction.

The included values are synthetic teaching data. They are not a claim about future market behavior or a probability of execution.

## Identical-QUBO comparison

The exact classical baseline and the confidence receipt operate on the same `QuboModel` object. The receipt records the model SHA-256, exact energy, selected candidates, expected energy, and energy gap. Phase 2E independently recomputes and checks both the route and flash model hashes before allowing the benchmark receipt to exist.

The default seeded replay uses a one-hot exact distribution so identical environments produce byte-stable experimental evidence. The dedicated Qiskit CI lane separately constructs and samples those same seeded route and flash QUBOs locally, then checks their hashes and gaps against the exact baselines.

## Verification boundary

Python may construct and bind evidence. QAOA may sample a model. The exact solver may establish a baseline. Neither can prove that route arithmetic or repayment still matches the declared market state.

The complete seeded replay therefore invokes:

- `codex-delta-verifier` for route identity, costs, gas, profitability, and margin;
- `codex-flash-liquidity-verifier` for borrowed asset, capacity, provider fee, repayment, and minimum net profit.

Both subprocess membranes remain local, explicit, size-bounded, timeout-bounded, `shell=False`, and fail closed on drift.

## Receipt surfaces

`hybrid-delta-benchmark-receipt-v0.1` binds:

- benchmark corpus SHA-256;
- seeded snapshot SHA-256;
- route and flash QUBO hashes;
- identical-model verification flags;
- route confidence and exact Rust verification;
- calibration and robustness receipts;
- flash confidence and exact repayment evidence;
- historical-replay mode;
- human-promotion requirement;
- `authority: false`.

The deterministic receipt can then be wrapped by the repository’s canonical `receipt_emitter` as an allowed `simulation_summary` artifact. The envelope records the artifact path and SHA-256 and remains `artifact_only`.

## CLI

After building the two Rust binaries:

```bash
python -m eve_q.hybrid_benchmark \
  --case benchmarks/seeded_market_v0_1.json \
  --route-verifier rust/delta-verifier/target/debug/codex-delta-verifier \
  --flash-verifier rust/delta-verifier/target/debug/codex-flash-liquidity-verifier \
  --receipt-out artifacts/hybrid_benchmark_receipt.json \
  --envelope-out artifacts/hybrid_benchmark_envelope.json \
  --source-commit "$(git rev-parse HEAD)" \
  --root .
```

## CI gates

`Hybrid Benchmark CI` validates:

- Python 3.11 and 3.13 benchmark reconstruction;
- seeded corpus and schema syntax;
- canonical hashing independent of array order;
- authority-escalation rejection;
- identical-QUBO exact comparisons;
- local Qiskit sampling against both seeded QUBOs;
- complete replay through both compiled Rust binaries;
- deterministic repeated receipts;
- canonical simulation-summary envelope emission;
- uploaded receipt artifacts for human inspection.

## Design law

```text
A benchmark must be reconstructible.
A model comparison must use the identical QUBO.
A source hash binds evidence; it does not make evidence true.
Rust verifies arithmetic; it does not authorize action.
A receipt records the experiment; it does not command the system.
Human review remains the promotion gate.
```

## Boundaries

- no live market discovery;
- no feed subscription;
- no wallet or signer;
- no RPC submission;
- no flash borrowing;
- no mempool interaction;
- no scheduler authority;
- no autonomous capital movement;
- no benchmark result may self-promote;
- all benchmark cases, models, evidence, receipts, and envelopes remain non-authoritative.
