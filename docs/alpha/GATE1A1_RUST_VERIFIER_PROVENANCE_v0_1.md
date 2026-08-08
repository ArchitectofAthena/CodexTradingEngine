# Gate 1A.1 Rust Verifier Provenance Membrane v0.1

## Purpose

A verifier answer is admissible only when its binary has a reviewable origin and deterministic replay chain.

```text
source commit or reviewed source digest
+ Cargo manifest and generated lock digests
+ exact executed build command
+ pinned rustc and cargo versions
+ package origin
+ target triple
+ clean-tree posture
+ binary SHA-256
+ full response-schema validation
+ request-derived identity binding
+ byte-identical replay
→ VERIFIED_RESEARCH_BINARY | HOLD_UNVERIFIED_BINARY
```

```text
binary exists != binary trusted
matching output != verified origin
schema-version string != schema-valid response
Rust verification != execution authority
```

## Manifest

The manifest records:

- source commit;
- complete reviewed source-tree digest;
- `Cargo.toml` and generated `Cargo.lock` digests;
- the same replayable build command used for the first CI release build;
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
4. records a complete build command containing the fixed reproducibility environment, `CARGO_TARGET_DIR`, `--manifest-path`, lock posture, binary name, and target;
5. executes that recorded command for build A;
6. builds the same release binary independently as build B;
7. requires identical binary SHA-256 values;
8. emits the provenance manifest;
9. runs the binary twice over the same bounded request;
10. requires byte-identical output;
11. validates the complete output against `schemas/delta_repricing_response.schema.json`;
12. binds `request_id`, snapshot hash, model hash, confidence receipt, candidate identity, edge identities, asset path, and minimum margin back to the request;
13. validates generated manifest and replay report schemas.

The generated lock digest is invocation evidence. It does not silently rewrite the repository.

## Exact replay command

The recorded command is executable as written and includes the source and target locations actually used for build A:

```bash
SOURCE_DATE_EPOCH=0 \
CARGO_INCREMENTAL=0 \
RUSTFLAGS='-C strip=symbols -C debuginfo=0' \
CARGO_TARGET_DIR=/tmp/target-a \
cargo build \
  --manifest-path /tmp/build-a/Cargo.toml \
  --locked \
  --release \
  --bin codex-delta-verifier \
  --target x86_64-unknown-linux-gnu
```

## Replay response admission

A response cannot earn `VERIFIED_RESEARCH_BINARY` from a matching schema-version string alone.

The membrane first validates the whole response document against the repository's canonical delta repricing response schema, including required identifiers, verifier status, nested verification result, numerical field types, and both authority-false locks. It then checks that request-derived identity fields and route fields are unchanged from the input.

This prevents a deterministic but incomplete, malformed, or identity-spoofed response from being promoted as verified provenance evidence.

## Fail-closed posture

`HOLD_UNVERIFIED_BINARY` is mandatory for:

- missing manifest;
- manifest identity mismatch;
- unknown or dirty source posture;
- binary digest mismatch;
- missing source, toolchain, target, package, build, or schema fields;
- missing or invalid canonical response schema;
- request or response schema mismatch;
- incomplete or malformed verifier output;
- changed request, snapshot, model, confidence, candidate, edge, asset-path, or minimum-margin identity;
- deterministic replay divergence;
- authority escalation.

A binary that emits a plausible numerical answer but fails provenance still holds.

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
  --response-schema schemas/delta_repricing_response.schema.json \
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
