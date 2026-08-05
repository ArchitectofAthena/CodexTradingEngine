# CodexTradingEngine Quickstart

This is the canonical public research path:

```text
install
→ provide local candidate routes or use the deterministic fixture
→ simulate
→ verify the receipt
→ receive one readable report
```

It never opens a wallet, signs a transaction, submits an order, broadcasts data to a chain, or moves capital.

Before describing or testing the larger vision, read [`docs/public/CURRENT_STATE_AND_TARGET_ARCHITECTURE_v0_1.md`](docs/public/CURRENT_STATE_AND_TARGET_ARCHITECTURE_v0_1.md). It separates implemented capability from target architecture, clarifies the experimental role of QAOA, and records which wallet, flash-loan, charity-transfer, and mainnet surfaces remain locked.

## Install

Python 3.11 or 3.13 is recommended.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

On Termux, activate with:

```bash
source .venv/bin/activate
```

## Explain the Gate 1A alpha environment

Before any public testnet observation, run:

```bash
codex-alpha-doctor
```

For machine-readable output:

```bash
codex-alpha-doctor --json
```

The doctor reports `READY`, `READY_WITH_WARNINGS`, or `HOLD` while keeping Gate 2, execution, signing, transactions, and capital locked.

The canonical registry now contains one time-bounded eligible source:

```text
ethereum-sepolia-blockscout-stats-v0-1
Ethereum Sepolia, chain ID 11155111
GET https://eth-sepolia.blockscout.com/api/v2/stats
Review expires 2026-09-04T01:12:00Z
```

A normal checkout without a configured Rust verifier reports `READY_WITH_WARNINGS`. The warning concerns unavailable Rust verification, not source eligibility.

Read [`docs/alpha/ALPHA_DOCTOR_AND_SOURCE_REGISTRY_v0_1.md`](docs/alpha/ALPHA_DOCTOR_AND_SOURCE_REGISTRY_v0_1.md) and the exact [source review receipt](docs/source-reviews/ETHEREUM_SEPOLIA_BLOCKSCOUT_STATS_v0_1.md).

## Run the deterministic built-in example

```bash
codex-research \
  --cycle-id public-demo-001 \
  --producer-commit 0000000000000000000000000000000000000000 \
  --output-dir artifacts/public-demo
```

The command prints three independent meanings:

```text
PIPELINE=READY | ECONOMICS=POSITIVE_EDGE | EXECUTION=LOCKED
```

- `PIPELINE=READY` means the local simulation and receipt-verification path completed.
- `ECONOMICS=POSITIVE_EDGE` means the selected fixture route remained positive after modeled costs.
- `EXECUTION=LOCKED` means there is still no wallet, signing, transaction, broadcast, or capital path.

Read:

```text
artifacts/public-demo/research-report.md
artifacts/public-demo/research-report.json
```

The cycle directory also contains the underlying receipt and non-authoritative proposal artifact.

## Run local route candidates

Copy the example:

```bash
cp examples/public_routes.example.json my-routes.json
```

Edit values, then run:

```bash
codex-research \
  --routes my-routes.json \
  --cycle-id my-local-study-001 \
  --producer-commit 0000000000000000000000000000000000000000 \
  --output-dir artifacts/my-local-study
```

Required route fields:

```json
{
  "route": "base-weth-usdc-weth",
  "chain": "base",
  "expected_profit_eth": "0.020",
  "gas_cost_eth": "0.005",
  "slippage_eth": "0.001",
  "safety_margin_eth": "0.002"
}
```

All values are local modeling inputs. They are not fetched prices, executable orders, or promises of recurrence.

## Approved alpha testnet path

The scoped Gate 1A alpha program is now documented for approved testers:

```text
public testnet observation
→ bounded capture
→ offline replay
→ explicit local fixture
→ simulation and verification
→ structured alpha report
```

Read [`docs/alpha/ALPHA_TESTNET_QUICKSTART_v0_1.md`](docs/alpha/ALPHA_TESTNET_QUICKSTART_v0_1.md).

Current alpha posture:

```text
Gate 1A TESTNET_READ_ONLY_ALPHA: ACTIVE FOR APPROVED ALPHA RUNS
Gate 1B MAINNET_READ_ONLY_TELEMETRY: LOCKED
Gate 2 LIVE_PROPOSAL_GENERATION: LOCKED
Gate 3 TESTNET_MANUAL_EXTERNAL: LOCKED
```

Gate 1A requires no wallet, seed phrase, signing key, write credential, or transaction. It uses public testnet observations only and preserves `EXECUTION=LOCKED`.

### Capture the reviewed Sepolia source

One explicit invocation performs one bounded GET, DNS/IP preflight, offline replay, post-capture DNS verification, and rollback receipt generation on supported failure:

```bash
export EVE_Q_GATE1_PILOT=1
unset EVE_Q_GATE1_KILL_SWITCH || true

RUN_ID="sepolia-blockscout-$(date -u +%Y%m%dT%H%M%SZ)" \
RUN_ROOT="$HOME/codex-alpha-runs" \
PRODUCER_COMMIT="$(git rev-parse HEAD)" \
  bash scripts/run_gate1_read_only_capture_v0_2.sh \
  registry/source_specs/ethereum_sepolia_blockscout_stats_v0_1.json
```

This source is observational. Its price-like fields are not executable quotes, and its testnet data is not production profitability evidence.

## Translate telemetry into a reviewed local draft

After a source has earned `ELIGIBLE` status and a Gate 1A bundle has passed replay, build a deterministic draft:

```bash
codex-telemetry-draft build \
  --bundle "$HOME/codex-alpha-runs/<RUN_ID>/snapshot" \
  --mapping examples/alpha/sepolia_blockscout_stats_mapping_v0_1.json \
  --assumptions examples/alpha/sepolia_blockscout_stats_assumptions_v0_1.json \
  --output-dir artifacts/<RUN_ID>-draft
```

The output keeps observed values, deterministic transformations, operator assumptions, and missing economic inputs in separate compartments. The first result remains `DRAFT_UNREVIEWED`, `LOCAL SIMULATION ELIGIBLE=false`, and `EXECUTION=LOCKED`.

An operator may review only the exact immutable draft hash:

```bash
codex-telemetry-draft review \
  --draft artifacts/<RUN_ID>-draft/draft.json \
  --expected-draft-hash <64-character-draft-hash> \
  --decision REVIEWED_FOR_LOCAL_SIMULATION \
  --reviewer "Architect" \
  --reviewed-at <UTC-DATE-TIME> \
  --note "Exact draft reviewed for local simulation only." \
  --output-dir artifacts/<RUN_ID>-reviewed
```

This review grants only local simulation eligibility. It does not invoke `codex-research`, create Gate 2 authority, sign anything, submit a transaction, or move capital.

Read [`docs/alpha/TELEMETRY_DRAFT_FIXTURE_ADAPTER_v0_1.md`](docs/alpha/TELEMETRY_DRAFT_FIXTURE_ADAPTER_v0_1.md).

## Carry the bounded alpha procedure in one command

The summary-first Gate 1A operator exposes nine independent states without widening authority:

```bash
codex-alpha-run status \
  --output-dir artifacts/alpha-status
```

With the current reviewed source and no configured Rust verifier, the expected status is:

```text
PIPELINE: READY
SOURCE: ELIGIBLE
FRESHNESS: NOT_RUN
ECONOMICS: NOT_RUN
CLASSICAL_BASELINE: NOT_RUN
QAOA_COMPARISON: NOT_RUN
RUST_VERIFICATION: NOT_RUN
EXECUTION: LOCKED
ROLLBACK: READY
```

After an exact-hash draft is reviewed for local simulation, run:

```bash
codex-alpha-run \
  --acknowledge-dirty \
  simulate-reviewed \
  --draft artifacts/<RUN_ID>-reviewed/reviewed-draft.json \
  --expected-draft-hash <64-character-draft-hash> \
  --cycle-id <bounded-cycle-id> \
  --producer-commit "$(git rev-parse HEAD)" \
  --output-dir artifacts/<RUN_ID>-alpha
```

The command validates the doctor, source eligibility, registry hash, draft hash, review binding, freshness, assumptions, route fields, and false-authority boundaries before invoking the simulation-safe research path. It emits one JSON report, one Markdown report, and one compact summary.

An unpaired QAOA result produces HOLD until an exact classical baseline accompanies it. No mode captures telemetry automatically, creates Gate 2 authority, signs, submits a transaction, executes, or moves capital.

Read [`docs/alpha/ONE_RUN_ALPHA_OPERATOR_v0_1.md`](docs/alpha/ONE_RUN_ALPHA_OPERATOR_v0_1.md).

## Verify the complete simulation-safe repository

```bash
python -m pytest \
  -o addopts='' \
  --strict-markers \
  -m 'not live' \
  tests/
```

GitHub's **Full Simulation Suite** runs the complete non-live suite on every pull request and every push to `main` using Python 3.11 and 3.13. It also compiles the isolated Rust verifiers and smoke-tests the built Python wheel in a clean environment.

## Report a useful failure

For the alpha program, use the **Alpha testnet report** issue form.

For other defects, include:

1. the exact command;
2. Python and operating-system versions;
3. the smallest local route fixture that reproduces the problem;
4. `research-report.json`, unless it contains information you do not wish to share;
5. whether the failure concerns pipeline mechanics, modeled economics, or boundary enforcement.

A failed experiment is evidence. It is not permission for the system to widen authority.
