"""Cross-platform alpha front door for CodexTradingEngine.

This module composes existing Gate 1A doctor, alpha status, deterministic
research, and focused verification surfaces. It performs no automatic network
capture and grants no wallet, signing, transaction, execution, or capital
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "alpha-activation"
BOUNDARY = {
    "artifact_is_command": False,
    "authority": False,
    "automatic_network_capture": False,
    "may_generate_live_proposal": False,
    "may_execute": False,
    "may_sign": False,
    "may_submit_transaction": False,
    "may_access_wallet": False,
    "may_move_capital": False,
    "automatic_merge": False,
    "human_promotion_required": True,
}
CHANNELS = {
    "cli": {
        "purpose": "Local alpha doctor, status, deterministic simulation, and verification.",
        "activate_posix": "./codex doctor",
        "activate_portable": "python codex doctor",
    },
    "gate1_testnet_read_only": {
        "purpose": "Explicit reviewed public-testnet observation.",
        "activate": "follow docs/alpha/ALPHA_TESTNET_QUICKSTART_v0_1.md",
        "automatic_capture": False,
        "wallet_required": False,
    },
    "offline_simulation": {
        "purpose": "Deterministic built-in or operator-supplied route research.",
        "activate": "python codex demo",
        "network": "none",
    },
    "spiralbloom_mcp": {
        "purpose": "Reviewed sibling-repository introspection and proposal membrane.",
        "activate": (
            "SPIRALBLOOM_ROOT=/path/to/spiralbloom-os "
            "CODEX_TRADING_ENGINE_ROOT=/path/to/CodexTradingEngine "
            "python /path/to/spiralbloom-os/tools/spiralbloom_mcp_server_v0_1.py"
        ),
        "transport": "stdio_json_rpc",
    },
    "ssh_termius": {
        "purpose": "Operate the Android or workstation host remotely.",
        "activate": "ssh <user>@<host>",
        "note": "Codex remains on the remote host; Termius is the console.",
    },
    "github": {
        "purpose": "CI, receipts, alpha reports, review, and explicit human promotion.",
        "activate": "push a feature branch and review the resulting checks",
        "authority": False,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def git_snapshot() -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "commit": None,
        "branch": None,
        "dirty": None,
    }
    if not shutil.which("git") or not (ROOT / ".git").exists():
        return result
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--short"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        )
        result.update(
            {
                "available": True,
                "commit": commit,
                "branch": branch,
                "dirty": dirty,
            }
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return result


def run_process(command: list[str], *, timeout: int = 600) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "command timed out",
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "command": command,
            "returncode": 127,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "timed_out": False,
        }


def json_payload(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def step(name: str, result: dict[str, Any]) -> dict[str, Any]:
    payload = json_payload(str(result.get("stdout", "")))
    return {
        "name": name,
        "returncode": int(result["returncode"]),
        "timed_out": bool(result["timed_out"]),
        "payload": payload,
        "stdout_tail": str(result.get("stdout", ""))[-3000:],
        "stderr_tail": str(result.get("stderr", ""))[-3000:],
    }


def doctor_command(*, as_json: bool = True) -> list[str]:
    command = [sys.executable, "-m", "eve_q.alpha_doctor"]
    if as_json:
        command.append("--json")
    return command


def status_command(output_dir: Path, *, as_json: bool = True) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "eve_q.alpha_operator",
        "--acknowledge-dirty",
    ]
    if as_json:
        command.append("--json")
    command.extend(["status", "--output-dir", str(output_dir)])
    return command


def demo_command(
    output_dir: Path,
    *,
    routes: Path | None = None,
    cycle_id: str = "alpha-frontdoor-demo-v0-1",
    as_json: bool = True,
) -> list[str]:
    commit = git_snapshot().get("commit") or "0" * 40
    command = [
        sys.executable,
        "-m",
        "eve_q.research_cli",
        "--cycle-id",
        cycle_id,
        "--producer-commit",
        str(commit),
        "--output-dir",
        str(output_dir),
    ]
    if routes is not None:
        command.extend(["--routes", str(routes)])
    if as_json:
        command.append("--json")
    return command


def verify_command(*, full: bool) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "--strict-markers",
    ]
    if full:
        command.extend(["-m", "not live", "tests/"])
    else:
        command.extend(
            [
                "tests/test_alpha_doctor_v0_1.py",
                "tests/test_alpha_operator_v0_1.py",
                "tests/test_research_cli_v0_1.py",
            ]
        )
    return command


def _safe_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    allowed = DEFAULT_OUTPUT.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise ValueError(f"refusing path outside {allowed}: {resolved}")
    return resolved


def _doctor_ready(payload: dict[str, Any] | None) -> bool:
    return bool(payload and payload.get("status") in {"READY", "READY_WITH_WARNINGS"})


def _status_ready(payload: dict[str, Any] | None) -> bool:
    surface = payload.get("result_surface") if payload else None
    return bool(
        isinstance(surface, dict)
        and surface.get("PIPELINE") == "READY"
        and surface.get("EXECUTION") == "LOCKED"
    )


def _demo_ready(payload: dict[str, Any] | None) -> bool:
    summary = payload.get("summary") if payload else None
    boundary = payload.get("boundary") if payload else None
    return bool(
        isinstance(summary, dict)
        and summary.get("pipeline") == "READY"
        and summary.get("execution") == "LOCKED"
        and isinstance(boundary, dict)
        and boundary.get("authority") is False
        and boundary.get("may_execute") is False
        and boundary.get("may_move_capital") is False
    )


def build_acceptance_receipt(
    *,
    steps: list[dict[str, Any]],
    generated_at: str,
    git_state: dict[str, Any],
) -> dict[str, Any]:
    by_name = {item["name"]: item for item in steps}
    returncodes_ok = all(
        by_name.get(name, {}).get("returncode") == 0
        for name in ("doctor", "status", "demo", "verify")
    )
    ready = (
        returncodes_ok
        and _doctor_ready(by_name.get("doctor", {}).get("payload"))
        and _status_ready(by_name.get("status", {}).get("payload"))
        and _demo_ready(by_name.get("demo", {}).get("payload"))
    )
    receipt: dict[str, Any] = {
        "artifact_type": "CodexAlphaAcceptanceReceipt",
        "contract_version": "codex_alpha_acceptance_v0.1",
        "generated_at": generated_at,
        "repository": "ArchitectofAthena/CodexTradingEngine",
        "source_commit": git_state.get("commit") or "0" * 40,
        "result": "READY" if ready else "HOLD",
        "channels": CHANNELS,
        "steps": steps,
        "git": git_state,
        "boundary": dict(BOUNDARY),
        "receipt_sha256": "0" * 64,
    }
    material = dict(receipt)
    material.pop("receipt_sha256")
    receipt["receipt_sha256"] = sha256_value(material)
    return receipt


def run_acceptance(
    output_dir: Path,
    *,
    generated_at: str | None = None,
    full_verify: bool = False,
) -> tuple[dict[str, Any], int]:
    output = _safe_output(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    steps = [
        step("doctor", run_process(doctor_command(), timeout=180)),
        step("status", run_process(status_command(output / "status"), timeout=180)),
        step("demo", run_process(demo_command(output / "demo"), timeout=300)),
        step("verify", run_process(verify_command(full=full_verify), timeout=1200)),
    ]
    receipt = build_acceptance_receipt(
        steps=steps,
        generated_at=generated_at or utc_now(),
        git_state=git_snapshot(),
    )
    receipt_path = output / "codex-alpha-acceptance.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt, 0 if receipt["result"] == "READY" else 2


def compost(output_dir: Path, *, apply: bool) -> dict[str, Any]:
    output = _safe_output(output_dir)
    exists = output.exists()
    files = sorted(str(path.relative_to(ROOT)) for path in output.rglob("*") if path.is_file()) if exists else []
    if apply and exists:
        shutil.rmtree(output)
    return {
        "artifact_type": "CodexAlphaCompostReceipt",
        "contract_version": "codex_alpha_compost_v0.1",
        "output_dir": str(output),
        "files": files,
        "applied": apply,
        "removed": bool(apply and exists),
        "boundary": dict(BOUNDARY),
    }


def emit(value: Any, *, as_json: bool) -> None:
    if as_json or not isinstance(value, str):
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        print(value)


def _relay(result: dict[str, Any]) -> int:
    if result["stdout"]:
        print(result["stdout"], end="")
    if result["stderr"]:
        print(result["stderr"], end="", file=sys.stderr)
    return int(result["returncode"])


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="codex",
        description="Cross-platform, simulation-first CodexTradingEngine alpha front door.",
    )
    subparsers = result.add_subparsers(dest="command", required=True)

    for name in ("channels", "ingest", "doctor", "renew"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--json", action="store_true")

    status = subparsers.add_parser("status")
    status.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT / "status")
    status.add_argument("--json", action="store_true")

    for name in ("demo", "regenerate"):
        demo = subparsers.add_parser(name)
        demo.add_argument("--routes", type=Path)
        demo.add_argument("--cycle-id", default="alpha-frontdoor-demo-v0-1")
        demo.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT / "demo")
        demo.add_argument("--json", action="store_true")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--full", action="store_true")

    for name in ("accept", "repeat"):
        accept = subparsers.add_parser(name)
        accept.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
        accept.add_argument("--generated-at")
        accept.add_argument("--full-verify", action="store_true")
        accept.add_argument("--json", action="store_true")

    compost_parser = subparsers.add_parser("compost")
    compost_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    compost_parser.add_argument("--apply", action="store_true")
    compost_parser.add_argument("--json", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "channels":
        emit({"channels": CHANNELS, "boundary": BOUNDARY}, as_json=args.json)
        return 0
    if args.command == "ingest":
        emit({"git": git_snapshot(), "boundary": BOUNDARY}, as_json=args.json)
        return 0
    if args.command in {"doctor", "renew"}:
        return _relay(run_process(doctor_command(as_json=args.json), timeout=180))
    if args.command == "status":
        return _relay(run_process(status_command(args.output_dir, as_json=args.json), timeout=180))
    if args.command in {"demo", "regenerate"}:
        return _relay(
            run_process(
                demo_command(
                    args.output_dir,
                    routes=args.routes,
                    cycle_id=args.cycle_id,
                    as_json=args.json,
                ),
                timeout=300,
            )
        )
    if args.command == "verify":
        return _relay(run_process(verify_command(full=args.full), timeout=1800))
    if args.command == "compost":
        try:
            receipt = compost(args.output_dir, apply=args.apply)
        except ValueError as exc:
            print(f"HOLD: {exc}", file=sys.stderr)
            return 2
        emit(receipt, as_json=args.json)
        return 0
    if args.command in {"accept", "repeat"}:
        try:
            receipt, exit_code = run_acceptance(
                args.output_dir,
                generated_at=args.generated_at,
                full_verify=args.full_verify,
            )
        except ValueError as exc:
            print(f"HOLD: {exc}", file=sys.stderr)
            return 2
        emit(receipt, as_json=args.json)
        return exit_code
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
