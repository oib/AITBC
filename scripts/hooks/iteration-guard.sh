#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Iteration Guard (ABS-12, counting model v2: ABS-115) — loop-enforcement backstop
# =============================================================================
# Counts a ticket's REAL bounces via the task-tracking adapter and blocks a
# gate agent's bounce once a cap is reached, forcing human escalation instead
# of another implement→validate loop.
#
# It is the MECHANICAL backstop to ABS-11's prompt-level rules — not a
# replacement. See specs/ABS-12-iteration-guard-spec.md for the base decisions
# (cap-from-marker, fail-open, interface, wiring) and
# specs/ABS-115-iteration-guard-v2-spec.md for the counting model.
#
# Counting model v2 (ABS-115, operator-confirmed 2026-07-07):
#   - A real bounce = a marker-bearing gate comment ("Iteration N of M" in a
#     kind gate-results|handoff comment) followed — before any other
#     transition — by a transition-reason comment recording a BACKWARD
#     transition. Markers in APPROVE results or quoted by operators never
#     count: their next transition is forward, or their comment kind is not a
#     gate kind. Transitions touching Blocked / Needs PO Decision are neutral.
#   - Two levels: a per-gate counter (gate = the bounce's from-status; a
#     forward transition out of a gate resets ONLY that gate's counter) capped
#     by ITERATION_GUARD_DEFAULT_CAP (default 3), which a marker "Iteration N of
#     M" may only RAISE above — never lower (PILOT-64: an agent must not shrink
#     its own budget via comment prose; the cap FLOOR is configuration, per
#     ADR-A-0026 — control state in typed fields/config, not parsed comments. An
#     APPROVE comment "Iteration 1 of 1" used to set cap=1 and deadlock already-
#     approved work at zero real bounces). The effective per-gate cap is thus
#     max(ITERATION_GUARD_DEFAULT_CAP, highest marker seen), and a cumulative
#     never-reset ticket counter capped by ITERATION_GUARD_TICKET_CAP
#     (default 9, 0 = off) as the general per-ticket budget brake (ADR-A-0009).
#   - Only FUNCTIONAL bounces count (PILOT-49 / ABS-555). A backward transition
#     whose REASON denotes an INFRASTRUCTURE abort — a seat crash, error_max_turns,
#     timeout, 429/rate-limit, session-poison, or the orchestrator's own
#     CRASH-REPAIR / INPROGRESS-HEAL / spawn-crashed / WAIT-STATE-REPAIR /
#     handoff-mis-report routes — carries NO functional verdict and does NOT
#     consume an iteration; it is tracked separately for observability only. The
#     criterion is "was a functional evaluation rendered", not "was a spawn used":
#     an infra abort used to trip the cap on already-approved work and deadlock it.
#   - Block when the next bounce would hit either cap.
#   - FAIL-OPEN: if the tracker is unreachable or no ticket id is determinable,
#     exit 0 with a loud stderr warning. A broken tracker must not deadlock all
#     agent work; the ABS-11 prompt rules remain the fallback layer.
#
# Comments are read only through the adapter (ADR-A-0006/0007) — never by
# touching tracker files or a vendor API directly.
#
# Usage (two modes):
#   Hook mode (no args):     read stdin for JSON tool call; enforce only on
#                            adapter gate bounce commands (comment + gate-results|handoff).
#   Test/CLI mode ($1):      bash scripts/hooks/iteration-guard.sh <ticket-id>
#
# Exit codes:
#   0  under cap — proceed (also every fail-open path)
#   2  cap reached — block the bounce and escalate to a human
# All human-readable output goes to stderr; stdout stays empty.
#
# Environment overrides (mainly for tests):
#   TRACKER_CMD / ITERATION_GUARD_ADAPTER   adapter command
#                             (default: <repo>/scripts/mock-tracker.sh)
#   ITERATION_GUARD_DEFAULT_CAP   per-gate cap FLOOR; a marker may raise it above
#                             this, but never lower it (default: 3)
#   ITERATION_GUARD_TICKET_CAP    cumulative ticket budget cap (default: 9, 0 = off)
#   MOCK_TRACKER_TICKETS_DIR  forwarded to the mock adapter (see mock-tracker.sh)
#
# NOTE (ABS-37): profiles now have a mechanical activation point
# (.active-profile / ACTIVE_PROFILE, see scripts/lib/profile.sh) and
# scripts/profile.sh can resolve a capability's provider. This guard does
# NOT read tracker resolution through profiles yet — there is no
# provider -> adapter-command mapping defined for task-tracking today, so
# wiring it here would be speculative. TRACKER_CMD / ITERATION_GUARD_ADAPTER
# remain the only way to select an adapter and still win over everything;
# profile-based tracker resolution is left for a follow-up ticket.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# TRACKER_CMD is the interface name from the ABS-21 ticket; ITERATION_GUARD_ADAPTER
# is an accepted alias. Either selects the task-tracking adapter command.
ADAPTER="${ITERATION_GUARD_ADAPTER:-${TRACKER_CMD:-$REPO_ROOT/scripts/mock-tracker.sh}}"
# PILOT-64: the per-gate cap FLOOR is configuration, never agent prose. A marker
# may only RAISE the cap above this floor (see §4); it can never lower it.
DEFAULT_CAP="${ITERATION_GUARD_DEFAULT_CAP:-3}"
# ABS-305: a PO release OUT of "Needs PO Decision" clears the per-gate bounce
# counters so a ticket parked at a gate cap can re-enter the pipeline (the capped
# gate is otherwise a locked room — its reset key is a forward transition FROM
# the gate, which needs the very seat the cap blocks). 0 = off = today's
# behaviour (a PO release is neutral and never resets). The cumulative ticket
# budget is never reset by this — the ADR-A-0009 brake stays.
PO_RELEASE_RESET="${ITERATION_GUARD_PO_RELEASE_RESET:-1}"
MARKER_RE='Iteration [0-9]+ of [0-9]+'
TICKET_RE='[A-Z][A-Z0-9]+-[0-9]+'
BOUNCE_KIND_RE='--kind[[:space:]]+(gate-results|handoff)'
# PILOT-49 / ABS-555: reason substrings (matched case-insensitively) that mark a
# backward transition as an INFRASTRUCTURE abort, not a functional bounce. Covers
# the orchestrator's own infra-route reason prefixes (CRASH-REPAIR, INPROGRESS-HEAL,
# spawn crashed, WAIT-STATE REPAIR, handoff mis-report/marker-missing) plus the
# generic crash/limit terms from the ABS-151 diagnostic (kept in step with
# blocker_class()'s transient set in scripts/orchestrator.sh).
# Fail-safe bias: matching is deliberately broad. A false match (a functional
# reject whose prose happens to contain e.g. "timeout") only makes the cap MORE
# lenient — the ADR-A-0009 cumulative brake still fires on the non-matching
# rejects — whereas a false MISS re-creates the exact deadlock this closes
# (approved work parked by an infra abort). Over-classifying as infra is the safe
# direction here; under-classifying is not.
INFRA_ABORT_RE='crash-repair|inprogress-heal|spawn crashed|wait-state repair|handoff mis-report|handoff marker-missing|error_max_turns|max_turns|turn ceiling|session-poison|session poisoned|salvage|rate limit|ratelimit|429|timeout|connection|non-zero exit'

