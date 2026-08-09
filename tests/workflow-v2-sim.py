#!/usr/bin/env python3
# =============================================================================
# Workflow v2 simulation — executable companion to
# specs/DRAFT-workflow-v2-full-agent-team-spec.md (§5 acceptance test cases)
# =============================================================================
# Simulates the PROPOSED v2 state machine (extended status→role map, JOIN rule,
# SKIP-FORWARD, per-ticket rework counter, follow-up containment, sequential
# merge + bisect, once-per-entry TDM guard, JOIN guards, crash escalation,
# Ticket-Review DoR gate) and runs scenarios S1–S16 as assertions. Python
# stdlib only; deterministic; no orchestrator code touched.
#
# This validates the SPEC's logic before implementation. When the runner work
# starts, these scenarios port to bash E2E dry-runs alongside
# tests/e2e-orchestrator-dryrun.sh, driving the real scripts/orchestrator.sh.
#
# Mutation checks at the end disable one guard each and assert the suite
# FAILS — proving the tests are sensitive to exactly the defects found in the
# 2026-07-05 theoretical reviews (rounds 1 and 2).
#
# Run: python3 tests/workflow-v2-sim.py
# =============================================================================

from collections import deque

STORY_CHAIN = [
    "Design",
    "Implement",
    "Code Review",
    "Security Review",
    "Test Prep",
    "In Test",
    "Design Test",
    "Story Acceptance",
    "Merging",
    "Docs",
    "Done",
]
CONDITIONAL = {"Design": "design", "Security Review": "security", "Test Prep": "data", "Design Test": "design"}
STORY_SPAWN = {
    "Design": "ui-ux-design",
    "Code Review": "system-architect",
    "Security Review": "security-engineer",
    "Test Prep": "data-provisioning-eng",
    "In Test": "qas",
    "Design Test": "qas-design",
    "Story Acceptance": "po-agent",
    "Merging": "rte",
    "Docs": "tech-writer",
}
STORY_OWNED = set(STORY_SPAWN) | {"Implement"}
EPIC_SPAWN = {
    "PO Triage": "po-agent",
    "Grooming": "bsa",
    "Enrichment": "issue-enrichment",
    "Ticket Review": "qas",  # DoR gate (spec §3.10)
    "Architecture Review": "system-architect",
    "Epic Integration": "rte",
    "Epic Done": "self-improvement",
}
REWORK_LIMIT = 3
FOLLOWUP_BUDGET = 5
CRASH_LIMIT = 3
SAFETY_CAP = 300  # global spawn ceiling; hitting it means a runaway loop


class SafetyCapExceeded(Exception):
    pass


class Ticket:
    def __init__(self, tid, ttype, parent=None, flags=(), role="be-developer"):
        self.id, self.type, self.parent = tid, ttype, parent
        self.flags, self.role = set(flags), role
        self.status, self.rework, self.done = None, 0, False
        self.blocked_entries, self.pre_blocked = 0, None
        self.children, self.pending_stories = [], []
        self.followups_created = 0


