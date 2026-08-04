# EVE_Q++ Gate 1 Pilot Status v0.1

```text
Gate 0  SIMULATION_ONLY: ACTIVE
Gate 1A TESTNET_READ_ONLY_ALPHA: ACTIVE FOR APPROVED ALPHA RUNS
Gate 1B MAINNET_READ_ONLY_TELEMETRY: LOCKED PENDING #68 / #76
Gate 2  LIVE_PROPOSAL_GENERATION: LOCKED
Gate 3  TESTNET_MANUAL_EXTERNAL: LOCKED
Gate 4–6: LOCKED
```

## Gate 1A activation

The Architect explicitly promoted one bounded sub-gate on 2026-08-04 so an alpha cohort can exercise the existing read-only capture and local research workflow against public blockchain testnets.

Gate 1A permits:

- public testnet observations only;
- HTTPS `GET` or `HEAD` sources with exact-host allowlisting;
- bounded capture, content addressing, offline replay, and DNS/IP verification;
- explicit operator translation into local route fixtures;
- local simulation, exact verification, and structured reporting.

Gate 1A does not permit:

- mainnet data;
- wallet material or write-capable credentials;
- direct live-data routing into proposal generation;
- transaction construction, signing, submission, or broadcast;
- capital movement;
- promotion into Gate 1B, Gate 2, or Gate 3.

The canonical alpha workflow is documented in:

```text
docs/alpha/ALPHA_TESTNET_QUICKSTART_v0_1.md
```

The governance decision is recorded in:

```text
docs/governance/EVE_Q_GATE1A_ALPHA_PROMOTION_v0_1.md
```

## Implemented controls

- HTTPS-only, exact-host allowlisted source specifications;
- `GET`/`HEAD` transport boundary;
- explicit pilot enable and kill switch;
- targeted write-secret preflight that reports names only;
- response-size and timeout bounds;
- JSON and text normalization;
- raw and normalized SHA-256 hashes;
- canonical snapshot artifact ID;
- offline replay and freshness validation;
- DNS/IP-class preflight and post-capture drift detection;
- rollback-receipt emission on supported failures;
- schema and boundary tests;
- structured alpha issue reporting.

## Still required before Gate 1B mainnet review

- reviewed live public/read-only mainnet source list;
- transport-level IP pinning while preserving TLS hostname verification, or an explicit accepted residual-risk decision;
- bounded source-outage campaign;
- conflicting-source and weak-provenance campaign;
- bounded live-read-only mainnet soak;
- content-addressed threat model, rollback receipt, and soak result;
- final `GateDescentProposal` update to `READY_FOR_HUMAN_REVIEW`;
- explicit human promotion of Gate 1B.

## Authority posture

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required_for_next_gate": true,
  "mainnet_allowed": false,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_move_capital": false,
  "testnet_read_only_alpha_allowed": true
}
```

Gate 1A opens a narrow observation window for alpha evidence. It does not open the cockpit door to execution.
