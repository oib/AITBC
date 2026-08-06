# =============================================================================
# ABS-261 — priority-aware slot allocation (hotfix passes wartende Feature-Arbeit)
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/tooling/test-orchestrator.sh into the
# live harness. In scope from the parent: assert_*, orch / tracker / new_env /
# cleanup_env, PASS/FAIL/TOTAL, REPO_ROOT / ORCH / TRACKER.
#
# The reconcile sweep now offers free concurrency slots in canonical-priority
# order (hotfix > high > normal > low; age ASC within a band) BEFORE the cap,
# instead of the adapter's key/arrival order. priority=hotfix may overrun the cap
# by ORCH_HOTFIX_CAP_BONUS (default 1) with NO preemption. Source is the adapter
# dump's `priority` field; absent => normal (full backward compat). Kill-switch
# ORCH_PRIORITY_DISPATCH=0 restores legacy order (ABS-111 pattern).
#
# All cases pin ORCH_ASYNC_SPAWNS=0 so LIVE_SPAWNS (not live_spawn_count of
# background pids) drives the cap synchronously under --dry-run --once, and
# ORCH_MAX_CONCURRENT=1 so "more dispatchable tickets than free slots" holds.
# =============================================================================

# Late monolith sections rebind tracker() to a per-id stub; restore the real
# adapter driver (same fix as the ABS-304 / ABS-225 includes).
tracker() { bash "$TRACKER" "$@"; }

echo -e "\n${CYAN}ABS-261 — priority-aware dispatch (hotfix beats wartende Feature-Arbeit)${NC}"

# --- AC1: at cap=1, the single slot goes to the highest priority ---------------
# Created in key order low -> normal -> hotfix, so key order != priority order.
# bonus=0 isolates the ORDERING decision from the hotfix cap-overrun (AC2).
new_env
export ORCH_ASYNC_SPAWNS=0 ORCH_MAX_CONCURRENT=1 ORCH_HOTFIX_CAP_BONUS=0
L=$(tracker create --type ticket --title lowprio --label orchestrator-ready --priority low | awk '{print $NF}')
N=$(tracker create --type ticket --title normprio --label orchestrator-ready | awk '{print $NF}')
H=$(tracker create --type ticket --title hotprio --label orchestrator-ready --priority hotfix | awk '{print $NF}')
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "SPAWN ticket=$H role=po-agent" "ABS-261 AC1: the hotfix takes the single free slot ahead of key-earlier tickets"
assert_contains "$out" "DEFER-CAP ticket=$N" "ABS-261 AC1: the normal ticket is deferred (rested), not spawned"
assert_contains "$out" "DEFER-CAP ticket=$L" "ABS-261 AC1: the low ticket is deferred (rested), not spawned"
assert_not_contains "$out" "SPAWN ticket=$L role=po-agent" "ABS-261 AC1: the low ticket does NOT get the slot"
cleanup_env

# --- AC4: the DEFER-CAP intent names the deferred ticket's priority ------------
assert_contains "$out" "DEFER-CAP ticket=$N role=po-agent to=Backlog note=priority=normal" \
    "ABS-261 AC4: DEFER-CAP names the priority (operator sees who was preferred)"
assert_contains "$out" "DEFER-CAP ticket=$L role=po-agent to=Backlog note=priority=low" \
    "ABS-261 AC4: DEFER-CAP names a low priority too"

# --- AC2: priority=hotfix overruns the cap by ORCH_HOTFIX_CAP_BONUS (no kill) ---
# Two hotfixes at cap=1 + bonus=1 => BOTH spawn (1 base slot + 1 bonus); a third
# hotfix defers. No running seat is ever killed — the gate only RAISES the
# admission ceiling for the new spawn.
new_env
export ORCH_ASYNC_SPAWNS=0 ORCH_MAX_CONCURRENT=1 ORCH_HOTFIX_CAP_BONUS=1
H1=$(tracker create --type ticket --title h1 --label orchestrator-ready --priority hotfix | awk '{print $NF}')
H2=$(tracker create --type ticket --title h2 --label orchestrator-ready --priority hotfix | awk '{print $NF}')
H3=$(tracker create --type ticket --title h3 --label orchestrator-ready --priority hotfix | awk '{print $NF}')
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$out2" "SPAWN ticket=$H1 role=po-agent" "ABS-261 AC2: first hotfix spawns (base slot)"
assert_contains "$out2" "SPAWN ticket=$H2 role=po-agent" "ABS-261 AC2: second hotfix spawns via the +1 cap bonus (overruns cap=1)"
assert_contains "$out2" "DEFER-CAP ticket=$H3 role=po-agent to=Backlog note=priority=hotfix" \
    "ABS-261 AC2: the third hotfix defers once the cap+bonus ceiling is reached"