class Engine:
    def __init__(
        self, join=True, skip=True, rework_guard=True, quiescence=True, empty_guard=True, crash_guard=True, dor_gate=True
    ):
        self.join, self.skip, self.rework_guard = join, skip, rework_guard
        self.quiescence, self.empty_guard = quiescence, empty_guard
        self.crash_guard, self.dor_gate = crash_guard, dor_gate
        self.tickets, self.events = {}, deque()
        self.spawns, self.notifies, self.merges = [], [], []
        self.backlog, self.decisions, self.audits = [], [], []
        self.behaviors = {}  # (role, ticket_id) -> list of actions
        self.pending_followups = []  # (source_story_id, epic_id, ac_blocking)
        self.tdm_guard = set()  # (ticket_id, blocked_entry_no)
        self.crashes = {}  # (ticket_id, status) -> consecutive count

    # --- scenario API ---------------------------------------------------
    def behave(self, role, tid, actions):
        self.behaviors[(role, tid)] = list(actions)

    def start_epic(self, eid, story_flags):
        e = Ticket(eid, "epic")
        e.pending_stories = list(story_flags)
        self.tickets[eid] = e
        self.transition(e, "PO Triage")
        return e

    def human_accept(self, e):
        self.transition(e, "Epic Done")

    def human_reject(self, e, extra_stories):
        e.pending_stories = list(extra_stories)  # forward-fix, never revert
        self.transition(e, "Grooming")

    def human_unblock(self, t):
        self.transition(t, t.pre_blocked)

    def sweep(self):  # follow-up watcher + crash recovery + JOIN re-check
        for _src, eid, acb in self.pending_followups:
            self._spawn("bsa", self.tickets[eid], "Follow-up Decision")
            e = self.tickets[eid]
            if e.followups_created >= FOLLOWUP_BUDGET:
                self._spawn("po-agent", e, "Needs PO Decision")
                self.decisions.append(("followup-overflow", eid))
            else:
                e.followups_created += 1
                if acb:
                    s = self._mk_story(e, f"{eid}-FU{e.followups_created}", ())
                    e.children.append(s)
                    self.transition(s, "Design")
                else:
                    self.backlog.append(f"{eid}-FU{e.followups_created}")
        self.pending_followups = []
        for t in list(self.tickets.values()):  # crash recovery re-derive
            owned = STORY_OWNED if t.type == "story" else set(EPIC_SPAWN)
            if t.status in owned and not any(ev[0] == t.id for ev in self.events):
                self.events.append((t.id, t.status))
        for t in list(self.tickets.values()):  # JOIN re-check after watcher
            if t.type == "epic":
                self._join_check(t)
        self.run()

    # --- mechanics --------------------------------------------------------
    def _mk_story(self, epic, sid, flags):
        s = Ticket(sid, "story", parent=epic.id, flags=flags)
        self.tickets[sid] = s
        return s

    def transition(self, t, to):
        t.status = to
        self.events.append((t.id, to))

    def bounce(self, t, target):
        t.rework += 1
        if self.rework_guard and t.rework >= REWORK_LIMIT:
            t.status = "Needs PO Decision"
            self._spawn("po-agent", t, "Needs PO Decision")
            self.decisions.append(("rework-limit", t.id))
            return
        self.transition(t, target)

    def _next(self, status):
        return STORY_CHAIN[STORY_CHAIN.index(status) + 1]

    def _act(self, role, tid):
        q = self.behaviors.get((role, tid))
        return q.pop(0) if q else "pass"

    def _spawn(self, role, t, status):
        self.spawns.append((role, t.id, status))
        if len(self.spawns) > SAFETY_CAP:
            raise SafetyCapExceeded(f"runaway loop at {role}/{t.id}/{status}")
        return self._act(role, t.id)

    def _crash(self, t, status):
        k = (t.id, status)
        self.crashes[k] = self.crashes.get(k, 0) + 1
        if self.crash_guard and self.crashes[k] >= CRASH_LIMIT:
            t.status = "Needs PO Decision"
            self._spawn("po-agent", t, "Needs PO Decision")
            self.decisions.append(("spawn-failure", t.id))

    def _block(self, t, at_status):
        t.blocked_entries += 1
        t.pre_blocked = at_status
        self.transition(t, "Blocked")

    def _blocked(self, t):
        key = (t.id, t.blocked_entries)
        if key not in self.tdm_guard:  # once-per-entry TDM spawn
            self.tdm_guard.add(key)
            self._spawn("tdm", t, "Blocked")
            self.notifies.append(("escalation", t.id))

    def _join_check(self, epic):
        if not self.join or epic.status != "Stories In Flight":
            return
        if self.quiescence and any(eid == epic.id for (_, eid, _) in self.pending_followups):
            return  # unprocessed follow-ups: wait
        if not epic.children:
            if self.empty_guard:  # vacuous JOIN forbidden
                epic.status = "Needs PO Decision"
                self._spawn("po-agent", epic, "Needs PO Decision")
                self.decisions.append(("empty-epic", epic.id))
                return
        if all(c.done for c in epic.children):
            self.transition(epic, "Epic Integration")

    def run(self):
        while self.events:
            tid, to = self.events.popleft()
            t = self.tickets[tid]
            if t.status != to:  # stale event (re-read guard)
                continue
            if t.type == "story":
                self._story(t, to)
            else:
                self._epic(t, to)

    def _story(self, t, to):
        if to in ("Done", "Needs PO Decision"):
            return
        if to == "Blocked":
            self._blocked(t)
            return
        if to in CONDITIONAL and CONDITIONAL[to] not in t.flags and self.skip:
            self.audits.append((t.id, to, "SKIP-FORWARD"))
            self.transition(t, self._next(to))
            return
        role = t.role if to == "Implement" else STORY_SPAWN[to]
        act = self._spawn(role, t, to)
        if act == "crash":
            self._crash(t, to)  # rests; sweep re-derives
            return
        self.crashes.pop((t.id, to), None)  # consecutive counter resets
        if act == "block":
            self._block(t, to)
            return
        if isinstance(act, tuple) and act[0] == "bounce":
            self.bounce(t, act[1])
            return
        if isinstance(act, tuple) and act[0] in ("followups", "followups-acb"):
            for _i in range(act[1]):
                self.pending_followups.append((t.id, t.parent, act[0] == "followups-acb"))
        if to == "Merging":
            self.merges.append(t.id)  # sequential per epic (FIFO)
        if to == "Docs":
            t.done = True
            t.status = "Done"
            self._join_check(self.tickets[t.parent])
            return
        self.transition(t, self._next(to))

    def _epic(self, e, to):
        if to in ("Stories In Flight", "Ready for Epic Acceptance", "Needs PO Decision"):
            return
        if to == "Blocked":
            self._blocked(e)
            return
        act = self._spawn(EPIC_SPAWN[to], e, to)
        if act == "crash":
            self._crash(e, to)
            return
        self.crashes.pop((e.id, to), None)
        if act == "block":
            self._block(e, to)
            return
        if isinstance(act, tuple) and act[0] == "bounce":
            self.bounce(e, act[1])  # e.g. DoR rework -> Grooming
            return
        if to == "PO Triage":
            self.transition(e, "Grooming")
        elif to == "Grooming":
            self.transition(e, "Enrichment")
        elif to == "Enrichment":
            for flags in e.pending_stories:
                e.children.append(self._mk_story(e, f"{e.id}-S{len(e.children) + 1}", flags))
            e.pending_stories = []
            self.transition(e, "Ticket Review" if self.dor_gate else "Architecture Review")
        elif to == "Ticket Review":  # DoR pass -> release path
            self.transition(e, "Architecture Review")
        elif to == "Architecture Review":
            e.status = "Stories In Flight"
            released = False
            for c in e.children:
                if not c.done and c.status is None:
                    self.transition(c, "Design")
                    released = True
            if not released:
                self._join_check(e)
        elif to == "Epic Integration":
            if isinstance(act, tuple) and act[0] == "bisect":
                bad = self.tickets[act[1]]
                bad.done = False
                self.transition(bad, "Implement")  # reopen, forward-fix
                e.status = "Stories In Flight"
            else:
                self.transition(e, "Ready for Epic Acceptance")
                self.notifies.append(("ready-to-test", e.id))
        elif to == "Epic Done":
            self.notifies.append(("proposals", e.id))


