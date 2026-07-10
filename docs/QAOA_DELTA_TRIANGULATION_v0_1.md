# QAOA Delta Triangulation v0.1

This document defines the first bounded hybrid quantum/classical arbitrage-search organ for CodexTradingEngine.

## Compute lanes

```text
Python control plane
    telemetry normalization, graph construction, policy, receipts

Qiskit QAOA lane
    price-delta triangulation and constrained cycle selection

Rust verifier lane
    exact repricing, fee/slippage arithmetic, latency-sensitive checks

Classical fallback
    benchmark, recovery path, oversized-problem handling, independent verification
```

## Core distinction

QAOA proposes a route candidate. It does not prove the route remains profitable and it never grants execution authority.

```text
market snapshot
→ directed exchange graph
→ triangular cycle enumeration
→ QUBO encoding
→ QAOA candidate selection
→ Rust exact verification
→ policy and risk gates
→ simulation receipt
→ human promotion
```

## Objective

For a triangular route, each directed edge contributes an effective multiplier after proportional costs:

```text
effective_rate = quoted_rate
               × (1 - fee_bps / 10_000)
               × (1 - slippage_bps / 10_000)
               × (1 - latency_penalty_bps / 10_000)
```

The cycle score is the natural logarithm of the product of effective rates, minus an explicit gas-cost penalty expressed in the starting asset's quote units.

Positive log delta means the multiplicative route remains above break-even before any further policy margin.

## QUBO contract

The first implementation assigns one binary variable to each already-enumerated triangular cycle. The QUBO minimizes negative cycle score while applying quadratic penalties when selected cycles conflict over the same edge.

This is deliberately narrower than an edge-level flow-conservation encoding. It gives us a deterministic, testable substrate before expanding the quantum search space.

## Qiskit boundary

The core package emits QUBO coefficients without requiring Qiskit. An optional adapter converts those coefficients into a `SparsePauliOp` suitable for `qiskit.circuit.library.QAOAAnsatz`.

Qiskit is optional because:

- Termux and low-resource environments must retain the classical fallback;
- the QUBO contract must remain independently testable;
- Qiskit Optimization 0.7.0 is no longer officially supported by IBM, so this architecture owns its QUBO encoding and depends only on the supported Qiskit core API when enabled.

## Authority boundary

Every problem, candidate, solution, and verification object carries `authority: false`.

This organ performs no:

- wallet or transaction signing;
- RPC submission;
- flash-loan borrowing;
- mempool mutation;
- autonomous capital movement;
- scheduler-triggered execution.

The output is a simulation/research proposal only.
