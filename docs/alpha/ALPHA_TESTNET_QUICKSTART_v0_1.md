# CodexTradingEngine Gate 1A Alpha Testnet Quickstart v0.1

## What is open now

```text
Gate 0  SIMULATION_ONLY: ACTIVE
Gate 1A TESTNET_READ_ONLY_ALPHA: ACTIVE FOR APPROVED ALPHA RUNS
Gate 1B MAINNET_READ_ONLY_TELEMETRY: LOCKED
Gate 2  LIVE_PROPOSAL_GENERATION: LOCKED
Gate 3  TESTNET_MANUAL_EXTERNAL: LOCKED
Gate 4–6: LOCKED
```

Gate 1A is a deliberately narrow descent. Approved alpha testers may observe bounded public data from blockchain **testnets**, replay the captured snapshot offline, translate observations into a local route fixture, run the existing simulation and verification path, and file a structured report.

Gate 1A does not open a wallet, use a seed phrase, sign a message, submit a transaction, generate a live proposal, touch mainnet, or move capital.

## The alpha path

```text
install
→ verify environment
→ run deterministic baseline
→ capture bounded public testnet observation
→ replay offline
→ build local route fixture
→ simulate and verify
→ read one summary report
→ file one structured alpha report
```

The capture membrane and the research CLI are separate on purpose. In v0.1, an alpha tester must explicitly translate an inspected observation into a local fixture. Live data does not flow directly into proposal generation.

## 1. Clone and install

Python 3.11 or 3.13 is recommended.

```bash
git clone https://github.com/ArchitectofAthena/CodexTradingEngine.git
cd CodexTradingEngine

python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

On Termux:

```bash
source .venv/bin/activate
```

Record the exact commit under test:

```bash
git rev-parse HEAD
```

## 2. Verify the local environment

Run the complete non-live suite before any network observation:

```bash
python -m pytest \
  -o addopts='' \
  --strict-markers \
  -m 'not live' \
  tests/
```

The alpha run is on HOLD if tests fail, the working tree contains unexplained changes, or the installed package does not resolve to the checked-out repository.

Useful checks:

```bash
git status --short
python --version
python -c 'import eve_q, pathlib; print(pathlib.Path(eve_q.__file__).resolve())'
```

Rust verifiers, when invoked by a workflow, must be compiled from this checkout or obtained from a reviewed release artifact with a published digest. Do not trust an unexplained local binary merely because it executes.

## 3. Run the deterministic baseline

```bash
codex-research \
  --cycle-id alpha-baseline-001 \
  --producer-commit "$(git rev-parse HEAD)" \
  --output-dir artifacts/alpha-baseline-001
```

Open:

```text
artifacts/alpha-baseline-001/research-report.md
artifacts/alpha-baseline-001/research-report.json
```

Interpret the three states independently:

```text
PIPELINE=READY
ECONOMICS=POSITIVE_EDGE | NO_POSITIVE_EDGE
EXECUTION=LOCKED
```

`PIPELINE=READY` is a software result. `ECONOMICS=POSITIVE_EDGE` is a modeled result for the supplied fixture. `EXECUTION=LOCKED` is the authority posture. None implies the others.

## 4. Choose a read-only public testnet source

Use a public HTTPS endpoint that exposes testnet market or chain observations through `GET` or `HEAD` and does not require a wallet or write-capable credential.

Good Gate 1A candidates include public testnet explorer APIs or public testnet data endpoints that provide bounded JSON or text responses.

Not eligible in Gate 1A:

- mainnet endpoints;
- endpoints requiring `POST`, signing, wallet authentication, or trading credentials;
- private, loopback, link-local, or IP-literal hosts;
- endpoints whose terms do not permit the intended use;
- sources with redirects outside the exact allowlist;
- payloads containing private user data;
- sources that cannot be identified and replayed.

Many blockchain JSON-RPC endpoints use `POST`. Those are outside the current Gate 1A transport contract even when the RPC method itself is read-only.

## 5. Create the source specification

```bash
cp \
  examples/telemetry/source_spec_template_v0_1.json \
  /tmp/codex-alpha-testnet-source.json
```

Edit only the bounded source fields:

```json
{
  "allowed_hosts": ["exact.public.testnet.host"],
  "freshness_ttl_seconds": 300,
  "max_response_bytes": 1048576,
  "source_id": "stable-testnet-source-id",
  "source_kind": "market_snapshot",
  "timeout_seconds": 10.0,
  "url": "https://exact.public.testnet.host/read-only-path"
}
```

The hostname in `allowed_hosts` must exactly match the URL hostname. Do not place API-key values, cookies, wallet material, or personal information in the file.

## 6. Capture and replay one bounded observation

```bash
export EVE_Q_GATE1_PILOT=1
unset EVE_Q_GATE1_KILL_SWITCH || true

