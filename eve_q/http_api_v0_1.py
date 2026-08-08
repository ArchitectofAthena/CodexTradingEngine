"""Loopback-only HTTP/JSON API for CodexTradingEngine research surfaces.

The API exposes deterministic shadow research, proposal validation/construction,
and accounting-evidence evaluation. It grants no wallet, signing, broadcast,
transaction, order, execution, or capital authority.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import urllib.parse
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from eve_q import alpha_frontdoor, capital_action_gate, gate_descent, research_cli
from eveq_failsafe_receipt import FailsafeConfig, progressive_trust_increment_from_receipt
from shadow_cycle_runner import build_shadow_receipt

SERVER_NAME = "codex-trading-http-api"
SERVER_VERSION = "0.1.0"
CONTRACT_VERSION = "codex_trading_http_api.v0.1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8771
MAX_BODY_BYTES = 1_048_576

BOUNDARY = {
    "artifact_is_command": False,
    "authority": False,
    "automatic_network_capture": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_execute_trades": False,
    "may_sign": False,
    "may_broadcast": False,
    "may_submit_transaction": False,
    "may_access_wallet": False,
    "may_move_capital": False,
    "human_promotion_required": True,
}


class ApiError(RuntimeError):
    """Deterministic client-facing API error."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _with_boundary(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.update(BOUNDARY)
    return result


def validate_bind_host(host: str) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("HTTP API host must be a literal loopback IP address") from exc
    if not address.is_loopback:
        raise ValueError("HTTP API v0.1 refuses non-loopback bind addresses")
    return host


def peer_is_loopback(peer: str) -> bool:
    try:
        return ipaddress.ip_address(peer).is_loopback
    except ValueError:
        return False


def _validate_routes(routes: Any) -> list[dict[str, Any]] | None:
    if routes is None:
        return None
    if not isinstance(routes, list) or not routes:
        raise ApiError(HTTPStatus.BAD_REQUEST, "routes must be a non-empty JSON array")
    required = {
        "route",
        "chain",
        "expected_profit_eth",
        "gas_cost_eth",
        "slippage_eth",
        "safety_margin_eth",
    }
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(routes):
        if not isinstance(item, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, f"route candidate {index} must be an object")
        missing = sorted(required - set(item))
        if missing:
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                f"route candidate {index} is missing fields: {', '.join(missing)}",
            )
        if not isinstance(item.get("route"), str) or not item["route"].strip():
            raise ApiError(HTTPStatus.BAD_REQUEST, f"route candidate {index} has invalid route")
        if not isinstance(item.get("chain"), str) or not item["chain"].strip():
            raise ApiError(HTTPStatus.BAD_REQUEST, f"route candidate {index} has invalid chain")
        for field in required - {"route", "chain"}:
            try:
                Decimal(str(item[field]))
            except (ValueError, ArithmeticError) as exc:
                raise ApiError(
                    HTTPStatus.BAD_REQUEST,
                    f"route candidate {index} has invalid {field}",
                ) from exc
        normalized.append(dict(item))
    return normalized


def _shadow_report(body: dict[str, Any]) -> dict[str, Any]:
    cycle_id = body.get("cycle_id")
    if cycle_id is not None and (not isinstance(cycle_id, str) or not cycle_id.strip()):
        raise ApiError(HTTPStatus.BAD_REQUEST, "cycle_id must be a non-empty string when supplied")
    routes = _validate_routes(body.get("routes"))
    try:
        receipt = build_shadow_receipt(cycle_id=cycle_id, candidate_routes=routes)
        validation = progressive_trust_increment_from_receipt(
            FailsafeConfig(),
            receipt,
            production_mode=False,
        )
    except (RuntimeError, ValueError, TypeError, KeyError, ArithmeticError) as exc:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            f"shadow research failed closed: {type(exc).__name__}",
        ) from exc

    report = {
        "artifact_type": "CodexHttpShadowResearchReport",
        "contract_version": CONTRACT_VERSION,
        "summary": {
            "pipeline": "READY" if validation.valid else "HOLD",
            "economics": research_cli.economics_state(receipt.actual_profit_eth),
            "execution": "LOCKED",
            "mode": receipt.mode,
            "chain": receipt.chain,
            "selected_route": receipt.selected_route,
            "actual_profit_eth": str(receipt.actual_profit_eth),
            "charity_due_eth": str(receipt.charity_due_eth),
            "tx_hashes": list(receipt.tx_hashes),
        },
        "verification": {
            "receipt_valid": bool(validation.valid),
            "trust_increment_allowed": bool(validation.trust_increment_allowed),
            "findings": research_cli.json_value(getattr(validation, "findings", [])),
        },
        "receipt": research_cli.json_value(receipt),
        "persistence": {
            "written_to_disk": False,
            "proposal_written": False,
            "receipt_written": False,
        },
    }
    return _with_boundary(report)


