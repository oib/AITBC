#!/usr/bin/env bash
# ops-sweep-sensors.sh — read-only, deterministic detectors for the eight
# "Steckenbleiber" (stuck) classes the operator resolved by hand across v3-pilots
# #3–#5 (PILOT-40, epic PILOT-39; twin ABS-549). Change-contract:
# work/improvement-proposals/2026-07-25-hourly-ops-sweep-janitor.md.
#
# WHY. Over three pilot runs the human operator kept resolving the SAME classes of
# stuck tickets. The runs were healthy; what held them up was janitorial cleanup
# with a DETERMINISTIC diagnosis. Seven of the eight classes have a mechanically
# checkable signature — an LLM that "reasons" about whether a lock is stale is
# strictly worse than a PID/TTL comparison. This script is the SENSOR half of that
# split (the plan's §1): pure shell, no LLM, unit-testable with fixtures. A TDM
# seat consumes its output and owns judgement/action; "what the sensor does not
# see does not exist for the sweep".
#
# CONTRACT (this is the interface — depend on it):
#   * Read-only. Never writes, never transitions, never touches git refs.
#   * Emits ONE line per finding, four whitespace-separated columns:
#         <class> <ticket-or-dash> <evidence> <suggestion>
#     Columns 3 (evidence) and 4 (suggestion) carry NO internal spaces
#     (comma/`=`/`-`-joined tokens) so a line splits into exactly four fields.
#   * Exit 0 EVEN WITH FINDINGS — this is a diagnosis, not a gate. The only
#     non-zero exit is 64 (usage error on bad input), fail-closed.
#   * Every input is env-overridable, which is exactly what makes each detector
#     fixture-testable in isolation. A detector whose input is absent prints
#     nothing and returns 0 (so an anomaly-free or partial fixture => zero lines).
#
# Usage:
#   ops-sweep-sensors.sh [detector ...]   # run named detectors, or ALL if none
#   ops-sweep-sensors.sh --list           # list detector names
#
# Env inputs (all optional; defaults derive from the ambient orchestrator env):
#   OPS_REPO             git repo / main checkout to inspect  (default: cwd toplevel)
#   OPS_MAIN_BRANCH      expected main-checkout branch        (default: main)
#   OPS_TARGET_BRANCH    merge-base target for dep/mr checks  (default: $OPS_MAIN_BRANCH)
#   OPS_TARGET_REMOTE    remote whose refs count as "pushed"  (default: active push remote/origin)
#   OPS_STATE_DIR        orchestrator state dir               (default: $ORCH_STATE_DIR)
#   OPS_LOCK_TTL         stale-lock age threshold, seconds     (default: $ORCH_LOCK_TTL or 4000)
#   OPS_LIVE_CWDS_FILE   file: one live-process cwd per line   (default: lsof over `claude` procs' cwd)
#                        stale-lock cross-checks this: a lock past TTL is stale ONLY IF no living
#                        process has its cwd in the ticket's seat worktree (PID/TTL alone is a
#                        false criterion — operator 2026-07-25, the costliest misclass). Set it to
#                        an empty/absent path to assert "no live seats" deterministically in tests.
#   OPS_OUTAGE_STALE     outage/probe marker staleness, secs  (default: 3600)
#   OPS_TICKETS_DIR      dir of mock-tracker ticket *.md      (default: none => ticket detectors skip)
#   OPS_BACKEND_ROWS     file: "<instance_id>[<TAB><count>]" per line (default: none => skip)
#   OPS_INSTANCE_PATTERN grep -E pattern of legit instance ids (default: none => skip junk-rows)
#   OPS_CI_CONFIG        shipped CI config to check for capacity (default: $OPS_REPO/.gitlab-ci.yml)
#   OPS_RUNNER_COUNT     injected count of usable runners       (default: none; unknown => ci-capacity skips)
#   OPS_CI_PROJECT       GitLab project for a LIVE runner count (default: none; used only when OPS_RUNNER_COUNT unset)
#   OPS_NOW              injected epoch clock for age tests    (default: date -u +%s)
# =============================================================================
set -uo pipefail

