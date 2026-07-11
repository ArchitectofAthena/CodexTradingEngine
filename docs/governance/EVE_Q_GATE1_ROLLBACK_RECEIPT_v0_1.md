# EVE_Q++ Gate 1 Rollback Receipt v0.1

## Purpose

Rollback must produce evidence, not merely print an error and disappear.

The Gate 1 launcher now emits a canonical `Gate1RollbackReceipt` whenever it fails closed after entering the pilot path.

## Supported triggers

- `kill_switch`
- `source_outage`
- `dns_policy_failure`
- `operator_abort`

## Required restoration proof

Every valid receipt records:

```text
pilot disabled: true
network capture stopped: true
pending capture abandoned: true
Gate 0 restored: true
Gate 2–6 locked: true
```

The receipt transitions only:

```text
LIVE_READ_ONLY_TELEMETRY_PILOT
→ SIMULATION_ONLY
```

It cannot open another gate.

## Constitutional posture

A rollback receipt is an observation of a bounded safety transition. It is not an execution command and carries no capital authority.

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

## CLI

Write and validate a synthetic kill-switch receipt:

```bash
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PRODUCER_COMMIT="$(git rev-parse HEAD)"

python -m eve_q.gate1_hardening \
  --write-rollback-receipt artifacts/gate1/rollback_receipt.json \
  --producer-commit "$PRODUCER_COMMIT" \
  --trigger kill_switch \
  --now "$NOW"

python -m eve_q.gate1_hardening \
  --validate-rollback-receipt artifacts/gate1/rollback_receipt.json
```

## Gate posture

This receipt proves return to Gate 0. It does not activate Gate 1.