def _validate_gate_descent(body: dict[str, Any]) -> dict[str, Any]:
    document = body.get("document")
    if not isinstance(document, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "document must be an object")
    now_value = body.get("now")
    try:
        now = gate_descent.parse_utc(now_value) if now_value is not None else None
        findings = gate_descent.validate_gate_descent(document, now=now)
        artifact_id = gate_descent.compute_artifact_id(document)
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"Gate descent document is invalid: {exc}") from exc
    return _with_boundary(
        {
            "artifact_type": "GateDescentValidationResult",
            "valid": not findings,
            "findings": findings,
            "computed_artifact_id": artifact_id,
            "promotion_performed": False,
        }
    )


def _build_gate_descent_draft(body: dict[str, Any]) -> dict[str, Any]:
    created_at = body.get("created_at")
    expires_at = body.get("expires_at")
    evidence = body.get("evidence", [])
    if not isinstance(created_at, str) or not isinstance(expires_at, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, "created_at and expires_at must be ISO-8601 strings")
    if not isinstance(evidence, list) or not all(isinstance(item, dict) for item in evidence):
        raise ApiError(HTTPStatus.BAD_REQUEST, "evidence must be an array of objects")
    try:
        draft = gate_descent.build_gate_0_to_1_draft(
            created_at=created_at,
            expires_at=expires_at,
            evidence=evidence,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"Could not build gate descent draft: {exc}") from exc
    return _with_boundary(
        {
            "artifact_type": "GateDescentDraftResult",
            "draft": draft,
            "written_to_disk": False,
            "promotion_performed": False,
        }
    )


def _evaluate_capital_completion(body: dict[str, Any]) -> dict[str, Any]:
    ledger_audit = body.get("ledger_audit")
    if not isinstance(ledger_audit, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "ledger_audit must be an object")
    try:
        certificate = capital_action_gate.build_completion_certificate(
            action_kind=body.get("action_kind"),
            target_status=body.get("target_status"),
            receipt_cid=body.get("receipt_cid"),
            ledger_audit=ledger_audit,
            source_receipt_cid=body.get("source_receipt_cid"),
            merkle_anchor_cid=body.get("merkle_anchor_cid"),
            require_merkle_anchor=body.get("require_merkle_anchor", False),
        )
    except (TypeError, ValueError, capital_action_gate.CapitalActionGateError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"Capital completion evidence failed closed: {exc}") from exc
    return _with_boundary(
        {
            "artifact_type": "CapitalCompletionEvaluationResult",
            "eligible_for_accounting_record": True,
            "certificate": certificate,
            "transaction_submitted": False,
            "transaction_settled_by_api": False,
        }
    )


def _channels() -> dict[str, Any]:
    channels = dict(alpha_frontdoor.CHANNELS)
    channels["http_api"] = {
        "purpose": "Local JSON/HTTP access to bounded research and validation surfaces.",
        "activate": "python -m eve_q.http_api_v0_1",
        "transport": "http_json",
        "default_url": f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",
        "localhost_only": True,
        "authority": False,
    }
    return _with_boundary(
        {
            "artifact_type": "CodexInterfaceChannels",
            "contract_version": CONTRACT_VERSION,
            "channels": channels,
        }
    )


