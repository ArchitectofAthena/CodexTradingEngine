#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 SOURCE_SPEC.json" >&2
  exit 2
fi

SOURCE_SPEC="$1"
: "${RUN_ROOT:=$HOME/spiralbloom-runs}"
: "${RUN_ID:=gate1-pilot-$(date -u +%Y%m%dT%H%M%SZ)}"
: "${PRODUCER_COMMIT:=$(git rev-parse HEAD)}"

OUT="$RUN_ROOT/$RUN_ID"
BUNDLE="$OUT/snapshot"
RESOLUTION_RECEIPT="$OUT/resolution_receipt.json"
ROLLBACK_RECEIPT="$OUT/rollback_receipt.json"
mkdir -p "$OUT"

write_rollback() {
  local trigger="$1"
  python -m eve_q.gate1_hardening \
    --write-rollback-receipt "$ROLLBACK_RECEIPT" \
    --producer-commit "$PRODUCER_COMMIT" \
    --trigger "$trigger"

  python -m eve_q.gate1_hardening \
    --validate-rollback-receipt "$ROLLBACK_RECEIPT"
}

if [[ "${EVE_Q_GATE1_KILL_SWITCH:-0}" == "1" ]]; then
  write_rollback "kill_switch"
  echo "Gate 1 kill switch is active; rollback receipt recorded." >&2
  echo "Remaining at Gate 0 simulation-only." >&2
  exit 1
fi

if [[ "${EVE_Q_GATE1_PILOT:-0}" != "1" ]]; then
  echo "Set EVE_Q_GATE1_PILOT=1 for an explicit pilot capture." >&2
  exit 1
fi

if ! python -m eve_q.gate1_hardening \
  --preflight-source "$SOURCE_SPEC" \
  --receipt-out "$RESOLUTION_RECEIPT" \
  --producer-commit "$PRODUCER_COMMIT"
then
  write_rollback "dns_policy_failure"
  echo "Gate 1 DNS/IP policy failed closed." >&2
  exit 1
fi

if ! python -m eve_q.live_read_only_telemetry \
  --capture "$SOURCE_SPEC" \
  --output-dir "$BUNDLE" \
  --producer-commit "$PRODUCER_COMMIT"
then
  write_rollback "source_outage"
  echo "Gate 1 source capture failed closed." >&2
  exit 1
fi

if ! python -m eve_q.live_read_only_telemetry \
  --replay "$BUNDLE"
then
  write_rollback "operator_abort"
  echo "Gate 1 offline replay failed closed." >&2
  exit 1
fi

if ! python -m eve_q.gate1_hardening \
  --verify-resolution-receipt "$RESOLUTION_RECEIPT" \
  --source-spec "$SOURCE_SPEC"
then
  write_rollback "dns_policy_failure"
  echo "Gate 1 post-capture DNS verification failed closed." >&2
  exit 1
fi

printf 'Gate 1 read-only pilot capture: PASS\n'
printf 'Run ID: %s\n' "$RUN_ID"
printf 'Output: %s\n' "$OUT"
printf 'Snapshot: %s\n' "$BUNDLE"
printf 'Resolution receipt: %s\n' "$RESOLUTION_RECEIPT"
