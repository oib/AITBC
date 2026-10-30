#!/usr/bin/env bash
# run.sh — stress driver: run.sh <script|all> [--times N] [--until-fail]
#          [--lane serial|parallel] [--include-once] [play args...]
set -euo pipefail
cd "$(dirname "$0")"
SEL="${1:?usage: run.sh <script|all> [opts] [play args]}"; shift
TIMES=1; UNTIL_FAIL=0; LANE=""; INCLUDE_ONCE=0
PASS=()
while [ $# -gt 0 ]; do case "$1" in
  --times) TIMES="$2"; shift 2;;
  --until-fail) UNTIL_FAIL=1; shift;;
  --lane) LANE="$2"; shift 2;;
  --include-once) INCLUDE_ONCE=1; shift;;
  *) PASS+=("$1"); shift;;
esac; done

scripts_for() {
  for f in plays/[0-9]*.sh; do
    [ -e "$f" ] || continue
    lane=$(sed -n 's/^# *LANE: *//p' "$f" | head -1)
    mode=$(sed -n 's/^# *MODE: *//p' "$f" | head -1)
    [ -n "$LANE" ] && [ "$lane" != "$LANE" ] && continue
    [ "$mode" = "once" ] && [ "$INCLUDE_ONCE" = 0 ] && [ "${STRESS_RUN_ONCE:-}" != 1 ] && continue
    [ "$SEL" = "all" ] && echo "$f" && continue
    case "$f" in *"$SEL"*) echo "$f";; esac
  done
}

SCRIPTS=$(scripts_for); [ -n "$SCRIPTS" ] || { echo "no matching plays"; exit 64; }
iter=0
while :; do
  iter=$((iter+1))
  [ "$UNTIL_FAIL" = 0 ] && [ "$iter" -gt "$TIMES" ] && break
  for f in $SCRIPTS; do
    echo "== iter $iter $f =="
    bash "$f" --tag "iter-$iter" "${PASS[@]:-}"
    rc=$?
    if [ $rc -eq 77 ]; then echo "  skip_mature"; continue; fi
    if [ $rc -eq 75 ]; then echo "  serial_wait"; continue; fi
    if [ $rc -ne 0 ]; then echo "STOP: $f failed (rc=$rc) at iter $iter"; exit $rc; fi
  done
done
echo "run complete: $iter iterations"