# =============================================================================
# Scenarios S1–S8 (spec §5, review round 1) and S9–S15 (round 2)
# =============================================================================


def _ready(g, eid):
    return [n for n in g.notifies if n == ("ready-to-test", eid)]


def S1(**kw):
    """Happy path: 3 stories, one design-flagged; exactly one NOTIFY."""
    g = Engine(**kw)
    e = g.start_epic("E1", [("design",), (), ()])
    g.run()
    assert _ready(g, "E1") == [("ready-to-test", "E1")]
    g.human_accept(e)
    g.run()
    assert e.status == "Epic Done"
    assert ("self-improvement", "E1", "Epic Done") in g.spawns
    assert len(g.spawns) == 27, f"expected 27 spawns, got {len(g.spawns)}"
    assert ("proposals", "E1") in g.notifies


def S2(**kw):
    """Design flaw loop: qas-design always demands design fix -> rework cap."""
    g = Engine(**kw)
    g.start_epic("E2", [("design",)])
    g.behave("qas-design", "E2-S1", [("bounce", "Design")] * 10)
    g.run()
    s = g.tickets["E2-S1"]
    assert s.status == "Needs PO Decision", s.status
    assert s.rework == REWORK_LIMIT
    assert ("rework-limit", "E2-S1") in g.decisions
    assert len(g.spawns) < 60


def S3(**kw):
    """Design-flagged story runs Design Test; unflagged story skips it."""
    g = Engine(**kw)
    g.start_epic("E3", [("design",), ()])
    g.run()
    flagged = [r for (r, t, _) in g.spawns if t == "E3-S1"]
    plain = [r for (r, t, _) in g.spawns if t == "E3-S2"]
    assert "qas-design" in flagged and "ui-ux-design" in flagged
    assert "qas-design" not in plain and "ui-ux-design" not in plain
    skips = [a for a in g.audits if a[0] == "E3-S2"]
    assert len(skips) == 4, skips  # Design, Security, Test Prep, Design Test


def S4(**kw):
    """Plain story costs exactly 6 spawns."""
    g = Engine(**kw)
    g.start_epic("E4", [()])
    g.run()
    n = len([s for s in g.spawns if s[1] == "E4-S1"])
    assert n == 6, f"expected 6 story spawns, got {n}"


