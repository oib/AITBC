#!/bin/bash
# =============================================================================
# Status Source-of-Truth Drift Guard (ABS-404)
# =============================================================================
# profiles/neutral/adapters/statuses.yaml is the SINGLE SOURCE OF TRUTH for the
# canonical ticket status machine. Several places embed a COPY of the status
# list / order / terminality for zero-dependency awk/bash reasons. Each embedded
# copy is a silent-drift surface: the ABS-338 'Canceled' merge added the status
# to statuses.yaml but not to the iteration-guard rank list, and it only
# surfaced at the v2.26.2 release check (not before the merge).
#
# This guard checks EVERY embedded copy against statuses.yaml in one place, and
# is auto-discovered by the CI / pre-release test loops via tests/test-*.sh
# (tests/test-status-source-drift.sh), so drift fails BEFORE the merge.
#
# ─── Inventory of embedded copies (AC1) ──────────────────────────────────────
#   COPY A  scripts/hooks/iteration-guard.sh    ranks[]/eranks[] awk arrays
#           -> the CHAIN ORDER (spec §2: ranks are embedded, not parsed at
#              runtime). Checked here as: order == statuses.yaml document order
#              (Blocked / Needs PO Decision excluded — cross-cutting/neutral).
#   COPY B  scripts/orchestrator.sh             is_known_status() case list
#           -> the full MEMBERSHIP set. Checked here as: set == statuses.yaml
#              `- name:` set (Blocked / Needs PO Decision included).
#   COPY C  scripts/orchestrator.sh             terminal rest-skip case lists
#           (is_legit_rest_status / first_live_claim /
#            propagate_start_label_to_children)
#           -> the TERMINAL subset. Checked here as: every `terminal: true`
#              status in statuses.yaml appears in each of these three lists (a
#              forgotten terminal status is the ABS-339 respawn-loop bug class).
#   COPY D  backend/packages/core/src/workflows/statuses.yaml
#           -> a full FILE MIRROR. Checked here as: byte-identical to the source.
#   COPY E  scripts/fastlane-eligibility.sh    IN_FLIGHT="A|B|C..." pipe list
#           -> a MEMBERSHIP SUBSET (the active-work statuses that count as a
#              sibling conflict). Checked here as: every IN_FLIGHT token is a
#              valid statuses.yaml name (catches a rename/removal in the source
#              leaving a dangling token). The REVERSE direction — a NEW active
#              status forgotten in IN_FLIGHT — is not mechanically checkable
#              without an in-flight/category attribute in statuses.yaml, so it is
#              out of scope for this guard; documented, not silently missed.
#
#   COPY F  knowledge/ticket-lifecycle-and-statuses.md
#           -> the DOCUMENTED status surface (ABS-520 / epic ABS-514): the file
#              claims a total count ("defines **N** canonical statuses") and
#              names every status in prose/tables. Checked here as: the claimed
#              count equals the statuses.yaml `- name:` count, and every
#              canonical name appears in the document. (Review split of the
#              original generate-doc-blocks idea: extend THIS guard, never add
#              a second status parser — ADR-A-0010.)
#
#   NOT copies (already data-driven from statuses.yaml — no drift possible):
#     scripts/jira-tracker.sh  CANON_STATUS_LIST (sed over the file)
#     scripts/orchestrator.sh  status_is_terminal()  (awk over the file)
#     scripts/mock-tracker.sh  status validation      (awk over the file)
#
#   NOT covered (out of scope — a separate backend-package drift class):
#     backend TS embeds status literals (packages/core/src/invariants.ts,
#     board.ts, apps/server/src/routes/dashboard.ts, apps/web/src/util.ts).
#     These are TypeScript-side semantic subsets, not scripts-side list copies;
#     COPY D already pins the backend statuses.yaml itself byte-identical. A
#     TS-side status-literal guard belongs with the backend workspace's own
#     lint/typecheck, not this bash scripts-side guard.
#
# Exit 0 = no drift. Exit 1 = at least one embedded copy drifted (details on
# stderr). The source file can be overridden with STATUS_SOURCE_FILE so the
# regression test can point the guard at a mutated copy.
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE="${STATUS_SOURCE_FILE:-$REPO_ROOT/profiles/neutral/adapters/statuses.yaml}"
GUARD_FILE="${STATUS_GUARD_FILE:-$REPO_ROOT/scripts/hooks/iteration-guard.sh}"
ORCH_FILE="${STATUS_ORCH_FILE:-$REPO_ROOT/scripts/orchestrator.sh}"
MIRROR_FILE="${STATUS_MIRROR_FILE:-$REPO_ROOT/backend/packages/core/src/workflows/statuses.yaml}"
FASTLANE_FILE="${STATUS_FASTLANE_FILE:-$REPO_ROOT/scripts/fastlane-eligibility.sh}"
KNOWLEDGE_FILE="${STATUS_KNOWLEDGE_FILE:-$REPO_ROOT/knowledge/ticket-lifecycle-and-statuses.md}"

