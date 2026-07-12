# EVE_Q++ Gate 1 Source Review Artifact v0.1

## Purpose

A candidate live read-only telemetry source must be reviewed before it may enter the bounded Gate 1 pilot.

```text
candidate source
→ source-review candidate document
→ deterministic validation
→ observation-eligibility decision
→ content-addressed review artifact
→ human review
```

The artifact approves only **observation eligibility**. It does not activate Gate 1, generate proposals, execute transactions, sign messages, submit orders, or move capital.

## Gate posture

```text
Gate 0 SIMULATION_ONLY: ACTIVE
Gate 1 LIVE_READ_ONLY_TELEMETRY: PILOT_ONLY
Gate 2–6: LOCKED
```

## Reviewed source surface

The source review records:

- source identity, operator, source kind, and exact endpoint;
- exact hostname allowlist;
- `GET` or `HEAD` only;
- authentication mode and proof that any credential reference is explicitly read-only;
- documented rate limit and expected response-size cap;
- expected JSON or plain-text payload class;
- freshness TTL, outage expectations, and redirect policy;
- provenance group, upstream provider, source-independence note, and concentration risk;
- legal/terms disposition;
- transport residual-risk disposition;
- rollback and kill-switch compatibility;
- human reviewer identity and exact producer commit.

No credential value belongs in this artifact. A credential reference is an environment-variable name or external-vault pointer only.

## Deterministic decision

The builder computes one observation-eligibility disposition:

- `ELIGIBLE`: all required controls are reviewed and compatible;
- `HOLD`: review, transport, rollback, kill-switch, or concentration work remains unresolved;
- `REJECT`: terms or residual transport risk are explicitly incompatible.

A source marked `ELIGIBLE` still cannot activate Gate 1. It may only proceed to the separately bounded campaign in issue #76 after explicit human review.

## Credential boundary

Allowed authentication modes:

```text
NONE
READ_ONLY_CREDENTIAL
```

A read-only credential reference must visibly contain `READ_ONLY` or `READONLY`. Wallet seeds, mnemonics, private keys, signing keys, trading secrets, order secrets, and wallet references fail closed.

## Build

Start from the non-live template:

```bash
cp \
  examples/telemetry/source_review_candidate_template_v0_1.json \
  /tmp/gate1-source-review-candidate.json
```

Build a deterministic artifact with an explicit timestamp and producer commit:

```bash
python -m eve_q.gate1_source_review build \
  --candidate /tmp/gate1-source-review-candidate.json \
  --producer-commit "$(git rev-parse HEAD)" \
  --created-at 2026-07-12T01:00:00Z \
  --output /tmp/gate1-source-review-artifact.json
```

Verify offline:

```bash
python -m eve_q.gate1_source_review verify \
  --artifact /tmp/gate1-source-review-artifact.json
```

The supplied template must build to `HOLD`. It is deliberately not a reviewed live source.

## Content address

`artifact_id` is SHA-256 over canonical UTF-8 JSON with sorted keys and compact separators after removing the `artifact_id` field itself.

Changing the endpoint, host allowlist, provenance assessment, legal review, risk disposition, reviewer, timestamp, or producer commit changes the artifact identity.

## Relationship to later work

```text
#77 source-review contract
→ #78 non-live soak scaffold
→ #76 reviewed bounded live campaign
→ #68 Gate 1 evidence decision
```

No earlier stage implies the next.

## Boundary

```text
source review artifact != live capture
ELIGIBLE != Gate 1 activation
successful verification != source truth
content address != legal permission
confidence != authority
```

Every artifact carries:

```json
{
  "artifact_is_command": false,
  "authority": false,
  "human_promotion_required": true,
  "may_activate_gate_1": false,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_move_capital": false
}
```

> Observation eligibility is a passport check, not permission to fly the aircraft.
