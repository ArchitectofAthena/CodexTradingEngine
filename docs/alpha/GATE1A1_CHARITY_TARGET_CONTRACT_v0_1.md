# Gate 1A.1 Simulation-Only Charity Target Contract v0.1

## Purpose

Define how charity may enter the Gate 1A.1 research architecture without becoming a wallet, transfer mechanism, unsupported causal story, or automatic reward rewrite.

```text
telemetry_observed
→ counterfactual_impact_estimated
→ uncertainty_preserved
→ human_review
→ no_transfer
```

The contract is a target and evaluation grammar only.

## Evidence taxonomy

### Donation transfer evidence

Proves that a transfer occurred only when a separate immutable transaction reference and receipt exist. In this contract:

```yaml
status: ABSENT
transaction_reference: null
receipt_sha256: null
```

Absence is not failure. No transfer was attempted.

### Observed outcome evidence

Represents measured external outcomes with provenance. In this contract:

```yaml
status: NO_DATA
observations: []
provenance: null
```

`NO_DATA` means no observation is available. It is explicitly not equivalent to zero impact, negative impact, transfer failure, or absence of charitable value.

### Modeled contribution

A counterfactual research estimate with an uncertainty interval and assumptions digest. It remains `MODEL_ONLY` and cannot be restated as observed outcome evidence.

### Unsupported causal claim

Forbidden. Modeled contribution and correlated telemetry do not prove that a charitable action caused an external outcome.

## Reward and authority boundary

Charity telemetry may inform a later human review. It cannot:

- update a reward function automatically;
- rewrite optimization priorities;
- activate Gate 1B;
- access a wallet;
- sign or submit a transaction;
- move capital;
- convert moral salience into execution authority.

A later reward-function proposal would require a separate explicit human promotion artifact.

## Contract identity

The full contract, including the ordered pipeline, no-data semantics, uncertainty posture, review state, and authority locks, is content-addressed. Semantic drift with the old identifier is rejected.

## CLI

```bash
codex-gate1a1-charity \
  contracts/gate1a1_charity_target_contract_v0_1.json \
  --output artifacts/gate1a1/charity-target-receipt.json
```

Expected decision-critical fields:

```yaml
status: SIMULATION_ONLY_CONTRACT_COMPLETE
transfer_evidence_status: ABSENT
outcome_evidence_status: NO_DATA
modeled_contribution_status: MODEL_ONLY
no_data_means_zero: false
transfer_enabled: false
reward_update_enabled: false
authority: false
gate1b_activated: false
human_promotion_required: true
```

## Boundary

```yaml
authority: false
artifact_is_command: false
automatic_gate_promotion: false
gate1b_activated: false
may_execute: false
may_sign: false
may_submit_transaction: false
may_access_wallet: false
may_move_capital: false
human_promotion_required: true
```

> Charity may curve the research question. It does not seize the controls.
