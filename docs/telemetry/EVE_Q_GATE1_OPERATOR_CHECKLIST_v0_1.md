# EVE_Q++ Gate 1 Operator Checklist v0.1

## Before capture

- [ ] On `feat/eve-q-live-read-only-telemetry-v0-1` or later reviewed branch.
- [ ] Source review checklist completed.
- [ ] Source URL is HTTPS and host exactly matches the allowlist.
- [ ] Source is public or credential is demonstrably read-only.
- [ ] No wallet, seed, private key, signing key, trading key, or order key is present.
- [ ] `EVE_Q_GATE1_KILL_SWITCH` is unset or `0`.
- [ ] `EVE_Q_GATE1_PILOT=1` is set intentionally.
- [ ] Output directory is outside the repository.

## During capture

- [ ] Only `GET` or `HEAD` is used.
- [ ] Timeout and response-size bounds remain active.
- [ ] No redirect escapes the exact host allowlist.
- [ ] No live proposal is generated.
- [ ] No execution or capital interface is invoked.

## After capture

- [ ] `snapshot.json`, `raw.bin`, and `normalized.json` exist.
- [ ] Offline replay passes.
- [ ] Freshness behavior is checked.
- [ ] Snapshot hashes are recorded.
- [ ] Any failure is preserved without rewriting evidence.
- [ ] Kill-switch rollback is tested before Gate 1 review.

## Stop immediately when

- source or credential posture is uncertain;
- any write-capable secret is detected;
- any method other than `GET`/`HEAD` appears;
- Gate 2 or later behavior becomes reachable;
- snapshot integrity or freshness cannot be proven.
