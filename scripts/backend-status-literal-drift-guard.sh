#!/usr/bin/env bash
# =============================================================================
# backend-status-literal-drift-guard.sh  (ABS-424)
# =============================================================================
# Single-source guard for the BACKEND TypeScript status-name LITERAL subsets.
#
# WHY THIS EXISTS
#   The canonical status machine lives in
#     backend/packages/core/src/workflows/statuses.yaml
#   (mirrored from profiles/neutral/adapters/statuses.yaml). Several backend TS
#   files embed status NAMES as string literals instead of deriving them from
#   that YAML. Rename or remove a status in the YAML and those literals silently
#   drift — the exact ABS-338 "Canceled" incident class, one package over.
#
#   ABS-404 closed this for the SCRIPTS-side embedded copies with its own
#   scripts/status-source-drift-guard.sh (COPY A–E) and explicitly scoped OUT
#   this backend-TS drift class. This guard closes that residual surface as a
#   self-contained, backend-package-native check (ABS-424, ticket OR clause) —
#   it does NOT depend on ABS-404's script, so it lands on the integration
#   branch regardless of whether that script is present there yet.
#
# WHAT IT CHECKS (rename/removal drift direction)
#   Every backend TS status literal carrying a trailing `drift-guard:status-name`
#   marker must be a VALID workflow status name — i.e. a name in statuses.yaml
#   (unioned with adr-lifecycle.yaml when that file is present, since `Proposed`
#   legitimately comes from the ADR lifecycle). A rename/removal in the YAML that
#   leaves a dangling TS literal turns this guard RED (non-zero exit).
#
#   The trailing marker makes extraction PRECISE: only marked quoted tokens are
#   checked, so a description, a UI group label, or an SQL fragment is never
#   mistaken for a status name.
#
# GUARDED FILES / SUBSETS (inventoried against the current tree, ABS-424)
#     backend/packages/core/src/board.ts          ESCALATION_INBOX_STATUSES
#     backend/packages/core/src/invariants.ts      WAIT_STATE_INVARIANTS.status
#     backend/packages/core/src/transitions.ts     REBASE_GATE_FROM / REBASE_GATE_TO
#     backend/apps/server/src/routes/dashboard.ts  MERGE_GATE_STATUSES
#     backend/apps/web/src/util.ts                 MERGE_GATE_STATUSES
#
# NOT COVERED (verified out of scope, ABS-424 — documented, not silently missed)
#   - board.ts boardColumns() group labels ("Backlog", "Epic Pipeline",
#     "Story Pipeline", "Blocked / Needs PO Decision", "Done"). These are
#     structurally-derived UI COLUMN HEADERS, not status-membership literals; the
#     column contents are derived from the resolved workflow, not hardcoded.
#     "Backlog" and "Done" happen to spell the same word as a status name — a
#     name collision, not an inventory gap — so they are deliberately unmarked.
#   - Single/fixed ADR-lifecycle literals that are not ordered status subsets:
#     items.ts ADR_STATUS_MAP (Draft/Proposed/Accepted/Superseded) + the
#     "Superseded" supersede-path literals, and server.ts `to === "Accepted"`.
#     These are keyed off adr-lifecycle.yaml (this guard's union source), so a
#     rename surfaces via the marked literals; guarding them too would over-reach
#     the ticket's "status name / list / order / terminality subset" scope.
#
# LIMITATION (documented, same as ABS-404 COPY E)
#   The REVERSE direction — a genuinely NEW status-literal subset added to a TS
#   file WITHOUT the marker — is not mechanically checkable without an
#   in-flight/category attribute in the YAML, so it is out of scope. As a partial
#   anti-rot lock, the guard goes RED if it finds ZERO marked literals at all
#   (every marker vanished = the guard was silently unwired).
#
# Exit 0 = no drift. Exit 1 = at least one marked TS literal is not a valid
# workflow status name (details on stderr).
# =============================================================================
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

STATUS_SOURCE_FILE="${STATUS_SOURCE_FILE:-$REPO_ROOT/backend/packages/core/src/workflows/statuses.yaml}"
ADR_SOURCE_FILE="${STATUS_ADR_SOURCE_FILE:-$REPO_ROOT/backend/packages/core/src/workflows/adr-lifecycle.yaml}"

TS_FILES=(
  "${STATUS_BOARD_TS_FILE:-$REPO_ROOT/backend/packages/core/src/board.ts}"
  "${STATUS_INVARIANTS_TS_FILE:-$REPO_ROOT/backend/packages/core/src/invariants.ts}"
  "${STATUS_TRANSITIONS_TS_FILE:-$REPO_ROOT/backend/packages/core/src/transitions.ts}"
  "${STATUS_DASHBOARD_TS_FILE:-$REPO_ROOT/backend/apps/server/src/routes/dashboard.ts}"
  "${STATUS_WEB_UTIL_TS_FILE:-$REPO_ROOT/backend/apps/web/src/util.ts}"
)

note() { printf '  %s\n' "$1" >&2; }

if [ ! -f "$STATUS_SOURCE_FILE" ]; then
  printf 'backend-status-literal-drift-guard: FAIL — status source not found: %s\n' "$STATUS_SOURCE_FILE" >&2
  exit 1
fi

# Valid names: statuses.yaml (∪ adr-lifecycle.yaml when present).
# YAML shape (kept stable by contract): "  - name: <Status>" at 2-space indent.
yaml_names() { sed -n 's/^[[:space:]]*-[[:space:]]*name:[[:space:]]*//p' "$1" | sed 's/[[:space:]]*$//'; }
valid_names="$(yaml_names "$STATUS_SOURCE_FILE")"
if [ -f "$ADR_SOURCE_FILE" ]; then
  valid_names="$valid_names
$(yaml_names "$ADR_SOURCE_FILE")"
fi

fail=0
seen=0
for tsf in "${TS_FILES[@]}"; do
  if [ ! -f "$tsf" ]; then
    note "SKIP: TS file not present ($tsf)"
    continue
  fi
  rel="${tsf#"$REPO_ROOT"/}"
  while IFS= read -r lit; do
    [ -n "$lit" ] || continue
    seen=$((seen + 1))
    if ! printf '%s\n' "$valid_names" | grep -qxF "$lit"; then
      note "DRIFT: TS status literal '$lit' in $rel is not a valid workflow status name (statuses.yaml / adr-lifecycle.yaml)"
      fail=1
    fi
  done < <(grep -h 'drift-guard:status-name' "$tsf" | grep -oE '"[^"]+"' | tr -d '"')
done

if [ "$seen" -eq 0 ]; then
  note "DRIFT: no marked backend TS status literals found — 'drift-guard:status-name' markers missing or renamed (anti-rot lock)"
  note "fix: restore the trailing 'drift-guard:status-name' markers on the backend TS status literals"
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  printf '\nbackend-status-literal-drift-guard: FAIL — a backend TS status literal drifted from statuses.yaml (see above).\n' >&2
  exit 1
fi

printf 'backend-status-literal-drift-guard: OK — %s marked backend TS status literals all valid workflow names.\n' "$seen"
exit 0