RUN_ID="gate1a-alpha-$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="$HOME/codex-alpha-runs" \
RUN_ID="$RUN_ID" \
PRODUCER_COMMIT="$(git rev-parse HEAD)" \
  bash scripts/run_gate1_read_only_capture_v0_1.sh \
  /tmp/codex-alpha-testnet-source.json
```

The launcher performs DNS/IP preflight, bounded capture, offline replay, post-capture DNS verification, and rollback-receipt emission on a supported failure.

Expected output root:

```text
$HOME/codex-alpha-runs/$RUN_ID/
```

Keep the snapshot bundle local unless it contains only public data you are comfortable publishing.

## 7. Inspect before translating

Before using any value in a route fixture, record:

- testnet/network name;
- chain ID when known;
- source ID and exact host;
- retrieval timestamp and freshness TTL;
- raw and normalized SHA-256 hashes;
- units and decimal precision;
- whether the value is directly observed, transformed, or inferred;
- any missing fees, gas, liquidity, latency, or slippage assumptions.

A captured value is an observation, not an executable quote and not a profitability claim.

## 8. Build a local route fixture

Copy the public example:

```bash
cp examples/public_routes.example.json \
  artifacts/alpha-testnet-routes.json
```

Translate only the inspected testnet observations and explicit modeling assumptions into the fixture. Each route remains local input:

```json
{
  "route": "testnet-weth-usdc-weth",
  "chain": "named-public-testnet",
  "expected_profit_eth": "0.020",
  "gas_cost_eth": "0.005",
  "slippage_eth": "0.001",
  "safety_margin_eth": "0.002"
}
```

Do not copy mainnet balances, private account data, pending private transactions, or wallet-derived information into the fixture.

## 9. Run the alpha simulation

```bash
codex-research \
  --routes artifacts/alpha-testnet-routes.json \
  --cycle-id "$RUN_ID" \
  --producer-commit "$(git rev-parse HEAD)" \
  --output-dir "artifacts/$RUN_ID"
```

Review the single summary first:

```text
artifacts/$RUN_ID/research-report.md
```

Open underlying JSON or receipts only when the summary identifies a specific question. This keeps receipt volume available for audit without making the operator swim through every artifact.

Where QAOA evidence is present, compare it only with the exact classical result produced from the identical QUBO hash. If the classical method is faster, clearer, and equally effective for the fixture, report that directly. QAOA is an experimental comparison lane, not a required badge.

## 10. File one structured alpha report

Open a GitHub issue using **Alpha testnet report** and include:

- exact commit SHA;
- operating system and Python version;
- testnet/network and chain ID when known;
- public read-only source class and exact host;
- capture and research commands;
- summary status values;
- artifact IDs or hashes needed to reproduce the result;
- expected and observed behavior;
- whether rollback was exercised;
- whether the issue concerns workflow, economics, verification, environment trust, or boundary enforcement.

Do not publish secrets, wallet material, private logs, personally identifying data, or sensitive exploit details.

## Immediate stop and rollback

Activate the kill switch:

```bash
export EVE_Q_GATE1_KILL_SWITCH=1
```

A Gate 1A run must stop and return to Gate 0 when:

- DNS/IP policy fails;
- the source becomes stale, malformed, oversized, or unavailable;
- the host or redirect chain drifts;
- replay or hash verification fails;
- a write-capable credential is present;
- mainnet data enters the run;
- the environment or binary origin cannot be explained;
- any proposal, signing, transaction, or capital surface appears.

## Gate 3 preview: not active

A future Gate 3 alpha may permit an approved tester to manually recreate a reviewed proposal using faucet-only testnet funds in an isolated wallet. The engine would still not hold keys or submit the transaction.

That phase is not active in v0.1. It requires a separate reviewed implementation for:

- supported testnets and chain IDs;
- faucet-only value caps;
- isolated-wallet hygiene;
- per-action human promotion;
- transaction-hash and outcome receipts;
- failed-transaction and rollback handling;
- explicit separation between engine output and the tester's external action.

```text
Gate 1A observes.
Gate 2 may later propose.
Gate 3 may later permit a human to test externally.
No gate inherits the authority of the next.
```
