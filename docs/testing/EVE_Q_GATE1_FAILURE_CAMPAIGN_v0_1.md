# EVE_Q++ Gate 1 Synthetic Failure Campaign v0.1

## Purpose

This campaign disturbs the Gate 1 read-only observation membrane without contacting a live source. It produces deterministic evidence that source failures and epistemic disagreement cannot cascade into proposal generation, execution authority, or capital authority.

## Cases

| Case | Required result |
|---|---|
| Independent agreement | `GROUNDED` + `OBSERVE_ONLY` |
| Conflicting sources | `CONFLICTING` + `HOLD` |
| Weak-provenance agreement | `HERDING_RISK` + `HOLD` |
| Source outage | valid rollback receipt to Gate 0 |
| Stale snapshot | rejected |
| Malformed payload | rejected |
| Replay hash mismatch | rejected |
| Non-public DNS answer | rejected |
| DNS address-set drift | rejected |

Agreement never creates authority. Even independently corroborated observations remain observation-only.

## Boundary

Every campaign record preserves:

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required": true,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_move_capital": false,
  "gate_posture": {
    "gate_0": "ACTIVE",
    "gate_1": "PILOT_ONLY",
    "gate_2_through_6": "LOCKED"
  }
}
```

The campaign performs no network calls and configures no live source.

## Run

```bash
export CYCLES=100
export SEED=424243
export PRODUCER_COMMIT="$(git rev-parse HEAD)"

bash scripts/run_gate1_failure_campaign_v0_1.sh
```

Outputs:

```text
$HOME/spiralbloom-runs/<run-id>/campaign.jsonl
$HOME/spiralbloom-runs/<run-id>/summary.json
```

## Acceptance

A passing campaign requires:

- every case exercised;
- every case producing the expected fail-closed disposition;
- zero unexpected failures;
- zero unauthorized transitions;
- every outage producing a canonical rollback artifact;
- conflict and herding risk always producing `HOLD`;
- independent agreement remaining `OBSERVE_ONLY`;
- Gate 2–6 remaining locked.

## Interpretation

This is synthetic resilience evidence. It does not activate Gate 1, prove live-source reliability, or authorize live proposal generation.

> Observe disagreement. Preserve uncertainty. Roll back cleanly. Never promote by momentum.
