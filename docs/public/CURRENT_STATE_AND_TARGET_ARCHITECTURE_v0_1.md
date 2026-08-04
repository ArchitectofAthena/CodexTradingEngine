# CodexTradingEngine Current State and Target Architecture v0.1

## Why this document exists

CodexTradingEngine is an active research build. Some repository surfaces are implemented and testable now; other surfaces describe intended later capabilities.

This document keeps those two layers separate so that reviewers, alpha testers, and contributors can tell what exists today from what the project is trying to earn.

```text
implemented != intended
modeled != observed
positive fixture edge != repeatable profit
review artifact != executable instruction
future architecture != current capability
```

## Current operating posture

```text
Gate 0  SIMULATION_ONLY: ACTIVE
Gate 1A TESTNET_READ_ONLY_ALPHA: ACTIVE FOR APPROVED ALPHA RUNS
Gate 1B MAINNET_READ_ONLY_TELEMETRY: LOCKED
Gate 2  LIVE_PROPOSAL_GENERATION: LOCKED
Gate 3  TESTNET_MANUAL_EXTERNAL: LOCKED
Gate 4–6: LOCKED
```

Gate 1A allows an approved tester to:

- capture bounded public blockchain testnet observations through reviewed HTTPS `GET` or `HEAD` sources;
- replay the captured snapshot offline;
- inspect provenance, freshness, units, and hashes;
- translate selected observations into a local simulation fixture;
- run `codex-research`;
- compare model outputs and file a structured alpha report.

Gate 1A does not allow:

- mainnet ingestion;
- wallet connection or custody;
- seed phrases, signing keys, or write-capable credentials;
- transaction construction, submission, or broadcast;
- flash-loan execution;
- live proposal generation;
- capital movement;
- autonomous charity transfers.

## Implemented and testable now

### Local simulation and reporting

The public CLI can:

- load deterministic or user-supplied local route fixtures;
- evaluate modeled profit after declared gas, slippage, and safety-margin inputs;
- emit one readable report plus underlying evidence artifacts;
- separate software readiness, modeled economics, and execution posture.

```text
PIPELINE=READY | HOLD
ECONOMICS=POSITIVE_EDGE | NO_POSITIVE_EDGE
EXECUTION=LOCKED
```

### Read-only testnet observation

The existing observation membrane supports:

- HTTPS-only `GET` and `HEAD` capture;
- exact-host allowlisting;
- DNS and IP-class preflight;
- response-size and timeout limits;
- raw and normalized SHA-256 hashes;
- offline replay;
- freshness checks;
- post-capture DNS drift detection;
- rollback receipts on supported failures.

Many blockchain JSON-RPC endpoints use `POST`. They remain outside Gate 1A even when the requested RPC method would be read-only.

### QAOA research comparison

The repository can construct bounded QUBO models and compare local QAOA evidence with an exact classical solution on the identical QUBO hash.

The current rule is:

```text
QAOA is an experimental comparison lane.
Exact classical solving is the independent baseline.
No quantum advantage is assumed.
```

QAOA should not be described as the primary production search path unless benchmark evidence later shows a practical advantage for a defined problem class, input size, hardware environment, and cost envelope.

### Rust verification

The Rust verifier lane independently checks modeled route identity and declared arithmetic under strict local subprocess contracts. It does not discover providers, borrow funds, sign transactions, or execute routes.

### Charity-allocation research

The repository currently produces non-authoritative charity-allocation proposals and applies concentration safeguards. Every current allocation decision preserves `hold_transfer: true`.

There is no active 15-percent transfer, autonomous donation mechanism, or deployed reinforcement-learning reward loop.

## Telemetry interpretation boundary

RSI, MACD, volume, sentiment, whale-flow, liquidity, fee, gas, latency, and cross-venue price observations may all become candidate features in later research.

They do not carry identical meanings:

- cross-chain or cross-venue price, liquidity, fee, gas, and latency data may support route modeling;
- RSI and MACD describe transformations of historical price series;
- volume and flow measures require source-specific interpretation;
- sentiment may support forecasting experiments but does not establish executable arbitrage;
- a correlation or model score does not prove causation or durable edge.

No single indicator should be presented as proof that a route exists or remains executable.

## Fee and chain boundary

Low-fee networks may reduce modeled transaction cost, but fees are not guaranteed to remain fractions of a cent. Cost depends on network congestion, protocol design, transaction complexity, token price, bridge or liquidity-provider fees, and execution conditions.

Every alpha report should state the units, timestamp, chain, source, and assumptions behind any cost estimate.

## Target architecture, not yet active

The long-range design may include:

```text
multi-chain telemetry
→ candidate route discovery
→ classical and QAOA comparison
→ independent Rust verification
→ robustness and liquidity checks
→ human-reviewed testnet proposal
→ faucet-only manual testnet action
→ transaction and outcome receipt
→ later capped live review
→ charity tithe and impact-feedback research
```

The following are target capabilities only:

- direct telemetry-to-proposal routing;
- live mainnet proposal generation;
- wallet-aware execution assistance;
- flash-loan borrowing or repayment;
- transaction signing or submission;
- automatic profit extraction;
- automatic 15-percent charity transfer;
- charity-outcome feedback as a machine-learning reward signal;
- migration from testnets to Solana, Polygon, Arbitrum, or other production networks.

Each target requires its own implementation, threat model, test campaign, rollback proof, and explicit gate promotion.

## Evidence required before later claims

### Before calling QAOA a primary path

- identical-input comparison with exact classical methods;
- runtime, solution quality, memory, stability, and cost measurements;
- problem-size scaling evidence;
- reproducible benchmark corpus;
- a stated domain where QAOA adds measurable value.

### Before Gate 2 live proposal generation

- completed Gate 1B evidence campaign;
- reviewed source set;
- provenance and conflict handling;
- deterministic telemetry-to-feature translation;
- explicit stale-data and source-disagreement behavior;
- proposal output that remains non-command.

### Before Gate 3 manual testnet action

- supported testnets and chain IDs;
- faucet-only wallet hygiene;
- per-action human approval;
- hard value and frequency caps;
- transaction-hash and outcome receipts;
- failure and rollback procedures;
- no engine custody of signing material.

### Before any charity transfer or reward loop

- a defined tithe contract;
- net-profit calculation after all costs and liabilities;
- tax and legal review;
- charity eligibility and destination verification;
- duplicate, fraud, and concentration controls;
- impact telemetry provenance and confidence rules;
- explicit separation between donation policy and model authority;
- complete dry-run and testnet evidence.

## Public description template

A current, accurate short description is:

> CodexTradingEngine is a simulation-first cross-chain telemetry and route-research system. Its current alpha lane captures bounded public testnet observations, replays them offline, translates them into local fixtures, and compares modeled route evidence with independent verification. QAOA is experimentally benchmarked against exact classical solutions. Wallets, signing, flash-loan execution, mainnet proposals, capital movement, and autonomous charity transfers remain locked.

A future-looking description should be labeled clearly:

> The target architecture is a human-gated cross-chain arbitrage research and execution stack that may eventually test faucet-only routes on testnets, earn tightly capped live capability, and direct a defined share of verified net profits toward approved charities.

## Canonical alpha entrypoint

Approved alpha testers should begin with:

- [`QUICKSTART.md`](../../QUICKSTART.md)
- [`ALPHA_TESTNET_QUICKSTART_v0_1.md`](../alpha/ALPHA_TESTNET_QUICKSTART_v0_1.md)

The alpha group is being asked to produce evidence about usability, environment trust, source handling, route modeling, classical-versus-QAOA behavior, and boundary enforcement. It is not being asked to risk funds.
