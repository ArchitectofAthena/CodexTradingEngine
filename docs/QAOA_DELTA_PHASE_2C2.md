# QAOA Delta Phase 2C-2 — Flash-Liquidity Geometry

## Purpose

Phase 2C-2 expands a verified triangular price-delta route into a bounded research geometry that includes temporary-liquidity source and amount choices.

The selected object is no longer only a route:

```text
route
+ flash-liquidity provider
+ borrowed asset
+ amount bucket
+ provider fee
+ declared capacity
+ repayment feasibility
```

This phase remains simulation-only. It does not borrow funds, sign transactions, submit RPC calls, monitor a mempool, schedule execution, or move capital.

## Compute lanes

### Python

Python owns:

- provider and amount-bucket contracts;
- deterministic route/provider/bucket expansion;
- combined-geometry QUBO construction;
- QAOA-compatible candidate projection;
- request hashing, schema surfaces, subprocess bounds, and evidence validation;
- explicit `authority: false` preservation.

### Qiskit QAOA

QAOA may rank the combined binary geometry. Each variable identifies one complete route/provider/bucket candidate. Infeasible capacity or repayment candidates receive a deterministic penalty.

QAOA output remains a proposal. It does not grant truth or authority.

### Rust

The isolated `codex-flash-liquidity-verifier` binary independently verifies:

- route identity through the existing exact triangular verifier;
- borrowed-asset alignment with the closed route;
- provider capacity against requested principal;
- provider fee and repayment amount;
- route output after fee, slippage, latency, and gas assumptions;
- minimum net-profit and repayment feasibility;
- candidate identity binding across route, provider, and bucket IDs.

The verifier has no network, wallet, signer, scheduler, or capital interface.

## Candidate arithmetic

For principal `P`, provider fee `f` in basis points, and Rust-verified route log delta `d`:

```text
route_output = P × exp(d)
repayment    = P × (1 + f / 10,000)
net_profit   = route_output - repayment
```

A candidate is repayment-feasible only when:

```text
borrowed asset matches route start/end
and principal <= declared capacity
and route_output >= repayment
and net_profit >= minimum_net_profit
```

## QUBO surface

The initial Phase 2C-2 QUBO selects at most one complete geometry.

- feasible positive-net-delta candidates receive negative minimization coefficients;
- capacity or repayment failures receive a large deterministic penalty;
- pairwise penalties prevent simultaneous selections.

Simultaneous opportunity packing and shared-capacity constraints remain future work.

## Identity and provenance

A flash candidate identifier is derived from:

```text
route_candidate_id | provider_id | amount_bucket_id
```

The verification request separately binds:

- market snapshot SHA-256;
- QUBO model SHA-256;
- QAOA confidence receipt ID;
- exact market edges;
- gas assumption;
- principal, fee, capacity, and minimum-profit values.

Changing any request field changes the request receipt identity even when the named route/provider/bucket identity remains constant.

## Boundary law

```text
QAOA may select a liquidity geometry.
Rust must reconstruct the route and repayment arithmetic.
Python must fail closed on protocol drift.
Evidence may increase trust.
Evidence cannot borrow, sign, submit, or command.
Human review remains sovereign.
```

Every provider, bucket, candidate, request, response, and verification object retains:

```json
{"authority": false}
```
