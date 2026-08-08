# CodexTradingEngine HTTP API v0.1

## Outcome

`eve_q/http_api_v0_1.py` adds a loopback-only JSON/HTTP interface for deterministic EVE_Q++ research and reviewed proposal/evidence surfaces.

The API is intentionally **simulation and validation only**. It grants no wallet, signing, broadcast, transaction, order, execution, or capital authority.

## Why this exists

Codex already supports:

- local CLI / Termux
- alpha front door commands
- reviewed SpiralBloom MCP access over stdio JSON-RPC
- SSH / Termius
- GitHub review / CI

HTTP adds a general integration membrane for native mobile apps, desktop clients, Python/JS clients, dashboards, notebooks, and future shells without forcing those clients to invoke a local shell command.

## Boundary

Every operational result restates:

```json
{
  "artifact_is_command": false,
  "authority": false,
  "automatic_network_capture": false,
  "may_generate_live_proposal": false,
  "may_execute": false,
  "may_execute_trades": false,
  "may_sign": false,
  "may_broadcast": false,
  "may_submit_transaction": false,
  "may_access_wallet": false,
  "may_move_capital": false,
  "human_promotion_required": true
}
```

v0.1 refuses non-loopback bind addresses. It is not a remotely exposed trading API.

## Endpoints

| Method | Path | Effect |
| --- | --- | --- |
| GET | `/v1/health` | API health and execution-lock boundary |
| GET | `/v1/channels` | List current operator/interface channels, including HTTP |
| POST | `/v1/research/shadow` | Run one in-memory deterministic shadow research cycle |
| POST | `/v1/gate-descent/validate` | Validate a Gate 0 to Gate 1 proposal in memory |
| POST | `/v1/gate-descent/draft` | Build a proposal-only Gate 0 to Gate 1 draft in memory |
| POST | `/v1/capital-completion/evaluate` | Evaluate receipt-ledger accounting evidence in memory |
| GET | `/v1/openapi.json` | Minimal OpenAPI 3.1 contract |

There are no live trade endpoints.

## Run

From the CodexTradingEngine repository root:

```bash
python -m eve_q.http_api_v0_1
```

Default bind:

```text
http://127.0.0.1:8771
```

Optional loopback-only overrides:

```bash
CODEX_API_HOST=127.0.0.1 \
CODEX_API_PORT=8771 \
python -m eve_q.http_api_v0_1
```

A non-loopback host such as `0.0.0.0` fails closed.

## Examples

Health:

```bash
curl -s http://127.0.0.1:8771/v1/health | python -m json.tool
```

Built-in deterministic shadow cycle:

```bash
curl -s \
  -H 'Content-Type: application/json' \
  -d '{}' \
  http://127.0.0.1:8771/v1/research/shadow \
  | python -m json.tool
```

Operator-supplied local candidate:

```bash
curl -s \
  -H 'Content-Type: application/json' \
  -d '{
    "cycle_id": "example-api-cycle",
    "routes": [{
      "route": "mock-route",
      "chain": "base",
      "expected_profit_eth": "0.010",
      "gas_cost_eth": "0.002",
      "slippage_eth": "0.001",
      "safety_margin_eth": "0.001"
    }]
  }' \
  http://127.0.0.1:8771/v1/research/shadow \
  | python -m json.tool
```

The shadow endpoint is in-memory in v0.1. It does not write a receipt, write a proposal, broadcast a transaction, or move capital.

## Relation to the CLI

The HTTP surface reuses the same research primitives used by `eve_q.research_cli` and `shadow_cycle_runner` instead of creating a separate trading engine.

```text
EVE_Q++ research primitives
        |
        +-> CLI / alpha front door
        +-> HTTP JSON
        +-> SpiralBloom MCP membrane
```

The transport changes. The execution boundary does not.

## Validation

```bash
python -m py_compile eve_q/http_api_v0_1.py
pytest -q tests/test_http_api_v0_1.py
```

## Remote-access phase is separate

A future remote phase should require, at minimum:

1. explicit authentication
2. encrypted transport or a reviewed private tunnel
3. rate limits and request quotas
4. origin / client policy
5. audit logging
6. scoped capabilities
7. independent review before any non-loopback bind

Remote addressability must not become implicit trade authority.

## Root law

Telemetry before autonomy. Profit is throughput. Charity is the geodesic. Addressability is not execution.
