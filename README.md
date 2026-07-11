# CodexTradingEngine

**Simulation-first crypto telemetry, planning, verification, charity-allocation, and artifact-receipt research for Termux/Python.**

CodexTradingEngine is the market-facing metabolic organ in the wider SpiralBloom architecture. It observes bounded inputs, constructs reviewable proposals, tests them against independent verifiers and policy membranes, and emits evidence artifacts.

It does **not** autonomously move capital.

## Constitutional Posture

```text
Agent proposes.
Artifact records.
Verifier gates.
Registry remembers.
Human promotes.
```

```text
Telemetry before autonomy.
Policy before runtime.
Membrane before motion.
```

The repository is intentionally:

- proposal-only by default;
- simulation-first;
- artifact- and receipt-driven;
- human-gated before any real-world capital touchpoint;
- explicit about uncertainty, provenance, and model boundaries;
- unable to convert evidence into authority by itself.

Artifacts are records, not commands. Metadata is a pointer, not authority. A successful model, verifier result, hash match, or receipt cannot promote itself.

## What the Engine Does

CodexTradingEngine may:

- ingest bounded telemetry and historical-replay inputs;
- construct market graphs and triangular-cycle candidates;
- build route and route-plus-liquidity QUBOs;
- run bounded local Qiskit statevector experiments;
- compare QAOA evidence against exact classical solutions on the identical QUBO;
- call isolated local Rust verifiers with strict subprocess contracts;
- calibrate deterministic adverse scenarios from source-bound observations;
- score perturbed-state robustness;
- model flash-liquidity provider and amount-bucket geometry;
- verify capacity, repayment, and minimum-profit arithmetic without borrowing;
- rank charity-allocation proposals from impact, need, urgency, confidence, and provenance signals;
- apply anti-monoculture portfolio safeguards;
- emit canonical simulation summaries, risk reports, and artifact receipts.

These outputs remain review artifacts with `authority: false`.

## What the Engine Must Not Do

CodexTradingEngine must not perform:

- wallet or transaction signing;
- autonomous capital movement;
- flash-loan execution;
- RPC submission;
- mempool mutation or interaction;
- scheduler- or webhook-triggered execution;
- governance mutation;
- silent remote command execution;
- receipt mutation after emission;
- self-promotion from simulation or evidence into execution authority.

## Local Constitutional Membrane

The machine-readable organ contract defines the repository's legal surface:

- `contracts/organ_contract.json` — allowed outputs, forbidden capabilities, allowed modes, promotion path, and hard invariants;
- `eve_q/organ_contract.py` — validates emitted records against that contract;
- `contracts/ttl_policy.json` and `eve_q/ttl_policy.py` — evaluate time-bounded posture and graceful degradation;
- `eve_q/receipt_emitter.py` — emits artifact-only receipts compatible with the wider SpiralBloom receipt lane.

The promotion path is:

```text
simulate
→ validate
→ emit receipt
→ ingest receipt
→ verify
→ human review
→ human promotion
```

No earlier stage implies the next.

## Charity Geodesic

The charity lane treats profit as throughput rather than destination. Verified positive impact may curve the recommendation landscape, but it never becomes execution authority.

```text
Verified impact bends the gradient.
It does not own the gradient.
No single charity may become the whole definition of good.
```

`eve_q/allocation/geodesic_policy.py` scores allocation proposals using bounded signals including:

- impact;
- need;
- urgency;
- neglect;
- funding gap;
- absorptive capacity;
- confidence;
- telemetry-source reliability;
- provenance.

Every decision keeps `hold_transfer: true`. Missing provenance, low confidence, low source reliability, or limited absorptive capacity raises review flags instead of authorizing a transfer.

`eve_q/allocation/charity_router.py` adds the anti-monoculture portfolio guard:

- a maximum single-charity weight;
- a reserved exploration budget;
- concentration-review thresholds;
- visible residual allocation caused by caps;
- mandatory human review before promotion.

The default policy caps any single current allocation at `0.45`, reserves `0.10` for exploration, and routes concentrated proposals toward review. The guard degrades concentration gracefully rather than allowing one measurement, charity, or theory of impact to consume the whole definition of good.

## Hybrid Delta Research Lane

```text
Python constructs graph, QUBO, policy context, and receipts.
Qiskit samples bounded local candidate geometry.
Classical exact solving supplies an independent baseline.
Rust reconstructs and verifies route and repayment arithmetic.
Python applies policy and emits non-authoritative evidence.
Human review remains the promotion gate.
```

### Route construction and QAOA evidence

- `eve_q/qaoa_delta.py` enumerates deterministic triangular cycles and builds QUBO/Ising contracts.
- `eve_q/qaoa_sampling.py` performs bounded local sampling, deterministic decoding, model hashing, and exact classical comparison.
- QAOA and classical results are only comparable when bound to the identical QUBO hash.

### Exact Rust repricing

- `eve_q/rust_repricing.py` binds a selected candidate and market snapshot to a strict request.
- `rust/delta-verifier/` independently reconstructs route identity and verifies fee, slippage, latency, gas, profitability, and declared margin assumptions.
- The bridge invokes an explicitly selected local binary with `shell=False` and fails closed on schema, identity, output-size, timeout, or authority drift.

### Perturbation and calibration

- `eve_q/delta_robustness.py` reprices a selected candidate across deterministic alternate market states and emits survival evidence.
- `eve_q/perturbation_calibration.py` converts source-bound historical observations into bounded adverse rate, fee, slippage, latency, and gas scenarios.
- Dataset, policy, scenario, model, and snapshot hashes preserve provenance.
- Quantiles describe the supplied corpus; they do not promise recurrence.

### Flash-liquidity geometry

