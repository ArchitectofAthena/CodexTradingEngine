# QAOA Delta Phase 2B — Isolated Rust Repricing Bridge

Phase 2B turns a QAOA confidence receipt into an independently repriced market claim.
It does not introduce live execution.

## Compute lanes

```text
QAOA confidence receipt
→ Python request builder
→ strict JSON request
→ isolated Rust verifier process
→ strict JSON response
→ Python response validation
→ simulation evidence
```

- **Qiskit/QAOA** proposes candidate geometry.
- **Rust** recomputes route closure, fees, slippage, latency penalty, gas penalty,
  net multiplier, net log delta, and margin survival.
- **Python** binds hashes, launches the explicit local verifier with `shell=False`,
  enforces timeout and payload limits, validates the response, and records drift.
- **Human review** remains the promotion gate.

## Request binding

Every request binds:

- a stable `request_id`;
- the market snapshot SHA-256;
- the QUBO model SHA-256;
- the originating QAOA confidence receipt;
- the triangular candidate identifier;
- exactly three ordered market edges;
- gas and minimum-margin assumptions;
- `authority: false`.

The Rust verifier independently reconstructs the candidate identifier from the
rotation-canonical edge sequence and rejects identity drift.

## Process boundary

The verifier:

- reads at most 65,536 bytes from standard input;
- accepts one strict JSON object with unknown fields rejected;
- writes one deterministic JSON response to standard output;
- writes a bounded machine-readable error to standard error on rejection;
- performs no network, filesystem, wallet, RPC, signer, scheduler, or capital action.

The Python bridge:

- requires an absolute executable path;
- invokes a single argument vector with `shell=False`;
- applies a strict timeout;
- rejects oversized output;
- requires exact response keys;
- verifies all request identity fields are echoed unchanged;
- rejects any authority escalation;
- fails closed on timeout, crash, malformed JSON, schema drift, or identity drift.

## Evidence object

Successful verification records:

```text
snapshot_sha256
model_sha256
confidence_receipt_id
candidate_id
verifier identity
ordered edge identifiers
asset path
net multiplier
net log delta
minimum margin
profitability
margin survival
proposal log delta
verified delta drift
authority: false
```

`delta_drift` is the difference between Rust's exact repricing result and the
Python proposal. A zero drift is expected when both lanes consume the same
snapshot and assumptions. Later phases may deliberately reprice against fresher
or perturbed snapshots, where nonzero drift becomes a primary signal.

## Promotion law

```text
QAOA may propose.
Rust must reprice.
Python must apply policy.
Evidence may increase trust.
Evidence cannot grant authority.
Human review remains required before any capital touchpoint.
```
