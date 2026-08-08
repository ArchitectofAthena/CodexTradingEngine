# Gate 1A.1 Rust Verifier Provenance Membrane v0.1

## Purpose

A verifier answer is admissible only when its binary has a reviewable origin and deterministic replay chain.

```text
source commit or reviewed source digest
+ Cargo manifest and generated lock digests
+ exact build command
+ pinned rustc and cargo versions
+ package origin
+ target triple
+ clean-tree posture
+ binary SHA-256
+ expected input/output schemas
+ byte-identical replay
→ VERIFIED_RESEARCH_BINARY | HOLD_UNVERIFIED_BINARY
```

```text
binary exists != binary trusted
matching output != verified origin
Rust verification != execution authority
```

## Manifest

The manifest records:

- source commit;
- complete reviewed source-tree digest;
- `Cargo.toml` and generated `Cargo.lock` digests;
- exact build command and environment posture;
- `rustc` and `cargo` versions;
- package origin;
- binary SHA-256;
- target triple;
- clean or reviewed-digest tree posture;
- expected request and response schema versions.

The manifest is itself content-addressed. Re-sealing one changed field without updating the full manifest identity is rejected.

## Deterministic build proof

The CI lane:

1. pins Rust `1.85.0` and `x86_64-unknown-linux-gnu`;
2. copies the verifier source into a temporary clean build context;
3. generates one dependency lock and records its digest;
4. builds the same release binary in two isolated target directories with fixed reproducibility flags;
5. requires identical binary SHA-256 values;
6. emits the provenance manifest;
7. runs the binary twice over the same bounded request;
8. requires byte-identical output and the declared response schema;
9. validates generated manifest and replay report schemas.

The generated lock digest is invocation evidence. It does not silently rewrite the repository.

## Fail-closed posture

`HOLD_UNVERIFIED_BINARY` is mandatory for:

- missing manifest;
- manifest identity mismatch;
- unknown or dirty source posture;
- binary digest mismatch;
- missing source, toolchain, target, package, build, or schema fields;
- request or response schema mismatch;
- deterministic replay divergence;
- malformed output;
- authority escalation;
- changed request identity.

A binary that emits the expected numerical answer but fails provenance still holds.

## CLI

```bash
codex-rust-verifier-provenance emit-manifest \
  --source-commit "$SOURCE_COMMIT" \
  --source-tree-sha256 "$SOURCE_TREE_SHA" \
  --cargo-manifest-sha256 "$CARGO_MANIFEST_SHA" \
  --cargo-lock-sha256 "$CARGO_LOCK_SHA" \
  --build-command "$BUILD_COMMAND" \
  --rustc-version "$(rustc --version --verbose | tr '\n' ' ')" \
  --cargo-version "$(cargo --version --verbose | tr '\n' ' ')" \
  --package-origin "github:ArchitectofAthena/CodexTradingEngine@$SOURCE_COMMIT:rust/delta-verifier/Cargo.toml" \
  --binary "$BINARY" \
  --target-triple x86_64-unknown-linux-gnu \
  --tree-posture CLEAN \
  --input-schema-version delta-repricing-request-v0.1 \
  --output-schema-version delta-repricing-response-v0.1 \
  --output artifacts/gate1a1/rust-verifier-manifest.json

codex-rust-verifier-provenance verify \
  --manifest artifacts/gate1a1/rust-verifier-manifest.json \
  --binary "$BINARY" \
  --request tests/fixtures/gate1a1_rust_repricing_request_v0_1.json \
  --output artifacts/gate1a1/rust-verifier-report.json
```

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

> Provenance before trust. Replay before admission. Verification never becomes authority.