warn()  { echo "iteration-guard: WARN $*"  >&2; }
block() { echo "iteration-guard: BLOCK $*" >&2; }

# Extract tool_input.command from Claude Code PreToolUse JSON on stdin.
# Delegates to the shared helper so this guard and the other "Bash" hooks
# (git commit/push, gh pr create) parse the payload identically.
extract_hook_command() {
    local json="$1"
    printf '%s' "$json" | bash "$SCRIPT_DIR/extract-bash-command.sh"
}

# True when the Bash command is an adapter gate bounce (not merely mentioning a marker).
is_bounce_command() {
    local cmd="$1"
    printf '%s' "$cmd" | grep -qE "comment[[:space:]]+${TICKET_RE}" &&
        printf '%s' "$cmd" | grep -qE -- "$BOUNCE_KIND_RE"
}

# Sets globals ticket and hook_ambiguous from a bounce command string.
extract_bounce_ticket() {
    local cmd="$1"
    local tickets unique_count
    hook_ambiguous=0
    ticket=""
    tickets="$(printf '%s\n' "$cmd" | grep -oE "comment[[:space:]]+${TICKET_RE}" | grep -oE "$TICKET_RE" || true)"
    if [ -z "$tickets" ]; then
        return 0
    fi
    unique_count="$(printf '%s\n' "$tickets" | sort -u | wc -l | tr -d ' ')"
    if [ "$unique_count" -gt 1 ]; then
        hook_ambiguous=1
        return 0
    fi
    ticket="$(printf '%s\n' "$tickets" | tail -1)"
}

