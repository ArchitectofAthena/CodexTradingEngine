# QAOA Delta Triangulation Phase 2A

Phase 2A turns the v0.1 QAOA cost circuit into a bounded local candidate-production loop.
It remains simulation-only and cannot grant execution authority.

## Compute lanes

```text
Python
  owns graph construction, QUBO encoding, bounded parameter search,
  deterministic decoding, comparison receipts, and policy surfaces

Qiskit
  constructs and locally simulates the QAOA ansatz

Classical exact solver
  supplies an independent optimum for the same QUBO

Rust
  remains the next-stage exact market repricer and route verifier
```

## Candidate-production chain

```text
market snapshot
→ triangular cycles
→ QUBO
→ QAOAAnsatz
→ bounded deterministic parameter grid
→ local statevector probability distribution
→ endianness-safe bitstring decoding
→ ranked candidate evidence
→ classical exact comparison
→ confidence receipt
```

No remote quantum backend is contacted. No wallet, RPC, flash-loan, mempool, scheduler,
or transaction surface is present.

## Confidence receipt

A `QaoaConfidenceReceipt` records:

- stable SHA-256 of the complete QUBO coefficient surface;
- solver and QAOA repetition count;
- deterministic parameter order and selected values;
- expected QUBO energy;
- highest-probability decoded assignment;
- top sampled assignments and probabilities;
- classical exact optimum on the identical QUBO;
- energy gap between sampled expectation and classical optimum;
- `authority: false` at every layer.

The receipt measures evidence quality. It does not authorize action.

## Determinism

- QUBO variables retain their canonical order.
- Qiskit bitstrings are explicitly reversed into qubit-index order.
- probability inputs are normalized before decoding.
- ties in parameter search are resolved lexicographically.
- sampled assignments are ranked by probability, energy, then bitstring.
- receipt identifiers derive from canonical JSON over the model and result surface.

## Bounded optimizer

The local optimizer uses a finite parameter grid and enforces a maximum evaluation count.
This is intentionally small and inspectable. Later optimizers may replace the grid, but must
preserve deterministic decoding, independent classical comparison, and receipt emission.

## Promotion law

```text
QAOA may propose.
Classical truth may benchmark.
Rust must reprice.
Python must apply policy.
Human review remains the promotion gate.
```