# ---- inputs / defaults ------------------------------------------------------
OPS_REPO="${OPS_REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
OPS_MAIN_BRANCH="${OPS_MAIN_BRANCH:-main}"
OPS_TARGET_BRANCH="${OPS_TARGET_BRANCH:-$OPS_MAIN_BRANCH}"
OPS_STATE_DIR="${OPS_STATE_DIR:-${ORCH_STATE_DIR:-}}"
OPS_LOCK_TTL="${OPS_LOCK_TTL:-${ORCH_LOCK_TTL:-4000}}"
OPS_OUTAGE_STALE="${OPS_OUTAGE_STALE:-3600}"
OPS_TICKETS_DIR="${OPS_TICKETS_DIR:-}"
OPS_BACKEND_ROWS="${OPS_BACKEND_ROWS:-}"
OPS_INSTANCE_PATTERN="${OPS_INSTANCE_PATTERN:-}"
# ABS-588: the load-bearing marker line the RTE writes into its epic-handoff
# artifact (rte.md handoff format). Its presence == a reviewable handoff exists.
OPS_EPIC_HANDOFF_MARKER="${OPS_EPIC_HANDOFF_MARKER:-EPIC-HANDOFF-READY}"
OPS_CI_CONFIG="${OPS_CI_CONFIG:-$OPS_REPO/.gitlab-ci.yml}"
OPS_RUNNER_COUNT="${OPS_RUNNER_COUNT:-}"
OPS_CI_PROJECT="${OPS_CI_PROJECT:-}"

now_epoch() { echo "${OPS_NOW:-$(date -u +%s)}"; }

# mtime_of <path> — epoch mtime, GNU `stat -c` first then BSD `stat -f` (ABS-246:
# GNU-first is load-bearing — `stat -f` succeeds as a filesystem query on GNU).
mtime_of() {
    local p="$1" m
    m="$(stat -c %Y "$p" 2>/dev/null || stat -f %m "$p" 2>/dev/null || echo '')"
    case "$m" in ''|*[!0-9]*) return 1 ;; esac
    echo "$m"
}

# g <args...> — git scoped to the inspected repo, read-only.
g() { git -C "$OPS_REPO" "$@" 2>/dev/null; }

# unmerged_count <branch> — commits on <branch> whose patch is NOT yet in the
# target (git cherry marks these '+'). This is patch-id based, so it correctly
# treats a REBASE/SQUASH-merged branch as merged (0) where a plain ancestor check
# would false-positive on the rewritten SHAs.
unmerged_count() { g cherry "$OPS_TARGET_BRANCH" "$1" | grep -c '^+'; }

# emit <class> <ticket> <evidence> <suggestion> — one finding line.
emit() { printf '%s %s %s %s\n' "$1" "${2:--}" "$3" "$4"; }

# live_cwds — newline list of the cwd path of every currently-living process that
# could be holding a seat worktree. This is the SEAM that makes stale-lock's
# liveness cross-check deterministically testable without spawning a real process:
#   * OPS_LIVE_CWDS_FILE set  -> authoritative source, one cwd per line (an empty
#     or absent path means "no live seats"; lsof is NEVER consulted). Tests inject this.
#   * unset (production)      -> lsof over every `claude` process's cwd descriptor
#     (`-a -c claude -d cwd -Fn`, the operator's "lsof … -d cwd über alle claude-Prozesse").
live_cwds() {
    if [ -n "${OPS_LIVE_CWDS_FILE:-}" ]; then
        [ -f "$OPS_LIVE_CWDS_FILE" ] && cat "$OPS_LIVE_CWDS_FILE" || true
        return 0
    fi
    command -v lsof >/dev/null 2>&1 || return 0
    lsof -a -c claude -d cwd -Fn 2>/dev/null | sed -n 's/^n//p'
}

# worktree_alive <ticket> <cwds> — 0 if any live cwd sits inside <ticket>'s seat
# worktree. A cwd belongs to the ticket when the id appears as a path component
# prefix ("/<ticket>-…" e.g. tmp/PILOT-50-work, or a subdir thereof), bounded by
# `-`/`/`/end so PILOT-5 never matches PILOT-50.
worktree_alive() {
    local ticket="$1" cwds="$2"
    [ -n "$cwds" ] || return 1
    printf '%s\n' "$cwds" | grep -qE "/${ticket}(-|/|\$)"
}