hook_ambiguous=0
ticket=""

if [ $# -eq 0 ] && [ ! -t 0 ]; then
    input="$(cat)"
    command="$(extract_hook_command "$input")"

    # Not an adapter gate bounce — allow (covers git commit messages, grep, tests, etc.).
    if [ -z "$command" ] || ! is_bounce_command "$command"; then
        exit 0
    fi

    # Approve-at-cap edge (spec §3.2): hook mode fires BEFORE the comment's
    # follow-up transition exists, so it cannot tell an approval from a bounce.
    # A gate approving on its final allowed iteration says "no bounce" (ABS-11
    # APPROVE convention) — let it through. This only relaxes the ADVISORY hook
    # layer; the authoritative CLI-mode check at the next dispatch still counts
    # a mislabeled comment once its backward transition lands.
    if printf '%s' "$command" | grep -qi "no bounce"; then
        exit 0
    fi

    extract_bounce_ticket "$command"
    if [ "${hook_ambiguous:-0}" -eq 1 ]; then
        block "ambiguous bounce command (multiple comment targets); escalate to human, do not bounce"
        exit 2
    fi
    if [ -z "$ticket" ]; then
        warn "gate bounce command but no ticket id extractable; allowing (fail-open)"
        exit 0
    fi
else
    ticket="${1:-}"
    if [ -z "$ticket" ]; then
        warn "no ticket id provided"
        exit 0
    fi
fi

# ============================================================================
# 2. Read the ticket's comments through the adapter. Any failure -> fail-open.
# ============================================================================

ticket_dump=""
# Resolve the adapter into a runnable command, accepting three shapes:
#   1. a script file path            (default: <repo>/scripts/mock-tracker.sh)
#   2. a PATH command                (e.g. "my-tracker")
#   3. either of the above WITH args (e.g. "/path/tracker.sh --config x", "my-tracker --json")
# A script file is run via `bash` so an unset +x bit does not disable the guard.
read -r -a adapter_words <<< "$ADAPTER"
adapter_cmd="${adapter_words[0]:-}"

if [ -z "$adapter_cmd" ]; then
    warn "adapter command is empty; allowing $ticket (fail-open)"
    exit 0
fi

if [ -f "$adapter_cmd" ]; then
    adapter_run=(bash "${adapter_words[@]}")
elif command -v "$adapter_cmd" >/dev/null 2>&1; then
    adapter_run=("${adapter_words[@]}")
else
    warn "adapter command not found or not executable: $adapter_cmd; allowing $ticket (fail-open)"
    exit 0
fi

if ! ticket_dump="$("${adapter_run[@]}" get "$ticket" 2>/dev/null)"; then
    warn "tracker unreachable or unknown ticket $ticket; allowing (fail-open)"
    exit 0
fi

# ============================================================================
# 3. Walk the comment stream chronologically and count REAL bounces (ABS-115).
#    A real bounce = marker-bearing gate comment (kind gate-results|handoff)
#    whose NEXT transition-reason comment records a backward transition.
#    Per-gate counters reset on a forward transition out of that gate; the
#    cumulative counter never resets. Cap M comes from the most recent marker.
# ============================================================================

# Ticket's current status (frontmatter) — the gate the pending bounce belongs to.
current_status="$(printf '%s\n' "$ticket_dump" | awk '/^## Comments$/{exit} /^status: /{sub(/^status: /,""); print; exit}' || true)"

# PILOT-77 / ADR-A-0026 P1: the per-gate cap as a TYPED FIELD read straight off
# the frontmatter (only-when-set, so absent on unmigrated tickets). When present
# it is AUTHORITATIVE — the dispatch reads the live field and comment markers no
# longer influence the cap. When ABSENT the guard falls back to the legacy
# marker behavior (fail-soft, PILOT-77 AC3) so nothing breaks pre-rollout.
iteration_cap_field="$(printf '%s\n' "$ticket_dump" | awk '/^## Comments$/{exit} /^iteration_cap: /{sub(/^iteration_cap: /,""); print; exit}' || true)"

comments_section="$(printf '%s\n' "$ticket_dump" | awk '/^## Comments$/,EOF { if (!/^## Comments$/) print }' || true)"

gate_count=0
total_count=0
marker_cap=0
abort_count=0

if [ -n "$comments_section" ]; then
    # One chronological awk pass over the comment blocks. The `### ` header
    # line carries the kind; every other line is body (no reliance on a blank
    # separator — adapters may omit it). Direction is ranked against the
    # canonical happy paths pinned in profiles/neutral/adapters/statuses.yaml
    # (see spec §2 for why the ranks are embedded, not parsed at runtime).
    # Blocked / Needs PO Decision / unknown statuses are neutral: their
    # transitions neither count a bounce nor reset a gate, but any transition
    # closes a pending marker window.
    result="$(printf '%s\n' "$comments_section" | awk -v marker_re="$MARKER_RE" -v current="$current_status" -v po_reset="$PO_RELEASE_RESET" -v infra_re="$INFRA_ABORT_RE" '
        function rank(s) { return (s in ranks) ? ranks[s] : -1 }
        BEGIN {
            # story pipeline (statuses.yaml v3 story order)
            n = 0
            n++; ranks["Backlog"] = n
            n++; ranks["Design"] = n
            n++; ranks["Ready for Development"] = n
            n++; ranks["In Progress"] = n
            n++; ranks["In Review"] = n
            n++; ranks["Security Review"] = n
            n++; ranks["Test Prep"] = n
            n++; ranks["In Test"] = n
            n++; ranks["Design Test"] = n
            n++; ranks["Story Acceptance"] = n
            n++; ranks["Merging"] = n
            n++; ranks["Docs"] = n
            n++; ranks["Ready for Human Acceptance"] = n
            n++; ranks["Ready for Merge"] = n
            n++; ranks["Done"] = n
            # epic pipeline (offset well past the story ranks; Backlog shared)
            e = 100
            e++; eranks["PO Triage"] = e
            e++; eranks["Grooming"] = e
            e++; eranks["Enrichment"] = e
            e++; eranks["Ticket Review"] = e
            e++; eranks["Architecture Review"] = e
            e++; eranks["Stories In Flight"] = e
            e++; eranks["Epic Integration"] = e
            e++; eranks["Ready for Epic Acceptance"] = e
            e++; eranks["Epic Done"] = e
            # ABS-338: Canceled is a shared terminal rest (like Epic Done, next: []);
            # highest rank so any move into it reads as forward, never a bounce.
            e++; eranks["Canceled"] = e
            # PILOT-34: Rejected is the same shape (shared terminal rest, next: [])
            # — highest rank so an override into it reads as forward, never a bounce.
            e++; eranks["Rejected"] = e
            for (s in eranks) ranks[s] = eranks[s]
            ranks["Backlog"] = 1   # shared entry, below both pipelines
            in_block = 0; kind = ""; pending_marker = 0
            marker_cap = 0; total = 0
        }
        /^### / {
            # New comment block: extract its kind from the header.
            in_block = 1
            kind = ""
            if (match($0, /kind: [a-z-]+/)) {
                kind = substr($0, RSTART + 6, RLENGTH - 6)
            }
            handled_transition = 0
            next
        }
        in_block == 1 {
            # Marker in a GATE comment opens a pending-bounce window; markers
            # in any other kind (decision, notification, transition-reason...)
            # are quotes and never count. PILOT-64: a marker may only RAISE the
            # cap — we take the MAX "of M" seen, never "most recent wins" — so an
            # agent cannot shrink its own budget with a small "of M" and deadlock
            # already-approved work. The configured floor is applied in bash (§4).
            # Markers of any kind still feed the max (informational ones report a
            # loop cap too), but since they can only widen the budget a non-gate
            # quote is harmless.
            if ($0 ~ marker_re) {
                if (match($0, /Iteration [0-9]+ of [0-9]+/)) {
                    m = substr($0, RSTART, RLENGTH)
                    sub(/^Iteration [0-9]+ of /, "", m)
                    if (m + 0 > marker_cap + 0) marker_cap = m + 0
                }
                if (kind == "gate-results" || kind == "handoff") {
                    pending_marker = 1
                }
            }
            # First Transition line of a transition-reason block decides
            # direction; both adapters emit "Transition: <from> -> <to>. Reason:".
            if (kind == "transition-reason" && handled_transition == 0 && $0 ~ /^Transition: .* -> .*\. Reason: /) {
                handled_transition = 1
                line = $0
                sub(/^Transition: /, "", line)
                to = line
                sub(/ -> .*$/, "", line); from = line
                sub(/^.* -> /, "", to); sub(/\. Reason: .*$/, "", to)
                # PILOT-49 / ABS-555: the transition REASON separates a FUNCTIONAL
                # bounce (a gate reject -> rework) from an INFRASTRUCTURE abort
                # (crash, error_max_turns, timeout, rate-limit, session-poison, or
                # the orchestrator own CRASH-REPAIR / INPROGRESS-HEAL / spawn-
                # crashed routes). An infra abort carries no functional verdict and
                # must not consume an iteration — it only tripped the cap on
                # already-approved work and deadlocked it.
                reason = $0
                sub(/^.*\. Reason: /, "", reason)
                infra = (tolower(reason) ~ infra_re)
                rf = rank(from); rt = rank(to)
                # ABS-305: a release OUT of "Needs PO Decision" (a fresh PO
                # adjudication) clears the per-gate bounce counters so a ticket
                # parked at a gate cap gets one clean re-entry. The cumulative
                # `total` is deliberately left intact (ADR-A-0009 budget brake).
                if (po_reset != "0" && from == "Needs PO Decision" && to != "Needs PO Decision" && to != "Blocked") {
                    for (g in gate) gate[g] = 0
                }
                neutral = (from == "Blocked" || to == "Blocked" || from == "Needs PO Decision" || to == "Needs PO Decision" || rf < 0 || rt < 0)
                if (!neutral && rt < rf) {
                    # Backward transition: a pending gate marker makes it a bounce…
                    if (pending_marker == 1) {
                        if (infra) {
                            # …unless it was an infrastructure abort: tracked for
                            # observability (AC5), never counted as an iteration.
                            aborts++
                        } else {
                            gate[from]++
                            total++
                        }
                    }
                } else if (!neutral && rt > rf) {
                    # Forward progress over `from` resets ONLY that gate.
                    gate[from] = 0
                }
                # Any transition closes the pending marker window.
                pending_marker = 0
            }
        }
        END {
            print gate[current] + 0 "|" total "|" marker_cap + 0 "|" aborts + 0
        }
    ')"

    gate_count="$(printf '%s\n' "$result" | cut -d'|' -f1 || true)"
    total_count="$(printf '%s\n' "$result" | cut -d'|' -f2 || true)"
    marker_cap="$(printf '%s\n' "$result" | cut -d'|' -f3 || true)"
    abort_count="$(printf '%s\n' "$result" | cut -d'|' -f4 || true)"
