# EVE_Q++ Gate 1 Pilot Status v0.1

```text
Gate 0 SIMULATION_ONLY: ACTIVE
Gate 1 LIVE_READ_ONLY_TELEMETRY: PILOT CODE UNDER REVIEW
Gate 2 LIVE_PROPOSAL_GENERATION: LOCKED
Gate 3–6: LOCKED
```

## Implemented in this branch

- HTTPS-only, exact-host allowlisted source specifications;
- `GET`/`HEAD` transport boundary;
- explicit pilot enable and kill switch;
- targeted write-secret preflight that reports names only;
- response-size and timeout bounds;
- JSON and text normalization;
- raw and normalized SHA-256 hashes;
- canonical snapshot artifact ID;
- offline replay and freshness validation;
- schema and boundary tests;
- draft threat model and rollback plan.

## Still required before Gate 1 can be ready for human review

- reviewed live public/read-only source list;
- DNS/IP-class and redirect-chain hardening;
- executable rollback test receipt;
- source-outage campaign;
- conflicting-source and weak-provenance campaign;
- bounded live-read-only soak;
- content-addressed threat model, rollback receipt, and soak result;
- final `GateDescentProposal` update to `READY_FOR_HUMAN_REVIEW`;
- explicit human promotion.

## Authority posture

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required": true,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_move_capital": false
}
```

This branch builds an observation membrane. It does not lower Gate 1.
