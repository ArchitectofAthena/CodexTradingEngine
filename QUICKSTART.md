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
