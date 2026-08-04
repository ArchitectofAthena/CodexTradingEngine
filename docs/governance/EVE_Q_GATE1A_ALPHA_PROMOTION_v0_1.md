# EVE_Q++ Gate 1A Alpha Promotion v0.1

## Human decision

On 2026-08-04, the Architect authorized one bounded gate descent so approved alpha testers can exercise a practical, reproducible public testnet workflow.

This promotion creates a scoped sub-gate. It does not certify the entire Gate 1 evidence campaign and does not skip Gate 2 or Gate 3.

## Active posture

```text
Gate 0  SIMULATION_ONLY: ACTIVE
Gate 1A TESTNET_READ_ONLY_ALPHA: ACTIVE FOR APPROVED ALPHA RUNS
Gate 1B MAINNET_READ_ONLY_TELEMETRY: LOCKED PENDING #68 / #76
Gate 2  LIVE_PROPOSAL_GENERATION: LOCKED
Gate 3  TESTNET_MANUAL_EXTERNAL: LOCKED
Gate 4–6: LOCKED
```

## Gate 1A authority surface

Gate 1A permits only:

- public blockchain testnet observations;
- HTTPS `GET` or `HEAD` sources with exact-host allowlisting;
- bounded response size, timeout, and freshness TTL;
- DNS/IP-class preflight and post-capture drift verification;
- content-addressed snapshot bundles;
- offline replay;
- explicit operator translation into local simulation fixtures;
- deterministic simulation and receipt verification;
- structured alpha reporting.

Gate 1A forbids:

- mainnet sources;
- wallet connection or custody;
- seed phrases, private keys, signing keys, or trading credentials;
- transaction construction, signing, submission, or broadcast;
- direct live-data routing into proposal generation;
- autonomous or assisted capital movement;
- `POST`, `PUT`, `PATCH`, or `DELETE` network transport;
- self-promotion into Gate 1B, Gate 2, or Gate 3;
- treating a testnet result as proof of future profit.

## Promotion receipt

```json
{
  "promotion_id": "eve-q-gate1a-alpha-v0.1",
  "decision_date": "2026-08-04",
  "decision_source": "Architect explicit instruction",
  "tracking_issue": 116,
  "from_gate": "SIMULATION_ONLY",
  "to_gate": "TESTNET_READ_ONLY_ALPHA",
  "scope": "approved_alpha_runs_only",
  "mainnet_allowed": false,
  "wallet_allowed": false,
  "signing_allowed": false,
  "transaction_submission_allowed": false,
  "live_proposal_generation_allowed": false,
  "capital_movement_allowed": false,
  "rollback_gate": "SIMULATION_ONLY",
  "human_promotion_required_for_next_gate": true,
  "artifact_is_command": false,
  "authority": false
}
```

The receipt records the human governance decision. It is not executable configuration and cannot widen its own scope.

## Alpha admission

The repository remains public, but participation in the named alpha cohort is approved by the Architect. Anyone may run the simulation-only quickstart. A run counts toward the Gate 1A alpha evidence set only when it:

1. identifies the exact producer commit;
2. uses a public testnet, not mainnet;
3. uses a public read-only source compatible with the current transport membrane;
4. completes preflight, capture, replay, and postflight verification;
5. preserves `EXECUTION=LOCKED`;
6. submits the structured alpha report without secrets or private data.

## Review window

Review Gate 1A after either:

- 25 accepted alpha sessions; or
- 30 calendar days from the first accepted alpha session;

whichever occurs first.

The review must summarize:

- installation and operator friction;
- environment and binary-trust failures;
- source-policy failures;
- rollback outcomes;
- receipt/report usefulness;
- classical versus QAOA comparison value;
- false positives, false negatives, and ambiguous economics;
- any attempted boundary expansion.

The review may retain, narrow, suspend, or retire Gate 1A. It may not automatically open Gate 1B, Gate 2, or Gate 3.

## Rollback

```text
boundary failure
→ kill switch
→ rollback receipt
→ Gate 0 simulation-only
→ human review
```

A failed alpha run is useful evidence. It is not a reason to hide the failure, and it is not authority to improvise around the membrane.

## Relationship to existing campaigns

- Issue #116 tracks the scoped alpha workflow.
- Issue #76 remains the bounded live read-only source review and soak campaign.
- Issue #68 remains the full Gate 1 evidence program.
- Gate 1A does not satisfy or replace the mainnet-facing evidence requirements in #68 or #76.

> The next gate is lowered only where the floor is testnet, the window is read-only, and the exit back to simulation remains obvious.