fail=0
note() { printf '  %s\n' "$1" >&2; }
drift() { printf 'DRIFT: %s\n' "$1" >&2; fail=1; }

for f in "$SOURCE" "$GUARD_FILE" "$ORCH_FILE"; do
    [ -f "$f" ] || { printf 'status-source-drift-guard: missing file: %s\n' "$f" >&2; exit 2; }
done

# --- extraction helpers ------------------------------------------------------
# Canonical names, in statuses.yaml document order.
source_order()   { sed -n 's/^  - name: //p' "$SOURCE"; }
# Chain order excludes the cross-cutting neutral statuses (as the guard ranks do).
source_chain()   { source_order | grep -vxE 'Blocked|Needs PO Decision'; }
# terminal: true statuses.
source_terminal(){ awk '/^  - name: /{cur=substr($0,11)} /^    terminal: true/{print cur}' "$SOURCE"; }
# Quoted tokens of a bash function body (opening `name() {` to its closing `}`).
fn_tokens() {
    awk -v fn="$1" '$0 ~ "^"fn"\\(\\) \\{"{f=1} f{print} f&&/^\}/{exit}' "$ORCH_FILE" \
        | grep -oE '"[^"]+"' | tr -d '"'
}

# --- COPY A: iteration-guard rank order == statuses.yaml document order -------
guard_order="$(sed -n '/story pipeline (statuses.yaml/,/for (s in eranks)/p' "$GUARD_FILE" \
    | grep -oE '(ranks|eranks)\["[^"]+"\]' | sed -E 's/^e?ranks\["//; s/"\]$//')"
if [ "$(source_chain)" = "$guard_order" ]; then
    note "COPY A OK: iteration-guard ranks match statuses.yaml order"
else
    drift "COPY A: iteration-guard.sh ranks[]/eranks[] drifted from statuses.yaml order"
    note "fix: update the ranks[]/eranks[] awk block in scripts/hooks/iteration-guard.sh"
    note "--- statuses.yaml (chain order) ---"; source_chain | sed 's/^/    /' >&2
    note "--- iteration-guard ranks ---";      printf '%s\n' "$guard_order" | sed 's/^/    /' >&2
fi

# --- COPY B: is_known_status membership == statuses.yaml name set -------------
iks="$(fn_tokens is_known_status | grep -vxF '$1')"
if [ "$(source_order | sort)" = "$(printf '%s\n' "$iks" | sort)" ]; then
    note "COPY B OK: orchestrator is_known_status() matches statuses.yaml names"
else
    drift "COPY B: orchestrator.sh is_known_status() drifted from statuses.yaml names"
    note "fix: update the is_known_status() case list in scripts/orchestrator.sh"
    note "--- only in statuses.yaml ---"; comm -23 <(source_order | sort) <(printf '%s\n' "$iks" | sort) | sed 's/^/    /' >&2
    note "--- only in is_known_status ---"; comm -13 <(source_order | sort) <(printf '%s\n' "$iks" | sort) | sed 's/^/    /' >&2
fi