- `eve_q/flash_liquidity.py` expands routes into provider, borrowed-asset, and amount-bucket candidates.
- `rust/delta-verifier/src/bin/codex-flash-liquidity-verifier.rs` verifies route identity, capacity, provider fee, repayment, and minimum net profit.
- No provider discovery, borrowing, signing, submission, or capital movement occurs.

### Reproducible benchmark spine

Phase 2E closes the research loop with a deterministic historical-replay instrument:

- `benchmarks/seeded_market_v0_1.json` — versioned synthetic snapshot and observation corpus;
- `eve_q/hybrid_benchmark.py` — strict loader, canonical hashing, identical-QUBO comparisons, Rust-backed replay, and receipt construction;
- `schemas/hybrid_delta_benchmark_case.schema.json` — benchmark-input contract;
- `schemas/hybrid_delta_benchmark_receipt.schema.json` — benchmark-evidence contract;
- `docs/QAOA_DELTA_PHASE_2E.md` — architecture and interpretation boundary;
- `.github/workflows/hybrid-benchmark-ci.yml` — Python 3.11/3.13, local Qiskit, compiled Rust replay, deterministic receipt, and artifact-emission validation.

The complete chain is:

```text
seeded market snapshot
→ triangular cycles
→ route QUBO
→ local QAOA evidence
→ exact classical comparison on the identical model
→ Rust exact repricing
→ source-bound perturbation calibration
→ Rust-backed robustness evaluation
→ route/provider/bucket QUBO
→ local QAOA liquidity evidence
→ exact classical comparison on the identical model
→ Rust capacity and repayment verification
→ canonical simulation_summary envelope
→ human review
```

A benchmark must be reconstructible. A source hash binds evidence; it does not make the evidence true. A receipt records the experiment; it does not command the system.

## Artifact and Memory Carrier Lane

```text
The image carries the acorn.
The CID points to the memory.
The key is consent.
The artifact never commands.
```

- `contracts/artifact_carrier_manifest.json` defines safe CID-backed carrier manifests.
- `eve_q/artifact_carrier.py` validates carrier manifests.
- `eve_q/receipt_carrier_attestation.py` binds receipt identity to carrier evidence.
- `eve_q/membrane_tool.py` extracts and compares bounded metadata without writing metadata or opening a reverse execution channel.

Private or encrypted payloads require explicit encryption metadata and human-held or external-vault key custody. Secrets, wallet seeds, private keys, API keys, shell commands, and execution fields are rejected.

## Allowed Output Classes

The current organ contract permits review artifacts such as:

- `artifact_receipt`;
- `safety_bridge_receipt`;
- `risk_report`;
- `charity_allocation_proposal`;
- `simulation_summary`;
- `drift_audit`;
- `testnet_result`.

Repository modules also produce typed intermediate evidence including QAOA confidence receipts, exact-repricing evidence, robustness receipts, perturbation-calibration receipts, flash-liquidity candidates, repayment-verification evidence, and hybrid benchmark receipts. These intermediate objects remain non-authoritative and must be wrapped in an allowed artifact class before entering the canonical external receipt lane.

## Current Surface Index

| Surface | File | Purpose |
| --- | --- | --- |
| Organ contract | `contracts/organ_contract.json` | Defines allowed outputs, forbidden capabilities, modes, promotion path, and hard invariants. |
| Organ validator | `eve_q/organ_contract.py` | Validates records against the local constitutional membrane. |
| Receipt emitter | `eve_q/receipt_emitter.py` | Emits canonical artifact-only receipts. |
| Charity geodesic policy | `eve_q/allocation/geodesic_policy.py` | Scores bounded impact/need proposals while holding transfers for review. |
| Charity diversity guard | `eve_q/allocation/charity_router.py` | Caps concentration, reserves exploration budget, and requires human promotion. |
| QAOA delta core | `eve_q/qaoa_delta.py` | Enumerates triangular cycles and builds QUBO/Ising models. |
| QAOA sampling | `eve_q/qaoa_sampling.py` | Emits deterministic confidence evidence and exact classical comparisons. |
| Rust repricing bridge | `eve_q/rust_repricing.py` | Invokes and validates the isolated exact verifier. |
| Robustness engine | `eve_q/delta_robustness.py` | Tests selected geometry across alternate market states. |
| Perturbation calibrator | `eve_q/perturbation_calibration.py` | Derives bounded empirical adverse scenarios from supplied history. |
| Flash-liquidity geometry | `eve_q/flash_liquidity.py` | Models provider, asset, amount, capacity, fee, and repayment choices. |
| Exact Rust verifiers | `rust/delta-verifier/` | Verify route and flash-repayment arithmetic without networking or authority. |
| Hybrid benchmark | `eve_q/hybrid_benchmark.py` | Reconstructs and receipts the complete seeded experiment. |
| Seeded corpus | `benchmarks/seeded_market_v0_1.json` | Supplies reproducible synthetic historical-replay inputs. |
| Benchmark CI | `.github/workflows/hybrid-benchmark-ci.yml` | Validates complete replay and canonical artifact emission. |
| Carrier validator | `eve_q/artifact_carrier.py` | Validates CID-backed memory-carrier manifests. |
| Membrane tool | `eve_q/membrane_tool.py` | Compares bounded image metadata, manifests, and attestations. |

## Status

CodexTradingEngine is an early-stage safety, telemetry, optimization, verification, charity-allocation, and artifact-research project.

It is not:

- a live autonomous trading engine;
- a wallet;
- a transaction signer;
- a flash-loan executor;
- a promise of profit;
- financial advice.

Current strength is planning and verification under uncertainty—not latency racing. The engine is designed to generate higher-quality, pressure-tested options and route them through explicit evidence and human promotion.

Human review and explicit human promotion remain required before any real-world capital touchpoint.
