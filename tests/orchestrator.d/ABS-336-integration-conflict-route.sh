# =============================================================================
# ABS-336 — INTEGRATION-CONFLICT forward-fix route (ADR-A-0014 amendment)
# -----------------------------------------------------------------------------
# `source`d by tests/tooling/test-orchestrator.sh into the live harness (no shebang, no
# re-`set -e`, no re-source of the harness). Shares assert_*, PASS/FAIL/TOTAL,
# and REPO_ROOT / ORCH / STUB / TRACKER, plus new_env/baseline/orch/tracker.
#
# WHAT ABS-336 ADDS
#   The Blocked triage recognises the class `integration-conflict` — an epic that
#   blocked FROM `Epic Integration` on a `sync-rebase conflict` (the RTE seat's
#   spec-conformant abort) — and, instead of ending autonomy at the tdm/human
#   triage, routes a forward-fix implementer (role from the FAILING COMMIT's
#   ticket, default be-developer) with a MERGE-not-rebase packet note. On the
#   forward-fix seat's clean handoff the runner routes the epic to
#   `Architecture Review` (re-review), NOT straight back to Epic Integration.
#
# AC coverage:
#   AC1 — triage class integration-conflict is recognised (INTEGRATION-CONFLICT
#          intent) and a forward-fix implementer is dispatched.
#   AC2 — the spawned role is DERIVED from the failing commit's ticket role:
#          frontmatter (fe-developer here), not the default.
#   AC2b — fallback: no failing-commit ticket → be-developer default.
#   AC3 — after the forward-fix handoff the runner routes the epic to
#          Architecture Review (RUNNER-TRANSITION + final status), not Epic
#          Integration.
#   AC4 — the forward-fix packet note carries the MERGE (never rebase) doctrine
#          and the commits: handoff requirement.
#   AC5 — negatives: a non-sync-rebase Blocked and a non-Epic-Integration origin
#          both keep the legacy tdm triage (no INTEGRATION-CONFLICT route); the
#          kill-switch (ORCH_INTEGRATION_CONFLICT_ROUTE=0) also restores tdm.
# =============================================================================

echo -e "\n${CYAN}=== ABS-336 integration-conflict forward-fix route ===${NC}\n"

# _walk_to_epic_integration <epic> — drive the epic legally through the pipeline
# to Epic Integration (the only legal predecessor chain), so the subsequent
# `-> Blocked` transition records `Epic Integration -> Blocked.` as its from.
_walk_to_epic_integration() {
    local e="$1" s
    for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" \
             "Architecture Review" "Stories In Flight" "Epic Integration"; do
        tracker transition "$e" "$s" --actor orchestrator --reason "walk" >/dev/null 2>&1
    done
}

# ---------------------------------------------------------------------------
# AC1 + AC2: class recognised, forward-fix role derived from the failing commit
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10

S=$(tracker create --type ticket --title "ABS-336 failing story" --role fe-developer | tail -1)
E=$(tracker create --type epic --title "ABS-336 epic AC1" | tail -1)
_walk_to_epic_integration "$E"
tracker comment "$E" --kind gate-results --actor rte \
    --body "RTE integration gate: Failing commit: deadbee1 on foo.ts [$S]. Abort, branch untouched (ADR-A-0014)." >/dev/null
# Consume all creation/walk events so the next --once sees only the fresh block.
baseline
tracker transition "$E" "Blocked" --actor rte \
    --reason "sync-rebase conflict on the epic integration branch; RTE abort, branch untouched" >/dev/null

out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1)
assert_contains "$out" "INTENT INTEGRATION-CONFLICT ticket=$E" \
    "ABS-336 AC1: Epic-Integration sync-rebase block recognised as integration-conflict"
assert_contains "$out" "INTENT SPAWN ticket=$E role=fe-developer to=Blocked" \
    "ABS-336 AC2: forward-fix spawn role derived from the failing commit's ticket (fe-developer)"
cleanup_env

# ---------------------------------------------------------------------------
# AC2b: fallback role — no failing-commit ticket named → be-developer default
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10

E=$(tracker create --type epic --title "ABS-336 epic AC2b" | tail -1)
_walk_to_epic_integration "$E"
# No "Failing commit: ... [ABS-nnn]" gate comment at all.
baseline
tracker transition "$E" "Blocked" --actor rte \
    --reason "sync-rebase conflict on the epic integration branch; RTE abort, branch untouched" >/dev/null

out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1)
assert_contains "$out" "INTENT INTEGRATION-CONFLICT ticket=$E role=be-developer" \
    "ABS-336 AC2b: absent failing-commit ticket → forward-fix defaults to be-developer"
cleanup_env

# ---------------------------------------------------------------------------
# AC3 + AC4: live handoff routes to Architecture Review; packet note carries the
#            MERGE doctrine + commits: requirement.
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_WORKTREE_SPAWNS=0   # epic-pipeline seats are not runner-worktree-isolated (as today's rte)

S=$(tracker create --type ticket --title "ABS-336 failing story AC3" --role data-engineer | tail -1)
E=$(tracker create --type epic --title "ABS-336 epic AC3" | tail -1)
_walk_to_epic_integration "$E"
tracker comment "$E" --kind gate-results --actor rte \
    --body "RTE integration gate: Failing commit: cafef00d on bar.ts [$S]. Abort, branch untouched (ADR-A-0014)." >/dev/null