# --- COPY C: every terminal status is present in the rest-skip case lists -----
# Process substitution keeps the loop in the current shell, so drift() and the
# ok flag mutate this scope directly (no subshell, no temp file).
copyc_ok=1
for fn in is_legit_rest_status first_live_claim propagate_start_label_to_children; do
    toks="$(fn_tokens "$fn")"
    while IFS= read -r t; do
        [ -n "$t" ] || continue
        printf '%s\n' "$toks" | grep -qxF "$t" && continue
        drift "COPY C: terminal status '$t' missing from ${fn}() in orchestrator.sh"
        copyc_ok=0
    done < <(source_terminal)
done
if [ "$copyc_ok" -eq 1 ]; then
    note "COPY C OK: all terminal statuses present in the orchestrator rest-skip lists"
else
    note "fix: add the terminal status to the rest-skip case list(s) named above"
fi

# --- COPY D: backend mirror byte-identical to the source ---------------------
if [ -f "$MIRROR_FILE" ]; then
    if cmp -s "$SOURCE" "$MIRROR_FILE"; then
        note "COPY D OK: backend statuses.yaml mirror is byte-identical"
    else
        drift "COPY D: backend/packages/core/src/workflows/statuses.yaml drifted from the source"
        note "fix: copy profiles/neutral/adapters/statuses.yaml over the backend mirror"
    fi
else
    note "COPY D SKIP: backend mirror not present ($MIRROR_FILE)"
fi

# --- COPY E: every fastlane IN_FLIGHT token is a valid statuses.yaml name -----
if [ -f "$FASTLANE_FILE" ]; then
    in_flight="$(sed -n 's/^IN_FLIGHT="\(.*\)"$/\1/p' "$FASTLANE_FILE")"
    if [ -z "$in_flight" ]; then
        note "COPY E SKIP: no IN_FLIGHT list found in fastlane-eligibility.sh"
    else
        names="$(source_order)"
        copye_ok=1
        while IFS= read -r t; do
            [ -n "$t" ] || continue
            printf '%s\n' "$names" | grep -qxF "$t" && continue
            drift "COPY E: fastlane IN_FLIGHT token '$t' is not a statuses.yaml name"
            copye_ok=0
        done < <(printf '%s\n' "$in_flight" | tr '|' '\n')
        if [ "$copye_ok" -eq 1 ]; then
            note "COPY E OK: fastlane IN_FLIGHT tokens are all valid statuses.yaml names"
        else
            note "fix: update IN_FLIGHT in scripts/fastlane-eligibility.sh to match statuses.yaml"
        fi
    fi
else
    note "COPY E SKIP: fastlane-eligibility.sh not present ($FASTLANE_FILE)"
fi

# --- COPY F: documented status surface in the knowledge doc -------------------
if [ -f "$KNOWLEDGE_FILE" ]; then
    copyf_ok=1
    actual_count="$(source_order | wc -l | tr -d ' ')"
    claimed_count="$(sed -n 's/.*defines \*\*\([0-9][0-9]*\)\*\* canonical statuses.*/\1/p' "$KNOWLEDGE_FILE" | head -1)"
    if [ -z "$claimed_count" ]; then
        drift "COPY F: knowledge doc no longer states its canonical-status count (\"defines **N** canonical statuses\")"
        copyf_ok=0
    elif [ "$claimed_count" != "$actual_count" ]; then
        drift "COPY F: knowledge doc claims $claimed_count canonical statuses, statuses.yaml defines $actual_count"
        copyf_ok=0
    fi
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        grep -qF -- "$name" "$KNOWLEDGE_FILE" && continue
        drift "COPY F: status '$name' is not documented in knowledge/ticket-lifecycle-and-statuses.md"
        copyf_ok=0
    done < <(source_order)
    if [ "$copyf_ok" -eq 1 ]; then
        note "COPY F OK: knowledge doc count + membership match statuses.yaml"
    else
        note "fix: update knowledge/ticket-lifecycle-and-statuses.md (count sentence + status tables)"
    fi
else
    note "COPY F SKIP: knowledge doc not present ($KNOWLEDGE_FILE)"
fi

if [ "$fail" -ne 0 ]; then
    printf '\nstatus-source-drift-guard: FAIL — statuses.yaml has drifted from an embedded copy (see above).\n' >&2
    exit 1
fi
printf 'status-source-drift-guard: OK — all embedded status copies match statuses.yaml.\n'
exit 0
