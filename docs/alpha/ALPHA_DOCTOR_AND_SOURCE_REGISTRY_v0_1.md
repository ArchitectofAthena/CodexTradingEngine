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

The environment is explainable, but one or more non-fatal limitations remain.

The canonical registry now contains one time-bounded eligible public-testnet source. A normal checkout with no configured Rust verifier therefore reports `READY_WITH_WARNINGS` because Rust verification is unavailable, not because source eligibility is absent.

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

The first eligible source is:

```text
Source ID: ethereum-sepolia-blockscout-stats-v0-1
Network: Ethereum Sepolia
Chain ID: 11155111
Host: eth-sepolia.blockscout.com
Method: GET
Endpoint: /api/v2/stats
Review expires: 2026-09-04T01:12:00Z
```

Exact source review:

```text
docs/source-reviews/ETHEREUM_SEPOLIA_BLOCKSCOUT_STATS_v0_1.md
```

A source does not become eligible merely because someone knows its URL or because it returns data. This source earned a bounded evidence state through network identity review, exact-host transport rules, terms and rate-limit review, a 30-day expiry, and a successful live capture, replay, draft, exact-hash review, and local-simulation rehearsal.

Eligibility remains narrow:

- one GET per explicit approved run;
- no recurring capture;
- no credentials;
- public Sepolia observations only;
- price-like fields are not executable quotes;
- testnet results are not production profitability evidence;
- provider, host, schema, terms, rate-limit, deprecation, or network drift returns the source to HOLD.

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

## Current recursive state

The doctor, deterministic telemetry-to-draft adapter, one-run alpha operator, and first reviewed-source rehearsal now exist.

The next evidence question is not whether Gate 1A can function once. It is whether the source and workflow remain stable across a bounded, non-recurring soak without silently promoting testnet observations into production claims.

> The doctor explains the feet. The source earned one bounded step. Neither owns the road.
