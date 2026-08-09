# Gate 1A.1 Rust Verifier Provenance Membrane v0.2

## Purpose

A verifier answer is admissible only when its binary and its validation law have reviewable, content-addressed origins.

```text
source commit or reviewed source digest
+ Cargo manifest and generated lock digests
+ exact executed build command
+ pinned rustc and cargo versions
+ package origin
+ target triple
+ clean-tree posture
+ binary SHA-256
+ packaged canonical response-schema SHA-256
+ full canonical response validation
+ request-derived identity binding
+ byte-identical replay
→ VERIFIED_RESEARCH_BINARY | HOLD_UNVERIFIED_BINARY
```

```text
binary exists != binary trusted
matching output != verified origin
schema-version string != schema-valid response
caller-provided schema != admission law
Rust verification != execution authority
```

## Canonical response law

The authoritative response schema remains repository source:

```text
schemas/delta_repricing_response.schema.json
```

An exact byte-for-byte mirror is packaged inside `eve_q`:

```text
eve_q/delta_repricing_response.schema.json
```

CI requires the two files to be identical. The packaged resource is included in the wheel so `codex-rust-verifier-provenance verify` can operate outside a repository checkout.

Manifest v0.2 records `response_schema_sha256`. Verification loads only the packaged canonical resource and requires its SHA-256 to match the reviewed manifest before validating any replay output.

There is no caller-selectable response-schema override in the verification path. A weaker external schema cannot redefine admission.

## Manifest v0.2

The manifest records:

- source commit;
- complete reviewed source-tree digest;
- `Cargo.toml` and generated `Cargo.lock` digests;
- canonical response-schema digest;
- the same replayable build command used for the first CI release build;
- `rustc` and `cargo` versions;
- package origin;
- binary SHA-256;
- target triple;
- clean or reviewed-digest tree posture;
- expected request and response schema versions.

The manifest is content-addressed. Changing the canonical schema digest changes the manifest identity.

## Deterministic build and replay proof

The CI lane:

1. pins Rust `1.85.0` and `x86_64-unknown-linux-gnu`;
2. copies verifier source into a temporary clean build context;
3. generates one dependency lock and records its digest;
4. records the complete build-A command, including reproducibility environment, target directory and manifest path;
5. executes that recorded command for build A;
6. builds the same release binary independently as build B;
7. requires identical binary SHA-256 values;
8. proves the source and packaged response schemas are byte-identical;
9. records the packaged canonical schema SHA-256 in the manifest;
10. runs the binary twice over the same bounded request;
11. requires byte-identical output;
12. validates the complete output against the packaged canonical schema;
13. binds request ID, snapshot hash, model hash, confidence receipt, candidate identity, edge identities, asset path and minimum margin back to the request;
14. validates generated manifest and replay report schemas.

The full simulation suite also builds a wheel, installs it into a clean virtual environment and requires the packaged response schema to be present and readable there.

## Fail-closed posture

`HOLD_UNVERIFIED_BINARY` is mandatory for:

- missing or malformed manifest;
- manifest identity mismatch;
- canonical schema digest mismatch;
- absent packaged canonical schema;
- source/package schema drift;
- unknown or dirty source posture;
- binary digest mismatch;
- missing source, toolchain, target, package, build or schema fields;
- request or response schema mismatch;
- incomplete or malformed verifier output;
- changed request-derived identity or route fields;
- deterministic replay divergence;
- authority escalation.

A deterministic binary and a permissive caller-supplied schema are never sufficient for admission.

## Boundary

```yaml
authority: false
artifact_is_command: false
may_execute: false
may_sign: false
may_submit_transaction: false
may_access_wallet: false
may_move_capital: false
gate1b_activated: false
human_promotion_required: true
```

> Provenance before trust. The validator's law is provenance too.
