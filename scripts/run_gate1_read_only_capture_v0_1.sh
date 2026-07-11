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

if [[ "${EVE_Q_GATE1_KILL_SWITCH:-0}" == "1" ]]; then
  echo "Gate 1 kill switch is active; remaining at Gate 0." >&2
  exit 1
fi

if [[ "${EVE_Q_GATE1_PILOT:-0}" != "1" ]]; then
  echo "Set EVE_Q_GATE1_PILOT=1 for an explicit pilot capture." >&2
  exit 1
fi

OUT="$RUN_ROOT/$RUN_ID"

python -m eve_q.live_read_only_telemetry \
  --capture "$SOURCE_SPEC" \
  --output-dir "$OUT" \
  --producer-commit "$PRODUCER_COMMIT"

python -m eve_q.live_read_only_telemetry \
  --replay "$OUT"

printf 'Gate 1 read-only pilot capture: PASS\n'
printf 'Run ID: %s\n' "$RUN_ID"
printf 'Output: %s\n' "$OUT"
