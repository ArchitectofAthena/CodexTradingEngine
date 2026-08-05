# CodexTradingEngine Gate 1A Alpha Doctor and Source Registry v0.1

## Purpose

The alpha doctor explains the local environment before any public testnet observation.

It answers three different questions without blending them:

1. Is this checkout and installed package explainable?
2. Has any public testnet source earned eligibility?
3. Does the engine have any authority to propose, sign, transact, execute, or move capital?

The third answer remains no.

## Install

From the repository root:

```bash
python -m pip install -e '.[test]'
```

On Termux, activate the same local virtual environment used for the rest of the alpha workflow before running the doctor.

## Run

Readable summary:

```bash
codex-alpha-doctor
```

Machine-readable output:

```bash
codex-alpha-doctor --json
```

Write the result to a local artifact:

```bash
codex-alpha-doctor --json --output artifacts/alpha-doctor.json
```

The command exits with status 2 when the result is `HOLD`. `READY` and `READY_WITH_WARNINGS` exit with status 0.

## Status meanings

### READY

The repository commit is known, the working tree is clean, the installed package resolves inside the checkout, no dangerous write-capable secret names are present, the kill switch is inactive, the source registry is valid, at least one source is eligible, and any configured Rust verifier has an explained origin.

`READY` does not authorize a network request. It only says the local preflight has no known hold.

### READY_WITH_WARNINGS

The environment is explainable, but one or more non-fatal limitations remain. The initial canonical registry intentionally has zero eligible sources, so the expected first result is `READY_WITH_WARNINGS` with public testnet capture still unavailable.

A missing Rust verifier is also a warning when no Rust workflow is being invoked.

### HOLD

A hold is emitted for conditions including:

- unknown repository state or invalid commit;
- installed `eve_q` package outside the checkout;
- unexplained dirty working tree;
- active Gate 1 kill switch;
- dangerous write-capable secret names;
- invalid source registry;
- configured Rust verifier with missing, unreadable, or unexplained origin.

The doctor reports secret names only. It never prints secret values.

## Dirty-tree acknowledgement

For bounded local research only, an operator may convert a dirty-tree hold into a warning:

```bash
codex-alpha-doctor --acknowledge-dirty
```

This does not make the modified checkout reproducible and should not be used for a release, shared result, or promotion decision.

## Rust verifier origin

No Rust binary is trusted merely because it executes.

A configured verifier is accepted only when either:

- its path resolves inside the checked-out repository; or
- it is outside the repository and its SHA-256 exactly matches the reviewed digest supplied in `EVE_Q_RUST_VERIFIER_SHA256`.

Configure an external reviewed artifact with:

```bash
export EVE_Q_RUST_VERIFIER_PATH=/absolute/path/to/verifier
export EVE_Q_RUST_VERIFIER_SHA256=<reviewed-64-character-sha256>
```

An absent verifier remains a warning. An unexplained configured verifier is a hold.

## Source registry

Canonical registry:

```text
registry/alpha_testnet_sources_v0_1.json
```

Schema:

```text
schemas/alpha_testnet_source_registry_v0_1.schema.json
```

The initial registry contains no sources. That is deliberate. A source does not become eligible because someone knows its URL or because it returns data.

An eligible source requires a reviewed testnet identity, chain ID, exact HTTPS host, GET or HEAD transport, freshness and response limits, unit conventions, terms and rate-limit review, provenance grouping, concentration-risk notes, review evidence, and explicit false authority fields.

Mainnet identifiers, POST methods, IP-literal hosts, embedded credentials, wallet requirements, signing, transaction submission, and capital movement are rejected.

## Gate boundary

The doctor itself performs no telemetry capture. It does not create a fixture, simulation, proposal, transaction, or charity transfer.

Its authority posture remains:

- Gate 0 active;
- Gate 1A active only for approved alpha runs;
- Gate 1B locked;
- Gate 2 locked;
- Gate 3 locked;
- Gates 4 through 6 locked;
- execution locked;
- capital locked.

## Next recursive slice

After a source earns eligibility, the next child of issue #118 is the deterministic telemetry-to-draft-fixture adapter. That adapter must preserve observed versus inferred fields, units, freshness, hashes, and missing economic assumptions while requiring explicit operator review before simulation.

> The doctor explains the feet. It does not take the step.