# active_remote — the branch's configured push remote, else origin, else first remote.
active_remote() {
    if [ -n "${OPS_TARGET_REMOTE:-}" ]; then echo "$OPS_TARGET_REMOTE"; return; fi
    local r
    r="$(g config "branch.$OPS_MAIN_BRANCH.remote")"
    [ -n "$r" ] && { echo "$r"; return; }
    if g remote | grep -qx origin; then echo origin; return; fi
    g remote | head -1
}

# ---- ticket-file helpers (mock-tracker markdown: frontmatter + ## Comments) --
tk_field()  { grep -E "^$2:" "$1" 2>/dev/null | head -1 | sed -E "s/^$2:[[:space:]]*//"; }
# newest ISO-8601 timestamp of a comment whose header matches "kind: <2>" (prefix).
tk_newest_kind_ts() {
    grep -E "^### .* \| kind: $2" "$1" 2>/dev/null \
        | sed -E 's/^### ([0-9TZ:.-]+).*/\1/' | sort | tail -1
}

# =============================================================================
# Detector 1 — worktree-hygiene
#   (a) main checkout HEAD != expected main branch
#   (b) a registered worktree whose directory has vanished (orphaned)
#   (c) main checkout has TRACKED uncommitted changes (PILOT-75 AC3): a Doku/PO/RTE
#       seat left work uncommitted in the main checkout — a FEHLERZUSTAND, not a
#       Zwischenstand. The next operator fast-forward would silently discard it
#       (the PILOT-44 Befund, ABS-581). Untracked files are ignored (--untracked-
#       files=no): the runner writes gitignored state, and only tracked-but-
#       uncommitted edits are the lost-work signature.
# =============================================================================
detect_worktree_hygiene() {
    [ -d "$OPS_REPO/.git" ] || g rev-parse --git-dir >/dev/null || return 0
    local head dirty
    head="$(g symbolic-ref --short HEAD)"
    if [ -n "$head" ] && [ "$head" != "$OPS_MAIN_BRANCH" ]; then
        emit worktree-hygiene - "head=$head,expected=$OPS_MAIN_BRANCH" "reset-main-checkout-to-$OPS_MAIN_BRANCH"
    fi
    # (c) unclean main checkout — tracked, uncommitted changes only.
    dirty="$(g status --porcelain --untracked-files=no 2>/dev/null | grep -c '[^[:space:]]' || true)"
    if [ "${dirty:-0}" -gt 0 ] 2>/dev/null; then
        emit worktree-hygiene - "unclean-main-checkout=${dirty}-file(s),branch=${head:--}" "commit-and-push-or-discard-main-checkout-edits"
    fi
    # `git worktree list --porcelain`: blocks of "worktree <path>" / "branch <ref>"
    # separated by blank lines. A trailing blank line (appended below, since
    # command substitution strips it) closes the final block in one place.
    local wt="" br=""
    while IFS= read -r line; do
        case "$line" in
            "worktree "*) wt="${line#worktree }"; br="" ;;
            "branch "*)   br="${line#branch refs/heads/}" ;;
            "")  # end of a block
                if [ -n "$wt" ] && [ ! -d "$wt" ]; then
                    emit worktree-hygiene - "worktree=$wt,branch=${br:--}" "prune-orphaned-worktree"
                fi
                wt=""; br="" ;;
        esac
    done <<EOF
$(g worktree list --porcelain)

EOF
}

