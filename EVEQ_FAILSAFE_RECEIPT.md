# EVE_Q++ Receipt-Gated Failsafe

This branch adds `eveq_failsafe_receipt.py`.

## Purpose

Trust / TTL expansion is routed through validated CycleReceipt state only.

## Invariant

```text
No validated receipt -> no trust expansion.
No proof -> no trust.
No liveness -> no execution.
```

## Included code

- `CycleReceipt`
- `validate_receipt(...)`
- `FailsafeConfig`
- `save_state(...)` / `load_state(...)`
- `progressive_trust_increment_from_receipt(...)`

## Development posture

Shadow and dry-run cycles may be logged and reviewed. They do not expand trust.

## Next integration point

Wire the cycle runner so each cycle creates a `CycleReceipt`, validates it, and updates failsafe state only through `progressive_trust_increment_from_receipt(...)`.