fi

gate_count="${gate_count:-0}"
total_count="${total_count:-0}"
abort_count="${abort_count:-0}"
marker_cap="${marker_cap:-0}"
# PILOT-64 (AC1/AC2): the cap FLOOR is configuration (ITERATION_GUARD_DEFAULT_CAP),
# never agent prose. A marker "Iteration N of M" may only RAISE the cap above that
# floor — it can never lower it — so an agent cannot shrink its own budget with a
# small "of M" and deadlock already-approved work (the PILOT-32 class). Aligns
# with ADR-A-0026: control state lives in typed config/fields, not parsed comments.
cap="$DEFAULT_CAP"
cap_source="configured floor ITERATION_GUARD_DEFAULT_CAP=$DEFAULT_CAP"
if [ -n "$iteration_cap_field" ] && [ "$iteration_cap_field" -ge 1 ] 2>/dev/null; then
    # PILOT-77 / ADR-A-0026 P1: a typed iteration_cap field is AUTHORITATIVE.
    # The dispatch reads the live field; comment markers ("Iteration N of M") no
    # longer raise (or lower) it — a past comment cannot re-raise the cap. The
    # value is a deliberate, audited operator/field write, so it is honored even
    # below the configured floor (that safety was for agent PROSE, not fields).
    cap="$iteration_cap_field"
    cap_source="typed field iteration_cap=$iteration_cap_field (ADR-A-0026 P1; comment markers ignored)"
