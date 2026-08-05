# EVE_Q++ Gate 1 Pilot Status v0.1

```text
Gate 0  SIMULATION_ONLY: ACTIVE
Gate 1A TESTNET_READ_ONLY_ALPHA: ACTIVE FOR APPROVED ALPHA RUNS
Gate 1B MAINNET_READ_ONLY_TELEMETRY: LOCKED
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
- transport-level public-IP connection pinning while preserving TLS hostname verification;
- rollback-receipt emission on supported failures;
- deterministic telemetry-to-draft translation with exact-hash operator review;
- one-run alpha doctor and result surface;
- fixed-count 25-capture Sepolia soak with complete replay;
- offline conflict and false-consensus refusal evidence;
- schema and boundary tests;
- structured alpha issue reporting.

## Gate 1A closure packet

Issue #132 packages the completed evidence into:

```text
examples/governance/gate1_closure_threat_model_v0_1.json
examples/governance/gate_descent_g0_to_g1_ready_v0_1.json
examples/governance/gate1_closure_rollback_receipt_v0_1.json
```

The proposal state is:

```text
READY_FOR_HUMAN_REVIEW
```

This state is non-commanding. Human decision fields remain unset, and passing tests do not promote any gate. The review question is limited to ratifying and closing the historical Gate 0 to Gate 1A evidence record. Gate 1B remains locked regardless of that decision.

## Still required before Gate 1B mainnet review

- reviewed live public/read-only mainnet source set with independent provenance;
- mainnet-specific terms, freshness, rate-limit, payload, and outage review;
- bounded source-outage and provider-conflict campaigns using those reviewed sources;
- bounded live-read-only mainnet soak;
- mainnet-specific content-addressed threat model and residual-risk decision;
- a separate Gate 1B proposal;
- explicit human promotion of Gate 1B.

## Authority posture

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required_for_next_gate": true,
  "mainnet_allowed": false,
  "may_generate_live_proposal": false,
  "may_sign": false,
  "may_submit_transaction": false,
  "may_execute": false,
  "may_use_flash_liquidity": false,
  "may_transfer_charity": false,
  "may_move_capital": false,
  "testnet_read_only_alpha_allowed": true
}
```

Gate 1A opens a narrow observation window for alpha evidence. It does not open the cockpit door to execution.
