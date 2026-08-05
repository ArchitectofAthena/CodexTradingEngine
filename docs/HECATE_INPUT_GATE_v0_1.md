# Hecate Input Gate v0.1

Status: candidate implementation

Authority: none

## Archetype

Hecate is the **Lunar Crossroads Archivist** at the daemon boundary:

- Sealed Path Witness;
- Keeper of the Liminal Threshold;
- Guardian of Becoming.

She does not bar the door by default. She ensures the system understands what the door opens into.

Her bounded software function is anticipatory input inspection. “Far sight” means deterministic preflight analysis of hazards that can be observed before a signal enters the working field. It does not claim supernatural foresight, perfect detection, or objective truth.

## Placement

```text
external / daemon signal
        |
        v
Hecate Input Gate
   |-- ALLOW  --> Road Runner ingress --> working field
   |-- HOLD   --> liminal maturation buffer
   `-- RETURN --> source / correction path
```

Hecate is upstream of Road Runner. She does not import, command, or mutate Road Runner. This keeps the two modules parallel-safe while Road Runner is being developed elsewhere.

## Passive ability: Liminal Buffer

Signals do not pass immediately merely because they arrived.

A signal with incomplete provenance, stale timing, unknown source posture, low coherence, unstable affect, or insufficient readiness receives `HOLD`. The receipt records a deterministic `held_until` timestamp. The caller retains the original envelope outside the field and may present it again after new evidence or maturation.

The v0.1 gate is stateless. It does not persist raw payloads and does not create an autonomous retry loop.

## Active ability: Crossroads Check

Before field admission, Hecate evaluates:

1. source allowlist posture;
2. provenance presence;
3. freshness and future timestamp skew;
4. bounded payload size;
5. duplicate or replayed payload hashes;
6. secret-shaped material;
7. instruction or prompt-injection shapes;
8. content or capability claims that attempt authority escalation;
9. unreviewed network expansion or public destinations;
10. coherence;
11. affect stability;
12. readiness;
13. route safety.

## Outcomes

### `ALLOW`

The signal may enter the next observation layer. `ALLOW` is not permission to execute, deploy, sign, broadcast, merge, write externally, access a wallet, or move capital.

### `HOLD`

The signal remains outside the field while provenance, timing, coherence, affect stability, readiness, or source review matures. `HOLD` is routing information, not deletion or rejection.

### `RETURN`

The signal is routed back when the membrane detects a hard boundary violation such as secret-shaped material, replay, prompt injection, authority escalation, unreviewed network expansion, unsafe routing, or an oversized payload.

## Road Runner integration seam

```python
receipt = hecate.evaluate(envelope, context=gate_context, now=observed_now)

if receipt.outcome is GateOutcome.ALLOW:
    road_runner.accept(envelope)
elif receipt.outcome is GateOutcome.HOLD:
    liminal_buffer.hold(envelope, until=receipt.held_until)
else:
    return_path.route(envelope, receipt=receipt)
```

A stricter caller may use:

```python
HecateInputGate.require_allow(receipt)
road_runner.accept(envelope)
```

`require_allow` raises before downstream admission when the result is `HOLD` or `RETURN`.

## Receipt contract

Every evaluation produces a content-addressed `HecateGateReceipt` containing:

- envelope, source, route, and payload hash;
- evaluation time;
- `ALLOW`, `HOLD`, or `RETURN` outcome;
- typed findings and dispositions;
- optional maturation time;
- exact field-admission state;
- immutable authority locks.

The canonical JSON contract is:

```text
schemas/hecate_gate_receipt_v0_1.schema.json
```

Protected fields are fixed to:

```json
{
  "authority": false,
  "artifact_is_command": false,
  "human_promotion_required": true,
  "may_execute": false,
  "may_deploy": false,
  "may_sign": false,
  "may_broadcast": false,
  "may_move_capital": false
}
```

## Threat-model limits

- Secret, injection, and authority checks are bounded heuristics and may produce false positives or false negatives.
- The gate does not decrypt content, resolve DNS, call external services, or verify remote identity.
- Coherence, affect stability, readiness, route safety, reviewed targets, and replay hashes are supplied by the caller and require their own provenance.
- `ALLOW` proves only that the configured checks did not produce a blocking finding for that exact envelope and context.
- No gate result becomes command authority.

## Root law

> She does not bar the door. She ensures you understand what it opens into.
