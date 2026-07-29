# ABS-115 Design Spec — Iteration-Guard v2 (real bounces + two-level counting)

**Ticket**: ABS-115 (epic ABS-114) · **Status**: accepted (architect review 2026-07-07: approve-with-changes, findings F1–F7 incorporated below; #PATH_DECISION (a) confirmed) · **Date**: 2026-07-07
**Supersedes**: the counting model of specs/ABS-12-iteration-guard-spec.md §1 (the rest of ABS-12 —
cap-from-marker, fail-open, interface, wiring — stays in force unchanged).

## 0. Defect being fixed

The ABS-12 guard counts EVERY comment block containing an `Iteration N of M` substring as a bounce.
Observed in the ABS-102 resume run (ABS-107): APPROVE gate results carrying the marker
informationally ("Iteration 1 of 3 (no bounce)") and operator comments quoting a marker were
counted, producing a permanent false-positive cap at In Review AND In Test with zero real bounces.
The live workaround (`ORCH_ITERATION_GUARD` pointed at a nonexistent path) disabled the guard
entirely.

Guard intent (operator refinement 2026-07-07): the guard is a GENERAL per-ticket cost/time brake,
not merely a ping-pong detector — a ticket that eats too many cycles overall must escalate even
without a strict two-seat pattern.

## 1. What counts as a real bounce  `#PATH_DECISION`

Two candidate marker conventions were named in the ticket:

- **(a) CHOSEN — transition-paired counting, no format break.** A bounce is counted only when a
  marker-bearing gate comment (`kind: gate-results` or `kind: handoff`) is followed — before any
  other transition — by a `transition-reason` comment recording a BACKWARD transition. Both
  adapters (mock + Jira) render every adapter-driven status change as a comment with the exact
  body `Transition: <from> -> <to>. Reason: ...` (jira-tracker.sh mirrors the mock's text
  verbatim), so the pairing signal is already present in every ticket dump, for free, across
  adapters. No gate-agent prompt/def changes, no new token to teach, and historic tickets parse
  correctly.
- **(b) REJECTED — explicit `BOUNCE-MARKER n/m` machine token.** Trivial to parse but requires
  updating every gate agent def AND the orchestrator's own cap comment, creates a migration window
  where old-format bounces are invisible, and still needs the transition data to attribute a
  bounce to a gate for per-gate reset. Option (a) gets the same precision from data the adapters
  already emit (ADR-A-0010: minimal change).

Consequences of (a):
- An APPROVE comment carrying "Iteration 1 of 3 (no bounce)" is followed by a FORWARD transition →
  not counted.
- An operator/decision/notification comment quoting a marker has a non-bounce `kind` → never
  eligible, regardless of transitions.
- A backward transition WITHOUT a preceding marker comment (PO deprioritization, operator
  rerouting, Blocked round-trips) is NOT a bounce — it is not an implement↔validate loop.

## 2. Direction: the status rank table

Backward/forward is decided from the canonical happy paths in
`profiles/neutral/adapters/statuses.yaml` (story and epic pipelines). The guard embeds the two
ordered rank lists (story: Backlog → Design → Ready for Development → In Progress → In Review →
Security Review → Test Prep → In Test → Design Test → Story Acceptance → Merging → Docs →
Ready for Human Acceptance → Ready for Merge → Done; epic: Backlog → PO Triage → Grooming →
Enrichment → Ticket Review → Architecture Review → Stories In Flight → Epic Integration →
Ready for Epic Acceptance → Epic Done) with a comment pinning them to statuses.yaml.

- `backward` = rank(to) < rank(from), both statuses in the same pipeline list.
- **Neutral** (neither bounce nor reset): any transition touching `Blocked` or
  `Needs PO Decision`, any transition whose from/to is unknown to both rank lists, and cross-list
  pairs. Neutral keeps the fail-open spirit: unparseable history never inflates a counter.

Rejected alternative: parsing rank order out of statuses.yaml at runtime — the file's `next:`
edges form a graph, not an order; deriving a total order from it is speculative and fragile
(same reasoning as the guard's existing NOTE on profile-based tracker resolution).

Drift risk (architect F4): this rank table is the THIRD copy of the chain order — orchestrator.sh
already embeds it twice (`chain_index`, `rework_count`'s `idx()`). Accepted because the guard must
stay standalone/dependency-free, but the test suite pins the guard's embedded lists against the
`- name:` document order of statuses.yaml (drift test) so a future status change cannot silently
diverge. The guard additionally ranks the v1/v2 human statuses (Ready for Human Acceptance, Ready
for Merge) that `chain_index` treats as neutral — needed so the v1/v2 pass route
(In Test → Ready for Human Acceptance) still counts as forward progress for the per-gate reset.

CLI/hook asymmetry (architect F7, deliberate forward-compatibility): the orchestrator's CLI-mode
call only covers `is_bounce_status` (In Review, In Test) today; the full rank table is exercised
by hook mode for every gate and is ready for ABS-116/118-era dispatch extensions without a guard
change.

## 3. Two-level counting model (operator-decided 2026-07-07)

Walk the ticket's comment blocks chronologically once:

1. **Per-gate counter** `count[G]` where `G` = the `from` status of each real bounce.
   - Real bounce at G → `count[G] += 1`.
   - FORWARD transition with `from == G` → `count[G] = 0` (forward progress over that gate resets
     ONLY that gate; a later fall back to the same gate counts fresh; other gates untouched).
   - No ticket-wide full reset exists.
2. **Cumulative ticket counter** `total` — every real bounce increments it; it NEVER resets. This
   is the budget brake (ADR-A-0009).

Caps:
- Per-gate cap `M`: from the most recent marker on the ticket, default 3 (unchanged ABS-12 rule).
- Cumulative cap: `ITERATION_GUARD_TICKET_CAP` env, **default 9 = 3× the default gate cap**
  (ticket's proposal, confirmed here). Not marker-derived: a per-ticket marker only speaks for its
  own loop; the budget brake must not be widenable by a gate agent writing "of 12".

Block decision (the bounce about to happen is the next one):
- Gate level: `count[current_status] + 1 >= M` → exit 2 (message names the gate).
- Ticket level: `total + 1 >= ITERATION_GUARD_TICKET_CAP` → exit 2 (message says cumulative
  budget). Both escalate to Needs PO Decision via the existing orchestrator §5.5 path (which
  currently transitions to Blocked — see §5).

`current_status` is read from the dump's frontmatter `status:` line. If it cannot be read →
fail-open for the gate level, but the cumulative check still applies (it needs no gate identity).

### 3.1 Relation to the §3.2 rework counter (architect F1)

The orchestrator already has a cumulative cross-stage brake: `rework_count` (ABS-74, spec §3.2,
`ORCH_REWORK_LIMIT` default 3). The two counters are deliberately DISTINCT and both stay:

- `rework_count` is **windowed** — it counts marker-INDEPENDENT backward agent transitions since
  the last `Needs PO Decision` exit and re-arms on every PO decision. It catches "too much churn
  since the last human touch".
- The guard's cumulative counter is **lifetime, never reset** and counts only REAL bounces
  (marker + backward pair). It catches exactly the case §3.2 leaves open: the PO keeps sending
  the ticket back and it keeps bouncing again — each PO round-trip resets §3.2's window, but the
  lifetime budget keeps accumulating. That is the justification for the 9 default (3 full
  §3.2-windows' worth of real bounces).

Escalation interaction: both escalate to `Needs PO Decision`. No double-fire is possible on one
event — the dispatch checks run in one derivation pass and the first blocking check wins
(`kill-switch -> budget -> iteration-guard -> rework-limit -> …`); whichever cap trips first
routes the ticket to the PO and the other counter simply still stands when the ticket returns.

### 3.2 Hook mode vs CLI mode (architect F2)

**CLI mode is authoritative.** The orchestrator calls the guard BEFORE spawning a gate seat
(`iteration_guard_blocks`); at that point all transitions are on record and the counting model is
exact. **Hook mode is best-effort defense-in-depth**: it fires before the gate agent's comment
lands, so it cannot see whether the FOLLOWING transition will be forward or backward.
Approve-at-cap edge: a gate approving on its final allowed iteration (comment "Iteration 3 of 3
(no bounce)" followed by a forward transition) must not be refused. Hook mode therefore allows
any gate comment whose command text carries the literal `no bounce` — the ABS-11 APPROVE
convention. A malicious/looping agent writing "no bounce" into a real bounce comment only evades
the ADVISORY hook layer; the authoritative CLI-mode check at the next dispatch still refuses the
respawn, and the marker-window pairing means the mislabeled comment still counts once its
backward transition lands.

## 4. Interface & compatibility

Unchanged: hook mode + CLI mode, exit 0/2, stderr-only output, fail-open on tracker errors,
adapter resolution, `ITERATION_GUARD_DEFAULT_CAP`. New env: `ITERATION_GUARD_TICKET_CAP`
(default 9; `0` disables the cumulative level — matching the runner's other `0 = off` knobs).

The `ORCH_ITERATION_GUARD` variable itself stays (it is the legitimate override seam); what is
removed is the RUNTIME workaround of pointing it at a nonexistent path — the run recipe docs and
ORCHESTRATOR_SOP drop that instruction, and the e2e dry run re-enables the guard.

## 5. Escalation target: Blocked → Needs PO Decision

`block_for_iteration_cap` in orchestrator.sh currently routes to **Blocked**; the ticket's AC says
both caps escalate to **Needs PO Decision** (consistent with `escalate_rework` and
`record_spawn_crash`, which already route there). Scope of the change (architect F5 — more than
one line): the transition target, the `--reason`, the comment BODY ("Transitioning to Blocked…"),
the `intent` line's target field, and the §5.5 test assertion (`status: Blocked` →
`status: Needs PO Decision`). Legality verified: In Review and In Test both list
Needs PO Decision in their `next:` edges, and `do_spawn_action` guards on `ticket_still_in`, so
the ticket is at the gate status when the block fires. ADR-A-0004-conform (no main-boundary or
irreversibility impact).

## 6. Test plan (tests/test-iteration-guard.sh + test-orchestrator.sh §5.5)

New cases (ABS-107-shaped fixtures):
- informational marker: APPROVE comment with marker + forward transition → no count
- quoted marker: `kind: decision` operator comment quoting a marker → no count
- real bounce: marker comment + backward transition → gate AND cumulative count
- per-gate reset matrix: bounce at G, forward over G, fall back to G → gate counter fresh;
  other gate's counter untouched; cumulative keeps growing
- cumulative cap: real bounces spread over gates each under gate-cap → block on
  ITERATION_GUARD_TICKET_CAP; `0` disables
- neutral transitions: Blocked round-trip and Needs PO Decision detour neither count nor reset
- legacy regression: marker-only history (no transitions) does NOT block — the false-positive fix
  itself, pinned as an explicit case; the old suite's marker-only block fixtures are rewritten
  with real backward transitions so they keep asserting the block paths
- hook-mode cases (architect F3): real-pair histories behind the piped JSON commands; the
  approve-at-cap edge — at cap, a command whose body carries `no bounce` is allowed (exit 0)
- §5.5 orchestrator fixture rewrite (architect F3): the seed gains real backward transitions
  (marker + In Test → In Progress → … loops) BEFORE the baseline snapshot, and the escalation
  assertion moves from `status: Blocked` to `status: Needs PO Decision`
- test-hooks-behavioral.sh guard seeds likewise rewritten to real-pair histories
- drift test (architect F4): the guard's embedded rank lists are compared against the `- name:`
  document order of profiles/neutral/adapters/statuses.yaml

Legacy-history caveat (accepted, extended per architect F6): tickets whose bounces predate
adapter-comment transitions have no transition records and stop counting; bounces routed through
a Blocked/Needs-PO-Decision detour are neutral and escape both this guard AND §3.2 (the Blocked
path triggers TDM triage by design); out-of-band status changes (Jira UI) emit no
transition-reason comment and are invisible to the guard. In all three cases
`ORCH_MAX_SPAWNS_PER_DAY` remains the deliberate outermost brake. Correct trade-off — the
false-positive failure mode is strictly worse than under-counting on these paths.
