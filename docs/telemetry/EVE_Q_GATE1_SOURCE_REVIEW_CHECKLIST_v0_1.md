# EVE_Q++ Gate 1 Source Review Checklist v0.1

Review every live telemetry source before adding it to a pilot source specification.

## Transport

- [ ] HTTPS only.
- [ ] `GET` or `HEAD` only.
- [ ] Exact hostname recorded in `allowed_hosts`.
- [ ] Redirect behavior inspected.
- [ ] No write-capable SDK or websocket command channel required.
- [ ] Timeout and response-size cap chosen.

## Credential posture

- [ ] Public unauthenticated source, or credential is demonstrably read-only.
- [ ] No wallet seed, private key, signing key, trading key, or order key present.
- [ ] Credential is not stored in the source-spec file.
- [ ] Environment variable name clearly states read-only posture.

## Data posture

- [ ] Source kind selected correctly.
- [ ] Freshness TTL justified.
- [ ] Content type supported.
- [ ] Payload can be replayed offline.
- [ ] Raw and normalized hashes will be recorded.
- [ ] Source limitations and known conflicts documented.

## Authority posture

- [ ] Snapshot is not a command.
- [ ] Snapshot cannot generate a live proposal.
- [ ] Snapshot cannot execute.
- [ ] Snapshot cannot move capital.
- [ ] Gate 2–6 remain locked.
- [ ] Explicit human promotion remains required before Gate 1 activation.

## Operator sign-off

```text
Source ID:
Reviewed URI:
Exact host:
Reviewer:
Review time:
Decision: APPROVE_FOR_PILOT / HOLD / REJECT
Reason:
```