# =============================================================================
# Detector 2 — dep-release-due
#   A Blocked ticket whose depends_on names a dep whose story branch head is
#   already an ANCESTOR of the target branch (merge-base --is-ancestor) => the
#   block should have been released.
# =============================================================================
detect_dep_release_due() {
    [ -n "$OPS_TICKETS_DIR" ] && [ -d "$OPS_TICKETS_DIR" ] || return 0
    local f status deps dep sha
    for f in "$OPS_TICKETS_DIR"/*.md; do
        [ -f "$f" ] || continue
        status="$(tk_field "$f" status)"
        [ "$status" = "Blocked" ] || continue
        deps="$(tk_field "$f" depends_on | tr -d '[]' | tr ',' ' ')"
        [ -n "$deps" ] || continue
        for dep in $deps; do
            dep="$(echo "$dep" | tr -d ' "')"
            [ -n "$dep" ] || continue
            sha="$(g rev-parse --verify --quiet "$dep-auto" \
                   || g rev-parse --verify --quiet "refs/remotes/$(active_remote)/$dep-auto")"
            [ -n "$sha" ] || continue
            if g merge-base --is-ancestor "$sha" "$OPS_TARGET_BRANCH"; then
                emit dep-release-due "$(basename "$f" .md)" \
                    "dep=$dep,sha=$(echo "$sha" | cut -c1-8),target=$OPS_TARGET_BRANCH" \
                    "release-from-blocked"
            fi
        done
    done
}

# =============================================================================
# Detector 3 — handoff-nomove-actionable
#   Newest comment is a handoff carrying a verdict / draft path, with NO later
#   transition — the declared move never happened.
# =============================================================================
detect_handoff_nomove_actionable() {
    [ -n "$OPS_TICKETS_DIR" ] && [ -d "$OPS_TICKETS_DIR" ] || return 0
    local f h_ts t_ts body draft draft_state target
    for f in "$OPS_TICKETS_DIR"/*.md; do
        [ -f "$f" ] || continue
        h_ts="$(tk_newest_kind_ts "$f" handoff)"
        [ -n "$h_ts" ] || continue
        t_ts="$(tk_newest_kind_ts "$f" transition)"
        # A transition at or after the handoff means the move happened -> not actionable.
        [ -n "$t_ts" ] && [ ! "$h_ts" \> "$t_ts" ] && continue
        body="$(cat "$f")"
        echo "$body" | grep -qiE 'APPROVED|REJECTED|draft|verdict' || continue
        draft="$(echo "$body" | grep -oE 'work/[A-Za-z0-9._/-]+\.md' | head -1)"
        if [ -z "$draft" ]; then draft_state="none"
        elif [ -f "$OPS_REPO/$draft" ] || [ -f "$draft" ]; then draft_state="exists"
        else draft_state="missing"; fi
        target="$(echo "$body" | grep -oiE 'exit:?[[:space:]]*[A-Za-z ]+' | head -1 | sed -E 's/.*://; s/^[[:space:]]*//; s/[[:space:]]*$//; s/ /_/g')"
        emit handoff-nomove-actionable "$(basename "$f" .md)" \
            "ts=$h_ts,draft=$draft_state,target=${target:--}" "post-comment-and-transition"
    done
}

# =============================================================================
# Detector 4 — missing-mr
#   A *-auto branch pushed to the remote, with commits ahead of target and not
#   merged into it: a candidate whose MR is missing/unverified.
# =============================================================================
detect_missing_mr() {
    g rev-parse --git-dir >/dev/null || return 0
    local remote br ahead sha
    remote="$(active_remote)"
    while IFS= read -r br; do
        [ -n "$br" ] || continue
        case "$br" in *-auto) ;; *) continue ;; esac
        # Must be PUSHED (remote ref exists) to be a "missing MR" rather than recoverable.
        g rev-parse --verify --quiet "refs/remotes/$remote/$br" >/dev/null || continue
        sha="$(g rev-parse --verify --quiet "$br")"
        [ -n "$sha" ] || continue
        ahead="$(unmerged_count "$br")"                                    # patch-id merged => 0
        [ "${ahead:-0}" -gt 0 ] 2>/dev/null || continue
        emit missing-mr "${br%-auto}" "branch=$br,ahead=$ahead,target=$OPS_TARGET_BRANCH" "open-or-verify-mr"
    done <<EOF
$(g for-each-ref --format='%(refname:short)' refs/heads)
EOF
}

# =============================================================================
# Detector 5 — branch-recoverable
#   A *-auto branch with commits ahead of target that is NOT on the remote —
#   its commits live only locally / in a seat worktree and can be re-pushed.
# =============================================================================
detect_branch_recoverable() {
    g rev-parse --git-dir >/dev/null || return 0
    local remote br sha ahead
    remote="$(active_remote)"
    while IFS= read -r br; do
        [ -n "$br" ] || continue
        case "$br" in *-auto) ;; *) continue ;; esac
        g rev-parse --verify --quiet "refs/remotes/$remote/$br" >/dev/null && continue  # on remote => not lost
        sha="$(g rev-parse --verify --quiet "$br")"
        [ -n "$sha" ] || continue
        ahead="$(unmerged_count "$br")"                                     # patch-id merged => nothing to recover
        [ "${ahead:-0}" -gt 0 ] 2>/dev/null || continue
        emit branch-recoverable "${br%-auto}" \
            "branch=$br,sha=$(echo "$sha" | cut -c1-8),ahead=$ahead" "restore-push-branch"
    done <<EOF