def S5(**kw):
    """Rebase fail bounces story B; smoke fail bisects to story A; no revert."""
    g = Engine(**kw)
    g.start_epic("E5", [(), ()])
    g.behave("rte", "E5-S2", [("bounce", "Implement"), "pass"])  # rebase fail once
    g.behave("rte", "E5", [("bisect", "E5-S1"), "pass"])  # smoke fail once
    g.run()
    assert g.merges == ["E5-S1", "E5-S2", "E5-S1"]  # append-only: no revert
    assert _ready(g, "E5") == [("ready-to-test", "E5")]
    assert g.tickets["E5-S2"].rework == 1


def S6(**kw):
    """Blocked on credentials: TDM once per entry, escalation, resume."""
    g = Engine(**kw)
    g.start_epic("E6", [()])
    g.behave("be-developer", "E6-S1", ["block", "pass"])
    g.run()
    s = g.tickets["E6-S1"]
    assert s.status == "Blocked"
    g.sweep()
    g.sweep()  # no TDM re-spawn
    assert len([x for x in g.spawns if x[0] == "tdm"]) == 1
    assert len([n for n in g.notifies if n[0] == "escalation"]) == 1
    g.human_unblock(s)
    g.run()
    assert _ready(g, "E6") == [("ready-to-test", "E6")]


def S7(**kw):
    """Follow-up storm: 5 to backlog, 6th -> Needs PO Decision; JOIN unaffected."""
    g = Engine(**kw)
    g.start_epic("E7", [(), ()])
    g.behave("qas", "E7-S1", [("followups", 6)])
    g.run()
    g.sweep()
    assert len(g.backlog) == 5, g.backlog
    assert ("followup-overflow", "E7") in g.decisions
    assert _ready(g, "E7") == [("ready-to-test", "E7")]


def S8(**kw):
    """Crash recovery + human rejection = forward-fix, main untouched."""
    g = Engine(**kw)
    e = g.start_epic("E8", [()])
    g.behave("system-architect", "E8", ["crash", "pass", "pass"])
    g.run()
    assert e.status == "Architecture Review"  # rested after crash
    g.sweep()  # re-derives the spawn
    assert _ready(g, "E8") == [("ready-to-test", "E8")]
    merged_before = list(g.merges)
    g.human_reject(e, [()])  # feedback -> one fix story
    g.run()
    assert g.merges[: len(merged_before)] == merged_before  # append-only
    assert len(_ready(g, "E8")) == 2
    g.human_accept(e)
    g.run()
    assert e.status == "Epic Done"


def S9(**kw):
    """Concurrent epics: JOINs, notifies and follow-up budgets stay isolated."""
    g = Engine(**kw)
    g.start_epic("EA", [(), ()])
    g.start_epic("EB", [()])
    g.behave("qas", "EA-S1", [("followups", 6)])
    g.run()
    g.sweep()
    assert _ready(g, "EA") == [("ready-to-test", "EA")]
    assert _ready(g, "EB") == [("ready-to-test", "EB")]
    assert ("followup-overflow", "EA") in g.decisions
    assert ("followup-overflow", "EB") not in g.decisions
    assert g.tickets["EB"].followups_created == 0


def S10(**kw):
    """Empty epic: grooming yields zero stories -> Needs PO Decision, no NOTIFY."""
    g = Engine(**kw)
    e = g.start_epic("E10", [])
    g.run()
    assert _ready(g, "E10") == [], "vacuous JOIN fired ready-to-test on empty epic"
    assert e.status == "Needs PO Decision"
    assert ("empty-epic", "E10") in g.decisions


def S11(**kw):
    """AC-blocking follow-up joins the epic; JOIN waits for it (no race)."""
    g = Engine(**kw)
    g.start_epic("E11", [()])
    g.behave("qas", "E11-S1", [("followups-acb", 1)])
    g.run()
    assert _ready(g, "E11") == [], "JOIN raced ahead of unprocessed follow-up"
    g.sweep()  # BSA creates AC-blocking child
    e = g.tickets["E11"]
    assert len(e.children) == 2
    assert g.tickets["E11-FU1"].done
    assert _ready(g, "E11") == [("ready-to-test", "E11")]


def S12(**kw):
    """Rework counter accumulates ACROSS stages: three different reviewers."""
    g = Engine(**kw)
    g.start_epic("E12", [("design", "security")])
    g.behave("system-architect", "E12-S1", [("bounce", "Implement")])  # traversal 1
    g.behave("security-engineer", "E12-S1", [("bounce", "Implement")])  # traversal 2
    g.behave("qas", "E12-S1", [("bounce", "Implement")])  # traversal 3
    g.run()
    s = g.tickets["E12-S1"]
    assert s.status == "Needs PO Decision", s.status
    assert s.rework == REWORK_LIMIT
    assert ("rework-limit", "E12-S1") in g.decisions


