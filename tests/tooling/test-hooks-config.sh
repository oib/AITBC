#!/usr/bin/env bash
# =============================================================================
# Test: hooks-config.json <-> settings.template.json STRUCTURAL parity
#       (ABS-25 origin; ABS-149 structural drift guard)
# =============================================================================
# hooks-config.json is the annotated source-of-record; settings.template.json is
# the LIVE, auto-loaded wiring (ABS-32). They must stay in lock-step: the same
# hook events, and — per event — the SAME set of command strings. Only the
# human-facing `description` fields may legitimately differ.
#
# The OLD version of this test grepped four fixed needles. That is the anti-
# pattern the ABS-149 defect exposed: entire hook entries could drift out of
# hooks-config.json unnoticed (the ABS-92 wrong-entry guard was missing from
# SessionStart) because no needle looked for them. This version compares the
# full command SET per event, so ANY future add/remove/edit drift class surfaces.
#
# WHY this targets harness/claude (not live .claude): under the generate(pin)
# model (ABS-94) the live .claude/ is materialized from the pin tag and must NOT
# be edited ahead of promotion — it is frozen with whatever drift the tag
# carried. The re-sync fix lives in the harness source-of-record and lands live
# at the next promotion. Comparing the harness copies keeps this guard green
# pre-promotion and guards the files developers actually edit.
# (system-architect signed off the harness-targeting approach for ABS-149.)
#
# bash 3.2 / BSD safe. Run from repo root: bash tests/tooling/test-hooks-config.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HARNESS="$REPO_ROOT/harness/claude"
CONFIG="$HARNESS/hooks-config.json"
SETTINGS="$HARNESS/settings.template.json"

if ! command -v jq >/dev/null 2>&1; then
  echo "SKIP: jq not installed — structural hooks-config test requires jq"; exit 0
fi

fail() { echo "FAIL: $1"; exit 1; }

# --- 0. Both source-of-record files must be valid JSON ----------------------
python3 -m json.tool "$CONFIG"   >/dev/null || fail "hooks-config.json is not valid JSON"
python3 -m json.tool "$SETTINGS" >/dev/null || fail "settings.template.json is not valid JSON"

# --- 1. Identical set of hook events ----------------------------------------
EV_S="$(jq -r '.hooks | keys[]' "$SETTINGS" | sort)"
EV_C="$(jq -r '.hooks | keys[]' "$CONFIG"   | sort)"
if [ "$EV_S" != "$EV_C" ]; then
  echo "--- settings events ---";     printf '%s\n' "$EV_S"
  echo "--- hooks-config events ---"; printf '%s\n' "$EV_C"
  fail "hook event sets differ between settings.template.json and hooks-config.json"
fi

# --- 2. Per event: identical command SET (order-independent) ----------------
# Descriptions may differ; the executable command strings may not. A mismatch
# means a hook was added, removed, or edited in one file but not the other.
TOTAL_CMDS=0
for ev in $EV_S; do
  S="$(jq -r --arg e "$ev" '[.hooks[$e][]?.hooks[]?.command] | sort | .[]' "$SETTINGS")"
  C="$(jq -r --arg e "$ev" '[.hooks[$e][]?.hooks[]?.command] | sort | .[]' "$CONFIG")"
  if [ "$S" != "$C" ]; then
    echo "=== command-set drift in event: $ev ==="
    diff <(printf '%s\n' "$S") <(printf '%s\n' "$C") || true
    fail "command sets differ for event '$ev' (settings.template.json vs hooks-config.json)"
  fi
  n=$(jq -r --arg e "$ev" '[.hooks[$e][]?.hooks[]?.command] | length' "$SETTINGS")
  TOTAL_CMDS=$((TOTAL_CMDS + n))
done

# Guard against a trivially-equal (both empty) pass.
[ "$TOTAL_CMDS" -gt 0 ] || fail "no hook commands found — refusing to pass on an empty config"

# --- 3. SessionEnd must NOT register the evolver lifecycle (Stop only) -------
for f in "$SETTINGS" "$CONFIG"; do
  if jq -e '[.hooks.SessionEnd[]?.hooks[]?.command] | map(select(test("evolver-lifecycle"))) | length > 0' "$f" >/dev/null 2>&1; then
    fail "evolver-lifecycle hook registered on SessionEnd in $(basename "$f") (use Stop only)"
  fi
done

# --- 4. ABS-149 regression floor: the wrong-entry guard is present in BOTH ---
# (the specific hook whose omission from hooks-config.json was the ABS-149 bug)
for f in "$SETTINGS" "$CONFIG"; do
  jq -e '[.hooks.SessionStart[]?.hooks[]?.command] | map(select(test("session-wrong-entry-guard"))) | length > 0' "$f" >/dev/null 2>&1 \
    || fail "ABS-92 wrong-entry guard missing from SessionStart in $(basename "$f")"
done

echo "PASS: hooks-config structural parity ($TOTAL_CMDS commands across $(printf '%s\n' "$EV_S" | grep -c .) events)"
exit 0
