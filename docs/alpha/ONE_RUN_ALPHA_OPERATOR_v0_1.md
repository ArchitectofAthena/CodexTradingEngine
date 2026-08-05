# CodexTradingEngine One-Run Gate 1A Alpha Operator v0.1

## Purpose

`codex-alpha-run` carries the Gate 1A procedure through one summary-first operator surface without inheriting the authority of later gates.

It answers nine questions independently:

```text
PIPELINE
SOURCE
FRESHNESS
ECONOMICS
CLASSICAL_BASELINE
QAOA_COMPARISON
RUST_VERIFICATION
EXECUTION
ROLLBACK
```

A ready pipeline does not imply positive economics. Positive modeled economics does not imply execution permission. A QAOA result does not replace its exact classical comparison. Execution remains locked in every mode.

## Current expected status

The canonical source registry currently contains zero sources with `ELIGIBLE` disposition. Therefore:

```bash
codex-alpha-run status
```

correctly writes a report and exits with status 2 while showing:

```text
PIPELINE: HOLD
SOURCE: HOLD_NO_ELIGIBLE_SOURCE
EXECUTION: LOCKED
```

This is an evidence-bearing hold, not a software failure and not permission to invent a source.

## Status mode

Run:

```bash
codex-alpha-run status \
  --output-dir artifacts/alpha-status
```

The command:

1. runs the alpha doctor;
2. validates the canonical source registry;
3. reports eligible, hold, and rejected source counts;
4. records kill-switch and rollback posture;
5. emits JSON, Markdown, and a compact text summary.

Output:

```text
artifacts/alpha-status/alpha-report.json
artifacts/alpha-status/alpha-report.md
artifacts/alpha-status/alpha-summary.txt
```

The status command performs no network request.

## Simulate one exact-hash reviewed draft

After a source has separately earned `ELIGIBLE`, a Gate 1A snapshot has passed replay, and a draft has been reviewed for local simulation, run:

```bash
codex-alpha-run simulate-reviewed \
  --draft artifacts/<RUN_ID>-reviewed/reviewed-draft.json \
  --expected-draft-hash <64-character-draft-hash> \
  --cycle-id <bounded-cycle-id> \
  --producer-commit "$(git rev-parse HEAD)" \
  --output-dir artifacts/<RUN_ID>-alpha
```

The operator requires all of the following:

- the environment doctor is not on HOLD;
- the draft validates against the v0.1 schema;
- the immutable draft hash matches the supplied hash;
- the operator review binds that exact hash;
- review state is `REVIEWED_FOR_LOCAL_SIMULATION`;
- local simulation eligibility is true;
- no required economic assumption remains missing;
- the draft is fresh;
- the source is still `ELIGIBLE` in the current registry;
- the registry hash still matches the draft provenance;
- every authority field remains false;
- the local route fixture contains every field required by `codex-research`.

Any failed condition stops the procedure and emits a visible HOLD report.

## Simulation boundary

`simulate-reviewed` extracts only the immutable local route fixture and invokes the existing simulation-safe research path.

It does not:

- capture telemetry;
- generate a live proposal;
- open or inspect a wallet;
- sign a message;
- submit a transaction;
- broadcast to a chain;
- use flash liquidity;
- transfer charity funds;
- move capital.

The result remains local simulation evidence.

## QAOA comparison boundary

When QAOA evidence is absent, the operator reports:

```text
CLASSICAL_BASELINE: NOT_AVAILABLE
QAOA_COMPARISON: NOT_AVAILABLE
```

When QAOA evidence is present, an exact classical baseline must also be present. An unpaired QAOA result produces:

```text
CLASSICAL_BASELINE: HOLD_MISSING_CLASSICAL_PAIR
QAOA_COMPARISON: HOLD_UNPAIRED_QAOA
PIPELINE: HOLD
```

This prevents an experimental optimizer result from becoming a prestige badge without comparative evidence.

## Structured alpha report

Each run emits:

- exact repository commit and Python version;
- doctor status, holds, and warnings;
- source registry posture;
- source, network, snapshot, and draft hashes when present;
- exact reviewed draft hash;
- independent result states;
- linked simulation report paths;
- deterministic orchestration receipt hash;
- rollback and kill-switch status;
- reproduction command;
- expected-versus-observed placeholders for the filed alpha report;
- publication-safety guidance.

The orchestration receipt excludes run timestamps and output-directory paths from its stable evidence material, so identical evidence reproduces the same receipt hash.

## Dirty-tree research

A dirty working tree normally produces HOLD. For bounded private local research only:

```bash
codex-alpha-run --acknowledge-dirty status
```

This converts that one condition to a warning. It does not make the checkout reproducible or suitable for release evidence.

## Termux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'

codex-alpha-run status \
  --output-dir "$HOME/codex-alpha-status"
```

Keep snapshots, reviewed drafts, research receipts, and alpha reports private unless every included field is safe to disclose.

## Gate posture

```text
Gate 0  ACTIVE
Gate 1A ACTIVE FOR APPROVED ALPHA RUNS
Gate 1B LOCKED
Gate 2  LOCKED
Gate 3  LOCKED
Gates 4–6 LOCKED
```

```text
one command = procedure
one report = evidence
neither = authority
```