baseline
tracker transition "$E" "Blocked" --actor rte \
    --reason "sync-rebase conflict on the epic integration branch; RTE abort, branch untouched" >/dev/null

out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>&1)
assert_contains "$out" "INTENT SPAWN ticket=$E role=data-engineer to=Blocked" \
    "ABS-336 AC3 setup: live forward-fix spawn with the derived role (data-engineer)"
assert_contains "$out" "INTENT RUNNER-TRANSITION ticket=$E role=data-engineer to=Architecture Review" \
    "ABS-336 AC3: clean forward-fix handoff routes the epic to Architecture Review"
status=$(tracker get "$E" | grep '^status:' | head -1)
assert_eq "$status" "status: Architecture Review" \
    "ABS-336 AC3: epic rests at Architecture Review (re-review), not back at Epic Integration"

# AC4: the packet note comment carries the merge doctrine + commits: requirement.
dump=$(tracker get "$E")
assert_contains "$dump" "INTEGRATION-CONFLICT-FORWARDFIX" \
    "ABS-336 AC4: forward-fix packet note posted on the epic"
assert_contains "$dump" "MERGE origin/main INTO the epic integration branch" \
    "ABS-336 AC4: packet note mandates MERGE (never rebase / rewrite history)"
assert_contains "$dump" "Do NOT rebase" \
    "ABS-336 AC4: packet note forbids rebase / history rewrite"
assert_contains "$dump" "Feature-Union" \
    "ABS-336 AC4: packet note carries the Feature-Union doctrine"
assert_contains "$dump" "commits: line" \
    "ABS-336 AC4: packet note requires a commits: line in the handoff"
cleanup_env

# ---------------------------------------------------------------------------
# AC5-a: a Blocked from Epic Integration WITHOUT the sync-rebase phrase keeps the
#         legacy tdm triage (no INTEGRATION-CONFLICT route).
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10

E=$(tracker create --type epic --title "ABS-336 epic AC5a" | tail -1)
_walk_to_epic_integration "$E"
baseline
tracker transition "$E" "Blocked" --actor rte \
    --reason "staging smoke failed; deploy could not be reached (transient)" >/dev/null

out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1)
assert_not_contains "$out" "INTENT INTEGRATION-CONFLICT ticket=$E" \
    "ABS-336 AC5-a: Epic-Integration block without 'sync-rebase conflict' is NOT an integration-conflict"
assert_contains "$out" "INTENT SPAWN ticket=$E role=tdm to=Blocked" \
    "ABS-336 AC5-a: non-conflict Epic-Integration block keeps the legacy tdm triage"
cleanup_env

# ---------------------------------------------------------------------------
# AC5-b: a sync-rebase-phrased block from a NON-Epic-Integration origin keeps tdm.
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10

T=$(tracker create --type ticket --title "ABS-336 story AC5b" --role be-developer | tail -1)
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
tracker transition "$T" "In Progress" --actor be-developer --reason claim >/dev/null
baseline
tracker transition "$T" "Blocked" --actor be-developer \
    --reason "sync-rebase conflict while pulling — mentions the phrase but not from Epic Integration" >/dev/null

out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1)
assert_not_contains "$out" "INTENT INTEGRATION-CONFLICT ticket=$T" \
    "ABS-336 AC5-b: sync-rebase phrase from a non-Epic-Integration origin is NOT an integration-conflict"
assert_contains "$out" "INTENT SPAWN ticket=$T role=tdm to=Blocked" \
    "ABS-336 AC5-b: non-Epic-Integration block keeps the legacy tdm triage"
cleanup_env

# ---------------------------------------------------------------------------
# AC5-c: kill-switch ORCH_INTEGRATION_CONFLICT_ROUTE=0 restores tdm-only triage.
# ---------------------------------------------------------------------------
new_env
export ORCH_MAX_CONCURRENT=10
export ORCH_INTEGRATION_CONFLICT_ROUTE=0

S=$(tracker create --type ticket --title "ABS-336 failing story AC5c" --role fe-developer | tail -1)
E=$(tracker create --type epic --title "ABS-336 epic AC5c" | tail -1)
_walk_to_epic_integration "$E"
tracker comment "$E" --kind gate-results --actor rte \
    --body "RTE integration gate: Failing commit: deadbee2 on baz.ts [$S]. Abort, branch untouched." >/dev/null
baseline
tracker transition "$E" "Blocked" --actor rte \
    --reason "sync-rebase conflict on the epic integration branch; RTE abort, branch untouched" >/dev/null

out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>&1)
assert_not_contains "$out" "INTENT INTEGRATION-CONFLICT ticket=$E" \
    "ABS-336 AC5-c: kill-switch off → no integration-conflict route"
assert_contains "$out" "INTENT SPAWN ticket=$E role=tdm to=Blocked" \
    "ABS-336 AC5-c: kill-switch off → legacy tdm triage runs unchanged"
cleanup_env

unset -f _walk_to_epic_integration 2>/dev/null || true
