# =============================================================================
# ABS-331 — jira-tracker search: canonical priority column + ORDER BY created ASC
# -----------------------------------------------------------------------------
# Per-story include (ABS-215): `source`d by tests/test-orchestrator.sh into the
# live harness. In scope from the parent: assert_*, orch / tracker / new_env /
# cleanup_env, PASS/FAIL/TOTAL, REPO_ROOT / ORCH / TRACKER.
#
# Follow-up of the accepted ABS-261 priority-aware dispatch. The adapter `search`
# surface now emits the canonical priority (ABS-242 label mapping) as a column
# and orders results age-ASC within the fence, so the orchestrator reads priority
# straight from the sweep instead of a per-row `tracker get` (that per-row read is
# unit-proven gone in tests/test-abs331-prioritize-rows.sh — AC3). Absent/unmapped
# priority => normal (full backward compat, AC4). The zero-get prioritization
# itself is asserted in that unit test; here we cover the adapter surface (AC1),
# the age-ASC ordering at mock parity (AC2), and the no-priority regression (AC4).
# =============================================================================

# Late monolith sections rebind tracker() to a per-id stub; restore the real
# adapter driver (same fix as the ABS-261 / ABS-304 includes).
tracker() { bash "$TRACKER" "$@"; }

echo -e "\n${CYAN}ABS-331 — search emits a priority column + age-ASC order${NC}"

# --- AC1: search emits a canonical priority column (default normal) -------------
new_env
H=$(tracker create --type ticket --title hotone  --label orchestrator-ready --priority hotfix | awk '{print $NF}')
N=$(tracker create --type ticket --title plainone --label orchestrator-ready                    | awk '{print $NF}')
rows=$(tracker search)
# Layout is id<TAB>type<TAB>status<TAB>priority<TAB>title — exactly 5 columns.
cols=$(printf '%s\n' "$rows" | head -1 | awk -F'\t' '{print NF}')
assert_eq "$cols" "5" "ABS-331 AC1: search rows carry 5 tab-separated columns (priority added)"
hprio=$(printf '%s\n' "$rows" | awk -F'\t' -v id="$H" '$1==id{print $4}')
nprio=$(printf '%s\n' "$rows" | awk -F'\t' -v id="$N" '$1==id{print $4}')
assert_eq "$hprio" "hotfix" "ABS-331 AC1: the priority column carries the ticket's canonical priority"
assert_eq "$nprio" "normal" "ABS-331 AC1: an unset priority defaults to normal in the column"
cleanup_env

# --- AC2: results are age-ASC within the fence (mock/live parity) ---------------
# Create three, then rewrite `created` so age order != id/creation order. search
# must return them oldest-first regardless of on-disk/key order.
new_env
A=$(tracker create --type ticket --title aaa --label orchestrator-ready | awk '{print $NF}')
B=$(tracker create --type ticket --title bbb --label orchestrator-ready | awk '{print $NF}')
C=$(tracker create --type ticket --title ccc --label orchestrator-ready | awk '{print $NF}')
# Age order chosen deliberately out of id order: C (oldest) -> A -> B (newest).
set_created() { sed "s/^created: .*/created: $2/" "$MOCK_TRACKER_TICKETS_DIR/$1.md" > "$MOCK_TRACKER_TICKETS_DIR/$1.md.tmp" && mv "$MOCK_TRACKER_TICKETS_DIR/$1.md.tmp" "$MOCK_TRACKER_TICKETS_DIR/$1.md"; }
set_created "$C" "2026-01-01T00:00:00Z"
set_created "$A" "2026-02-01T00:00:00Z"
set_created "$B" "2026-03-01T00:00:00Z"
order=$(tracker search | cut -f1 | tr '\n' ' ')
assert_eq "$order" "$C $A $B " "ABS-331 AC2: search returns rows age-ASC (created), not id/on-disk order"
cleanup_env

# --- AC2 tiebreak: equal timestamps keep a deterministic (on-disk) order --------
new_env
P=$(tracker create --type ticket --title pp --label orchestrator-ready | awk '{print $NF}')
Q=$(tracker create --type ticket --title qq --label orchestrator-ready | awk '{print $NF}')
set_created() { sed "s/^created: .*/created: $2/" "$MOCK_TRACKER_TICKETS_DIR/$1.md" > "$MOCK_TRACKER_TICKETS_DIR/$1.md.tmp" && mv "$MOCK_TRACKER_TICKETS_DIR/$1.md.tmp" "$MOCK_TRACKER_TICKETS_DIR/$1.md"; }
set_created "$P" "2026-05-01T00:00:00Z"
set_created "$Q" "2026-05-01T00:00:00Z"
order=$(tracker search | cut -f1 | tr '\n' ' ')
assert_eq "$order" "$P $Q " "ABS-331 AC2: equal timestamps fall back to a stable on-disk order"
cleanup_env

# --- AC4: a no-priority tree dispatches exactly as before (backward compat) ------
# Every row's column reads normal, so priority-on and priority-off must make the
# identical spawn decision — the key-first (age-first) ticket keeps the slot.
new_env
export ORCH_ASYNC_SPAWNS=0 ORCH_MAX_CONCURRENT=1
F=$(tracker create --type ticket --title first  --label orchestrator-ready | awk '{print $NF}')
S=$(tracker create --type ticket --title second --label orchestrator-ready | awk '{print $NF}')
allnormal=$(tracker search | awk -F'\t' '$4!="normal"{print "BAD:"$1}')
assert_eq "$allnormal" "" "ABS-331 AC4: a no-priority tree shows priority=normal for every row"
on=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null | grep -E "INTENT SPAWN ticket=" | sort)
off=$(ORCH_PRIORITY_DISPATCH=0 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null | grep -E "INTENT SPAWN ticket=" | sort)
assert_eq "$on" "$off" "ABS-331 AC4: no-priority tree dispatches identically feature-on vs feature-off"
assert_contains "$on" "SPAWN ticket=$F role=po-agent" "ABS-331 AC4: the age-first ticket keeps the single slot (legacy order preserved)"
cleanup_env

unset H N A B C P Q F S rows cols hprio nprio nprio order on off allnormal