cleanup_env

# AC2 control: bonus=0 restores a hard cap even for hotfix (only one spawns).
new_env
export ORCH_ASYNC_SPAWNS=0 ORCH_MAX_CONCURRENT=1 ORCH_HOTFIX_CAP_BONUS=0
H1=$(tracker create --type ticket --title h1 --label orchestrator-ready --priority hotfix | awk '{print $NF}')
H2=$(tracker create --type ticket --title h2 --label orchestrator-ready --priority hotfix | awk '{print $NF}')
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
n_spawn=$(printf '%s\n' "$out3" | grep -c "INTENT SPAWN ticket=.* role=po-agent" || true)
assert_eq "$n_spawn" "1" "ABS-261 AC2 control: bonus=0 gives hotfix no extra slot (exactly one spawns)"
cleanup_env

# --- AC3: absent priority => normal; feature ON == feature OFF (byte-identical) -
# A tree with no priorities dispatches identically whether the feature is on or
# off — the sort is stable and the cap ceiling unchanged for normal tickets.
new_env
export ORCH_ASYNC_SPAWNS=0 ORCH_MAX_CONCURRENT=1
A=$(tracker create --type ticket --title a --label orchestrator-ready | awk '{print $NF}')
B=$(tracker create --type ticket --title b --label orchestrator-ready | awk '{print $NF}')
on=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null | grep -E "INTENT (SPAWN|DEFER-CAP) ticket=" | sort -u)
off=$(ORCH_PRIORITY_DISPATCH=0 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null | grep -E "INTENT (SPAWN|DEFER-CAP) ticket=" | sort -u)
assert_contains "$on" "SPAWN ticket=$A role=po-agent" "ABS-261 AC3: key-first ticket keeps the slot when all priorities are absent (=normal)"
# The spawn/defer SET is unchanged; only the DEFER-CAP note differs (feature on
# annotates priority=normal). Compare the spawn decisions specifically.
on_spawn=$(printf '%s\n' "$on" | grep "INTENT SPAWN" | sort)
off_spawn=$(printf '%s\n' "$off" | grep "INTENT SPAWN" | sort)
assert_eq "$on_spawn" "$off_spawn" "ABS-261 AC3: spawn decisions are identical feature-on vs feature-off (backward compat)"
cleanup_env

# --- AC5: kill-switch ORCH_PRIORITY_DISPATCH=0 -> adapter row order + note-less DEFER-CAP
# The switch disables the RUNNER's own priority preference (re-sort + DEFER-CAP
# note), not the adapter's row order: since ABS-389 every adapter's search emits
# priority ASC, created ASC (task-tracking.md contract), so with the switch off
# the hotfix row still arrives first and keeps the slot — but the runner adds no
# note of its own (the DEFER-CAP line stays byte-identical to pre-ABS-261).
new_env
export ORCH_ASYNC_SPAWNS=0 ORCH_MAX_CONCURRENT=1
L=$(tracker create --type ticket --title lowprio --label orchestrator-ready --priority low | awk '{print $NF}')
H=$(tracker create --type ticket --title hotprio --label orchestrator-ready --priority hotfix | awk '{print $NF}')
legacy=$(ORCH_PRIORITY_DISPATCH=0 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_contains "$legacy" "SPAWN ticket=$H role=po-agent" "ABS-261 AC5: switch=0 follows the adapter row order (ABS-389: hotfix row arrives first, keeps the slot)"
assert_contains "$legacy" "DEFER-CAP ticket=$L role=po-agent to=Backlog" "ABS-261 AC5: the low ticket is deferred under adapter order (runner adds no preference of its own)"
assert_not_contains "$legacy" "DEFER-CAP ticket=$L role=po-agent to=Backlog note=" "ABS-261 AC5: switch=0 emits a note-less DEFER-CAP (byte-identical to pre-ABS-261)"
cleanup_env

# --- AC6: the priority charter line ships in _common-rules ----------------------
# Seats never raise priority; only Human/PO sets hotfix. The rule lives once in
# the shared common-rules body that the spawn seam prepends to every seat.
assert_contains "$(cat "$REPO_ROOT/harness/claude/agents/_common-rules.md")" "never raise a ticket's priority" \
    "ABS-261 AC6: _common-rules carries the priority charter line (seats never raise priority)"

unset L N H H1 H2 H3 A B out out2 out3 n_spawn on off on_spawn off_spawn legacy