$(g for-each-ref --format='%(refname:short)' refs/heads)
EOF
}

# =============================================================================
# Detector 6 — stale-lock
#   A per-ticket lock dir older than the TTL (crashed/orphaned seat). The merge/
#   token subtree is excluded (its staleness is holder-liveness, not a clock).
#
#   TTL alone is a FALSE criterion (operator 2026-07-25, marked VERBINDLICH — the
#   costliest misclass, because a false "stale" leads a downstream actuator to
#   double-dispatch onto LIVE work): a lock is stale ONLY IF it is past TTL AND no
#   living process has its cwd inside the ticket's seat worktree. The liveness
#   lookup goes through live_cwds(), which is env-injectable (OPS_LIVE_CWDS_FILE),
#   so a dead PID in the lock but a live claude in the worktree is deterministically
#   NOT flagged — without spawning a real process.
# =============================================================================
detect_stale_lock() {
    local locks="$OPS_STATE_DIR/locks" d ticket now mtime age cwds
    [ -n "$OPS_STATE_DIR" ] && [ -d "$locks" ] || return 0
    now="$(now_epoch)"
    cwds="$(live_cwds)"
    for d in "$locks"/*; do
        [ -d "$d" ] || continue
        ticket="$(basename "$d")"
        [ "$ticket" = "merge" ] && continue
        mtime="$(mtime_of "$d")" || continue
        age=$((now - mtime))
        [ "$age" -ge "$OPS_LOCK_TTL" ] || continue
        # Cross-check: a live seat still working under the ticket's worktree keeps
        # the lock legitimate no matter how old the lock dir's mtime is.
        worktree_alive "$ticket" "$cwds" && continue
        emit stale-lock "$ticket" "age=${age},ttl=${OPS_LOCK_TTL}" "clear-stale-lock"
    done
}

# =============================================================================
# Detector 7 — outage-marker-stale
#   An outage / probe-inflight marker older than its window while the run is
#   otherwise progressing (a healthy resume removes it on the next good spawn).
# =============================================================================
detect_outage_marker_stale() {
    [ -n "$OPS_STATE_DIR" ] && [ -d "$OPS_STATE_DIR" ] || return 0
    local now marker name mtime age
    now="$(now_epoch)"
    for name in outage probe-inflight; do
        marker="$OPS_STATE_DIR/$name"
        [ -f "$marker" ] || continue
        mtime="$(mtime_of "$marker")" || continue
        age=$((now - mtime))
        if [ "$age" -ge "$OPS_OUTAGE_STALE" ]; then
            emit outage-marker-stale - "marker=$name,age=${age},window=${OPS_OUTAGE_STALE}" "clear-stale-outage-marker"
        fi
    done
}

# =============================================================================
# Detector 8 — backend-junk-rows
#   seat_spawn rows whose instance_id falls OUTSIDE the operating pattern
#   (env-leakage test junk). Detection only; purge stays human-gated (Tier D).
# =============================================================================
detect_backend_junk_rows() {
    [ -n "$OPS_BACKEND_ROWS" ] && [ -f "$OPS_BACKEND_ROWS" ] && [ -n "$OPS_INSTANCE_PATTERN" ] || return 0
    local id count
    while IFS="$(printf '\t')" read -r id count; do
        [ -n "$id" ] || continue
        case "$id" in \#*) continue ;; esac
        echo "$id" | grep -qE "$OPS_INSTANCE_PATTERN" && continue
        emit backend-junk-rows - "instance=$id,rows=${count:-?}" "backup-and-propose-purge"
    done < "$OPS_BACKEND_ROWS"
}

# =============================================================================
# Detector 9 — epic-handoff-missing (ABS-588)
#   An epic ticket at status "Ready for Epic Acceptance" whose reviewable handoff
#   artifact is ABSENT. The RTE releases the epic to this status for a HUMAN to
#   merge the epic branch to main (ADR-A-0014 — no agent opens/merges that PR),
#   but the human needs ONE named next step + the verification state, not a bare
#   branch name (Pilot 7: MR !231 was assembled by hand from the log). The artifact
#   is the RTE gate-results comment carrying the OPS_EPIC_HANDOFF_MARKER token; its
#   absence at this status is the finding (AC4) — so the epic is reported, never
#   left silently reading as "waiting for human" while it waits on a missing artifact.
# =============================================================================
detect_epic_handoff_missing() {
    [ -n "$OPS_TICKETS_DIR" ] && [ -d "$OPS_TICKETS_DIR" ] || return 0
    local f status id
    for f in "$OPS_TICKETS_DIR"/*.md; do
        [ -f "$f" ] || continue
        status="$(tk_field "$f" status)"
        [ "$status" = "Ready for Epic Acceptance" ] || continue
        grep -qF "$OPS_EPIC_HANDOFF_MARKER" "$f" && continue
        id="$(tk_field "$f" id)"; [ -n "$id" ] || id="$(basename "$f" .md)"
        emit epic-handoff-missing "$id" \
            "status=Ready-for-Epic-Acceptance,artifact=absent" "post-epic-handoff-artifact"
    done
}

# =============================================================================
# Detector 10 — ci-capacity (ABS-595)
#   A shipped CI config with NO execution capacity paralyses the WHOLE automerge
#   lane: every MR pipeline dies in the stuck-timeout (failure_reason=
#   stuck_or_timeout_failure) and the RTE seat waits on a pipeline that can never
#   finish. This sensor names it ONCE, before the first seat hangs on it — instead
#   of every MR suffering it individually (AC4). Signature: a `.gitlab-ci.yml`
#   exists AND the project has zero runners that can pick up a job.
#   Runner count: injected via OPS_RUNNER_COUNT (deterministic, fixture-testable);
#   in production, unset it and set OPS_CI_PROJECT so the count is read live via
#   ci-capacity-probe.sh. Count unknown => skip (no false alarm).
# =============================================================================
detect_ci_capacity() {
    [ -f "$OPS_CI_CONFIG" ] || return 0
    local runners="$OPS_RUNNER_COUNT"
    if [ -z "$runners" ] && [ -n "$OPS_CI_PROJECT" ]; then
        runners="$("$(dirname "$0")/ci-capacity-probe.sh" runners "$OPS_CI_PROJECT" 2>/dev/null)"
    fi
    case "$runners" in ''|*[!0-9]*) return 0 ;; esac   # unknown -> skip
    if [ "$runners" -eq 0 ]; then
        emit ci-capacity - "ci-config=$(basename "$OPS_CI_CONFIG"),runners=0" "register-a-runner-or-remove-the-ci-config"
    fi
}

# ---- driver -----------------------------------------------------------------
ALL_DETECTORS="worktree-hygiene dep-release-due handoff-nomove-actionable missing-mr branch-recoverable stale-lock outage-marker-stale backend-junk-rows epic-handoff-missing ci-capacity"

run_one() {
    case "$1" in
        worktree-hygiene)           detect_worktree_hygiene ;;
        dep-release-due)            detect_dep_release_due ;;
        handoff-nomove-actionable)  detect_handoff_nomove_actionable ;;
        missing-mr)                 detect_missing_mr ;;
        branch-recoverable)         detect_branch_recoverable ;;
        stale-lock)                 detect_stale_lock ;;
        outage-marker-stale)        detect_outage_marker_stale ;;
        backend-junk-rows)          detect_backend_junk_rows ;;
        epic-handoff-missing)       detect_epic_handoff_missing ;;
        ci-capacity)                detect_ci_capacity ;;
        *) echo "ops-sweep-sensors: unknown detector '$1'" >&2; return 64 ;;
    esac
}

main() {
    case "${1:-}" in
        --list) printf '%s\n' $ALL_DETECTORS; return 0 ;;
        -h|--help) sed -n '2,50p' "$0"; return 0 ;;
    esac
    local detectors="$ALL_DETECTORS"
    [ "$#" -gt 0 ] && detectors="$*"
    local d
    for d in $detectors; do
        run_one "$d" || return 64
    done
    return 0
}

main "$@"
