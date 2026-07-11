# Typed TTL Lattice and Bounded Authority Manifest v0.2

## Purpose

Codex already treats authority as expiring. This layer makes expiry typed and independently auditable.

```text
bounded capability-space
+ typed time limits
+ deterministic degradation
+ immutable evidence receipt
→ safer proposal and simulation behavior
```

The evaluator is advisory and local. It cannot schedule, sign, submit, borrow, broadcast, mutate a mempool, move capital, or renew itself.

## Spatial boundary

The manifest declares explicit simulation ceilings:

- allowed assets;
- allowed venues;
- allowed order types;
- maximum modeled position notional;
- maximum modeled daily loss;
- maximum modeled leverage;
- denied capabilities.

These values constrain simulation and review. They do **not** grant live capital authority.

A scope request outside the manifest produces a hard-stop receipt with effective state `inert`.

## Temporal boundary

The lattice currently defines seven clocks:

| Clock | Default ceiling | Expiry target | Expiry action |
|---|---:|---|---|
| signal | 90 seconds | `simulation_only` | discard signal |
| provider evidence | 1 hour | `local_analysis_only` | ignore remote evidence |
| strategy packet | 5 minutes | `local_analysis_only` | recompile or emit no proposal |
| execution intent | 30 seconds | `risk_review_only` | cancel-and-reprice advisory |
| position | 15 minutes | `risk_review_only` | closure-review advisory |
| autonomy lease | 24 hours | `alert_only` | degrade to alerts |
| credential lease | 48 hours | `inert` | revocation advisory |

`execution_intent`, `position`, and `credential_lease` are optional clock types. Their names describe policy state only; this repository still has no live order, wallet, signer, or capital path.

## Degradation ladder

```text
bounded_proposal
→ simulation_only
→ local_analysis_only
→ risk_review_only
→ alert_only
→ receipt_only
→ inert
```

The evaluator chooses the most restrictive target reached by any expired clock. It never promotes a state and never accepts self-asserted renewal.

A requested TTL greater than the manifest ceiling is capped. The cap is recorded in the receipt.

## Required clocks

The current manifest requires:

- signal;
- provider evidence;
- strategy packet;
- autonomy lease.

A missing required clock is treated as expired and degrades to the clock's declared target.

## Hard-stop conditions

Hard stop occurs when:

- requested scope exceeds an allowed set or numeric ceiling;
- a denied capability is requested;
- the manifest itself claims execution, wallet, signing, capital, deployment, or scheduler authority.

Hard stop returns `effective_state: inert` and retains `authority: false`.

## Receipt

Every successful evaluation emits a deterministic receipt containing:

- manifest and snapshot hashes;
- current and effective state;
- per-clock age and effective TTL;
- expired and missing clocks;
- scope violations;
- denied capability hits;
- human-review requirement;
- explicit non-authority fields;
- the manifest's hard invariants.

The receipt performs no mutation and makes no network call.

## Example

```python
from eve_q.ttl_lattice import evaluate_ttl_lattice

receipt = evaluate_ttl_lattice(
    {
        "evaluated_at": "2026-07-11T12:00:00Z",
        "current_state": "bounded_proposal",
        "clocks": {
            "signal": {"observed_at": "2026-07-11T11:59:30Z"},
            "provider_evidence": {"observed_at": "2026-07-11T11:30:00Z"},
            "strategy_packet": {"observed_at": "2026-07-11T11:58:00Z"},
            "autonomy_lease": {"observed_at": "2026-07-11T00:00:00Z"}
        },
        "requested_scope": {
            "assets": ["BTC"],
            "venues": ["historical_replay"],
            "order_types": ["proposal"],
            "position_notional_usd": 5000,
            "daily_loss_usd": 100,
            "leverage": 1.0
        },
        "requested_capabilities": [],
        "renewal_requested": False
    }
)
```

## Root law

> Authority is bounded in space. Authority is bounded in time. Expiry reduces capability and never silently renews it. A receipt records degradation; it does not execute it.

## Boundary

- no live market dependency;
- no wallet or signer;
- no order or transaction submission;
- no RPC or mempool mutation;
- no flash-loan borrowing;
- no scheduler or deployment authority;
- no autonomous capital movement;
- human promotion remains required.