def S13(**kw):
    """Max-flag story (design+security+data) runs all 10 stages: 16 spawns to NOTIFY."""
    g = Engine(**kw)
    g.start_epic("E13", [("design", "security", "data")])
    g.run()
    story = [s for s in g.spawns if s[1] == "E13-S1"]
    assert len(story) == 10, f"expected 10 story spawns, got {len(story)}"
    assert len(g.spawns) == 16, len(g.spawns)  # incl. Ticket-Review gate spawn
    roles = [r for (r, _, _) in story]
    for must in ("ui-ux-design", "security-engineer", "data-provisioning-eng", "qas", "qas-design"):
        assert must in roles, must
    assert _ready(g, "E13") == [("ready-to-test", "E13")]


def S14(**kw):
    """Epic-level Blocked (BSA needs domain input): TDM once, resume to Grooming."""
    g = Engine(**kw)
    e = g.start_epic("E14", [()])
    g.behave("bsa", "E14", ["block", "pass"])
    g.run()
    assert e.status == "Blocked"
    g.sweep()
    g.sweep()
    assert len([x for x in g.spawns if x[0] == "tdm"]) == 1
    g.human_unblock(e)
    g.run()
    assert e.pre_blocked == "Grooming"
    assert _ready(g, "E14") == [("ready-to-test", "E14")]


def S15(**kw):
    """Repeated spawn crashes escalate (3 consecutive -> Needs PO Decision)."""
    g = Engine(**kw)
    g.start_epic("E15", [()])
    g.behave("be-developer", "E15-S1", ["crash"] * 5)
    g.run()
    g.sweep()
    g.sweep()
    g.sweep()
    s = g.tickets["E15-S1"]
    assert s.status == "Needs PO Decision", s.status
    assert ("spawn-failure", "E15-S1") in g.decisions
    tries = len([x for x in g.spawns if x[1] == "E15-S1" and x[0] == "be-developer"])
    assert tries == CRASH_LIMIT, tries


def S16(**kw):
    """DoR gate: un-ready tickets bounce to Grooming; no story released; cap -> PO."""
    g = Engine(**kw)
    e = g.start_epic("E16", [(), ()])
    g.behave("qas", "E16", [("bounce", "Grooming")] * 10)  # DoR rework verdicts
    g.run()
    assert e.status == "Needs PO Decision", e.status
    assert e.rework == REWORK_LIMIT
    assert ("rework-limit", "E16") in g.decisions
    released = [s for s in g.spawns if s[1].startswith("E16-S")]
    assert released == [], f"stories released before DoR gate passed: {released}"
    assert _ready(g, "E16") == []


SCENARIOS = [S1, S2, S3, S4, S5, S6, S7, S8, S9, S10, S11, S12, S13, S14, S15, S16]
MUTATIONS = [  # (name, kwargs, scenarios expected to fail without the rule)
    ("JOIN rule disabled", {"join": False}, [S1]),
    ("SKIP-FORWARD disabled", {"skip": False}, [S3, S4]),
    ("rework counter disabled", {"rework_guard": False}, [S2, S12]),
    ("empty-epic guard disabled", {"empty_guard": False}, [S10]),
    ("JOIN quiescence disabled", {"quiescence": False}, [S11]),
    ("crash escalation disabled", {"crash_guard": False}, [S15]),
    ("DoR gate disabled", {"dor_gate": False}, [S16, S1]),
]

if __name__ == "__main__":
    failed = 0
    print("— scenario suite (all guards active) —")
    for s in SCENARIOS:
        try:
            s()
            print(f"  PASS  {s.__name__}: {s.__doc__.strip()}")
        except (AssertionError, SafetyCapExceeded) as ex:
            failed += 1
            print(f"  FAIL  {s.__name__}: {ex}")
    print("— mutation checks (each disabled guard must break its scenario) —")
    for name, kw, targets in MUTATIONS:
        for s in targets:
            try:
                s(**kw)
                failed += 1
                print(f"  NOT-CAUGHT  {name} -> {s.__name__} still passed")
            except (AssertionError, SafetyCapExceeded):
                print(f"  CAUGHT  {name} -> {s.__name__} fails as expected")
    print("RESULT:", "FAIL" if failed else "OK — workflow v2 behaves as specified")
    raise SystemExit(1 if failed else 0)