def _openapi() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "CodexTradingEngine HTTP API",
            "version": SERVER_VERSION,
            "description": "Loopback-only simulation and validation API; execution remains locked.",
        },
        "servers": [{"url": f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"}],
        "paths": {
            "/v1/health": {"get": {"summary": "API health and boundary"}},
            "/v1/channels": {"get": {"summary": "Available operator channels"}},
            "/v1/research/shadow": {"post": {"summary": "Run one in-memory shadow research cycle"}},
            "/v1/gate-descent/validate": {"post": {"summary": "Validate a gate-descent artifact"}},
            "/v1/gate-descent/draft": {"post": {"summary": "Build a proposal-only gate-descent draft"}},
            "/v1/capital-completion/evaluate": {"post": {"summary": "Evaluate accounting evidence only"}},
            "/v1/openapi.json": {"get": {"summary": "Return this OpenAPI document"}},
        },
    }


def dispatch(
    method: str,
    path: str,
    query: dict[str, list[str]],
    body: dict[str, Any] | None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    del query
    if method == "GET" and path == "/v1/openapi.json":
        return HTTPStatus.OK, _openapi()
    if method == "GET" and path == "/v1/health":
        return HTTPStatus.OK, _with_boundary(
            {
                "artifact_type": "CodexHttpApiHealth",
                "contract_version": CONTRACT_VERSION,
                "server": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "status": "READY",
                "transport": "http_json",
                "localhost_only": True,
                "execution": "LOCKED",
                "mode": "simulation_and_validation_only",
            }
        )
    if method == "GET" and path == "/v1/channels":
        return HTTPStatus.OK, _channels()
    if method == "POST":
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON object body required")
        if path == "/v1/research/shadow":
            return HTTPStatus.OK, _shadow_report(body)
        if path == "/v1/gate-descent/validate":
            return HTTPStatus.OK, _validate_gate_descent(body)
        if path == "/v1/gate-descent/draft":
            return HTTPStatus.OK, _build_gate_descent_draft(body)
        if path == "/v1/capital-completion/evaluate":
            return HTTPStatus.OK, _evaluate_capital_completion(body)
    raise ApiError(HTTPStatus.NOT_FOUND, "unknown API route")


class CodexHttpApiHandler(BaseHTTPRequestHandler):
    server_version = f"{SERVER_NAME}/{SERVER_VERSION}"

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _authorize_peer(self) -> bool:
        if peer_is_loopback(self.client_address[0]):
            return True
        self._send_json(
            _with_boundary({"ok": False, "error": "trusted loopback clients only"}),
            HTTPStatus.FORBIDDEN,
        )
        return False

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ApiError(HTTPStatus.LENGTH_REQUIRED, "Content-Length required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid Content-Length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body exceeds 1 MiB")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "body must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON object body required")
        return payload

    def _handle(self, method: str) -> None:
        if not self._authorize_peer():
            return
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        body: dict[str, Any] | None = None
        try:
            if method == "POST":
                body = self._read_json_body()
            status, payload = dispatch(method, parsed.path, query, body)
            self._send_json(payload, status)
        except ApiError as exc:
            self._send_json(_with_boundary({"ok": False, "error": exc.message}), exc.status)
        except Exception as exc:  # fail closed and redact internals
            self._send_json(
                _with_boundary({"ok": False, "error": f"internal failure: {type(exc).__name__}"}),
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    host = validate_bind_host(host)
    if not 1 <= port <= 65535:
        raise ValueError("port must be in range 1..65535")
    server = ThreadingHTTPServer((host, port), CodexHttpApiHandler)
    try:
        print(f"CodexTradingEngine HTTP API v0.1 at http://{host}:{port}")
        print("Boundary: localhost only; simulation/validation only; execution LOCKED.")
        server.serve_forever()
    finally:
        server.server_close()
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="codex-http-api")
    result.add_argument("--host", default=os.environ.get("CODEX_API_HOST", DEFAULT_HOST))
    result.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CODEX_API_PORT", str(DEFAULT_PORT))),
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return serve(args.host, args.port)
    except (OSError, ValueError) as exc:
        print(f"CodexTradingEngine HTTP API failed: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