elif [ -n "$marker_cap" ] && [ "$marker_cap" -gt "$cap" ] 2>/dev/null; then
    # FAIL-SOFT (PILOT-77 AC3): no iteration_cap field on this ticket (unmigrated)
    # — fall back to the legacy comment-marker behavior so pre-rollout runs are
    # unaffected. A marker may only RAISE above the configured floor (PILOT-64).
    cap_source="raised by marker to $marker_cap (above configured floor $DEFAULT_CAP; no iteration_cap field — legacy fail-soft)"
    cap="$marker_cap"
fi
# Cumulative ticket budget cap is fixed (not marker-derived): a per-ticket
# marker speaks only for its own loop; the budget brake must not be widenable
# by a gate agent writing "of 12". 0 disables the level (runner convention).
ticket_cap="${ITERATION_GUARD_TICKET_CAP:-9}"

# ============================================================================
# 4. Decide. The bounce about to happen is the next one on BOTH levels.
# ============================================================================

next_gate=$((gate_count + 1))
next_total=$((total_count + 1))

if [ -n "$current_status" ] && [ "$next_gate" -ge "$cap" ]; then
    block "$ticket — $gate_count prior FUNCTIONAL bounce(s) at gate '$current_status', cap $cap [$cap_source] reached ($abort_count infrastructure abort(s) excluded, not counted — PILOT-49/ABS-555); escalate to human, do not bounce"
    exit 2
fi
if [ "$ticket_cap" -gt 0 ] 2>/dev/null && [ "$next_total" -ge "$ticket_cap" ]; then
    block "$ticket — $total_count FUNCTIONAL bounce(s) over the ticket lifetime, cumulative budget cap $ticket_cap reached (ITERATION_GUARD_TICKET_CAP; $abort_count infrastructure abort(s) excluded, not counted — PILOT-49/ABS-555); escalate to human, do not bounce"
    exit 2
fi

exit 0
