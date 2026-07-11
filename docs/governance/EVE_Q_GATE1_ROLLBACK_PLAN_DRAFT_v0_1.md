# EVE_Q++ Gate 1 Rollback Plan Draft v0.1

## Trigger

Rollback is required when any of the following occurs:

- `EVE_Q_GATE1_KILL_SWITCH=1`;
- write-capable secret detected;
- non-allowlisted host or redirect;
- unsupported HTTP method;
- source outage or repeated timeout;
- malformed or oversized payload;
- stale snapshot used where freshness is required;
- raw, normalized, or artifact hash mismatch;
- Gate 2 or later capability appears reachable;
- operator uncertainty about source or credential posture.

## Rollback target

```text
Gate 0 SIMULATION_ONLY: ACTIVE
Gate 1 LIVE_READ_ONLY_TELEMETRY: DISABLED
Gate 2–6: LOCKED
```

## Procedure

1. Set `EVE_Q_GATE1_KILL_SWITCH=1`.
2. Stop all Gate 1 pilot capture processes.
3. Preserve existing snapshot bundles and failure receipts without modification.
4. Remove or unset `EVE_Q_GATE1_PILOT`.
5. Verify a new capture attempt fails with `kill_switch_active`.
6. Run simulation-only producer and contract tests.
7. Record hashes of the rollback plan, failure evidence, and rollback test receipt.
8. Require new human review before any later pilot restart.

## Success criteria

- no network capture proceeds while the kill switch is active;
- simulation-only tests remain available;
- no live observation is converted into a live proposal;
- no wallet, signing, order, transaction, broadcast, or capital interface exists;
- preserved artifacts remain replayable offline;
- the rollback receipt is content-addressed.

## Current state

This plan is a draft. A successful executable rollback test and content-addressed receipt are still required before Gate 1 can become ready for human review.
