# Design Spec — Workflow v3.1: Flexible Intake (three-way classification, Path-A + Path-B heads)

**Ticket**: ABS-103 (Story 1 of epic ABS-102) · **Status**: draft (for Architecture Review) · **Date**: 2026-07-06
**Author role**: BSA / Backend Developer (spec-authoring seat) · **Epic**: ABS-102 — "Workflow v3.1 — flexible intake"
**Extends**: [ABS-69-workflow-v3-full-agent-team-spec.md](ABS-69-workflow-v3-full-agent-team-spec.md) §3.5 (merge/integration policy), §3.10 (Ticket-Review DoR gate)
**Depends on**: [docs/sop/DEFINITION_OF_READY.md](../sop/DEFINITION_OF_READY.md) · **Diagram (Story 7)**: [assets/workflow-v2.drawio](assets/workflow-v2.drawio)

> **Scope of this document.** This is a *design-only* spec. It resolves the two open
> `#PATH_DECISION`s carried in the ABS-102 grooming draft and pins the contracts the sibling
> implementation stories (ABS-104..110) must not re-decide. **No runner code, no adapter code, no
> diagram edit, and no SOP-body edit ship under ABS-103** (ADR-A-0010 minimal-change default — that
> work belongs to Stories 2–8). Where this spec and the already-landed
> [`docs/sop/ORCHESTRATOR_SOP.md`](../sop/ORCHESTRATOR_SOP.md) "Intake classification" subsection
> describe the same behavior, they are intentionally identical.

---

## 1. Purpose

Workflow v3 (ABS-69) assumes **every top-level ticket is an empty epic to decompose**: a top-level
ticket enters at `PO Triage → Grooming → Enrichment`, which generate the child stories, then the
`Ticket Review` Definition-of-Ready (DoR) gate (§3.10) batch-reviews them before release. That single
assumption is wrong for two common real inputs:

1. A **standalone story or bug** with no parent epic — there is nothing to decompose; forcing it
   through epic grooming manufactures a one-child epic.
2. A **pre-populated epic** authored with its child tickets already attached — Grooming would
   re-decompose (or duplicate) work a human already did.

v3.1 makes intake **flexible**: a bash-only, no-LLM classifier (ADR-A-0009) reads each top-level
ticket's **parent-epic link** and **child count** and routes one of three ways. The change is
**purely additive** — the empty-epic route is the unchanged v3.0 flow, and the two new routes add
**entry heads that feed the existing pipeline**, not new stages.

This spec delivers, per the epic goal: the three-way intake-classification decision table (§4); the
Path-A solo-pipeline shape plus its merge seam with both `#PATH_DECISION`s resolved (§3, §5); the
Path-B DoR entry gate plus auto-fix rework loop (§6); the EXPORT_CRITICAL merge guardrail restated
verbatim for Path-A (§7); a coverage map from every ABS-102 epic DoD item to its delivering story
(§8); the spec-section → E2E-scenario map (§8.1); and the residual `#PLAN_UNCERTAINTY` items each with
a stated resolution path (§9).

---

## 2. Terms

- **Top-level ticket** — a ticket the runner pulls from `Backlog` (carries the orchestrator-ready
  opt-in label, ABS-101). Intake classification runs on top-level tickets only.
- **Intake head** — a new *entry route* (Path-A or Path-B) that lands a top-level ticket onto an
  existing pipeline stage. Heads add entry routes, **not** new stages.
- **Path-A** — the parentless-ticket solo story pipeline (§5).
- **Path-B** — the pre-populated-epic DoR entry gate + auto-fix rework loop (§6).
- **Conditional stage / SKIP-FORWARD** — a `Design` / `Security Review` / `Test Prep` / `Design Test`
  stage gated on the `design` / `security` / `data` flag; when the flag is unset the runner
  re-transitions to the next status with an audit comment and **no spawn** (ABS-69 §3.3).

---

## 3. `#PATH_DECISION` (a) — Path-A triage seat  *(RESOLVED)*

**Question (from ABS-102 grooming).** When a parentless ticket enters Path-A, what seat — if any —
sits at the head of the solo pipeline to validate the ticket before implementation?

**Resolution.** Path-A begins with the **existing `po-agent` `PO Triage` seat, run in single-ticket
mode** — the *same* seat and charter that already heads the v3.0 epic pipeline, invoked over one
ticket instead of an epic. **Exactly one seat; no new role.**

**Rationale.**

- **Reuse over invention (ADB standing rule + ADR-A-0002).** Never add a new `.claude/agents/` role
  when an existing role already owns the function. Intake validation of a top-level ticket — "is this
  in scope, does it carry testable AC, is it ready to build?" — is precisely the product-authority
  duty `po-agent`'s `PO Triage` seat already performs. A parentless ticket needs that judgement no
  less than an epic does.
- **The DoR batch gate is degenerate for one ticket.** The QAS `Ticket Review` gate (§3.10) earns its
  keep on the *cross-story* checks — overlap, acyclic dependencies, and the mandatory coverage mapping
  over a **batch** of children. A single parentless ticket has no batch and no coverage map, so a full
  QAS batch gate is unwarranted. The `PO Triage` seat instead runs a **one-ticket readiness
  self-check** (testable AC present; scope fits one spawn; flags consistent with content) — the
  per-ticket half of the DoR checklist, applied inline. Anything it cannot decide escalates to
  `Needs PO Decision`, exactly as the epic triage seat does.
- **Cost.** +1 spawn at the head of Path-A. Bounded and known.

**Rejected alternative (named).** A **new lightweight "bug-triage" seat** dedicated to Path-A.
Rejected because it duplicates `po-agent`'s triage duty for only marginal per-spawn token savings,
violates one-seat-one-duty and the reuse rule, and adds a charter to maintain and keep in sync with
the epic triage seat. *(Also rejected: **no triage seat at all** — feeding a parentless ticket
straight to `Design`/`Implement`. Rejected because nothing would then verify AC/readiness before code
is written — the exact shift-left failure the DoR gate (§3.10) exists to prevent.)*

---

## 4. Intake-classification decision table

The classifier is **bash-only, no LLM** (ADR-A-0009). It reads two adapter signals — the ticket's
**parent-epic link** (`parent <id>`) and its **child count** (`child-count <id>`) — plus the ticket
**type**, and writes a `kind: gate-results` audit comment naming the chosen path before routing. The
type discriminator is what keeps rows 1 and 3 unambiguous (both have no parent and zero children).

| # | Ticket type | Parent-epic link | Child count | Classification | Route |
|---|-------------|------------------|-------------|----------------|-------|
| 1 | epic | none | 0 | **empty-epic** | **v3.0 decomposition (unchanged)** — `PO Triage → Grooming → Enrichment → Ticket Review → …` |
| 2 | epic | none | ≥ 1 | **epic-with-children** | **Path-B** (§6) — DoR entry gate over the pre-existing children (skips Grooming decomposition) |
| 3 | story / bug | none | 0 | **parentless-ticket** | **Path-A** (§5) — solo story pipeline on its own branch, PR-to-main tail |
| 4 | any | **present** | — | **child-of-epic** | **classifier no-op** — runs as a normal child inside its parent epic's existing v3.0 pipeline (no intake head) |

**Unambiguity.** Every `(type, parent-link, child-count)` tuple resolves to exactly one row: row 4
captures anything with a parent (a child story), so rows 1–3 are all parentless; among the parentless,
`child-count ≥ 1` selects row 2, and `type` (epic vs story/bug) discriminates rows 1 and 3. No tuple
matches two rows; no reachable tuple matches none. (A story/bug carrying children is not an expected
input; if seen it falls to row 2's `child-count ≥ 1` branch and is handled as a pre-populated parent —
safe, and flagged to `Needs PO Decision` by the Path-B DoR gate if the children are inconsistent.)

Both new heads (rows 2 and 3) **feed the existing pipeline** — they add entry routes, not stages.

---

## 5. Path-A — parentless-ticket solo pipeline

### 5.1 `#PATH_DECISION` (b) — bug pipeline shape  *(RESOLVED)*

**Question (from ABS-102 grooming).** What is the exact ordered status sequence for a parentless
ticket — which v3.0 **story-pipeline** stages are in, which epic-pipeline stages are out, and how do
the conditional stages behave?

**Resolution — full nominal sequence (all `design`/`security`/`data` flags set):**

```
PO Triage (§3)  →  Design  →  Implement  →  Code Review  →  Security Review
              →  Test Prep  →  In Test  →  Design Test  →  Story Acceptance
              →  Merging (PR-to-main variant, §7)  →  Docs  →  Done
```

**Stages IN** — the full v3.0 **story pipeline** (ABS-69 §1.2), reused verbatim: `Design`,
`Implement`, `Code Review`, `Security Review`, `Test Prep`, `In Test`, `Design Test`,
`Story Acceptance`, `Merging`, `Docs`. **Plus** the single `PO Triage` head (the only epic-pipeline
stage that runs, in single-ticket mode — §3).

**Stages OUT** — the epic-pipeline decomposition/integration stages: `Grooming`, `Enrichment`,
`Ticket Review`, `Architecture Review`, `Epic Integration`. A parentless ticket has no children to
groom, no batch to DoR-review, no sibling set to release, and no epic branch to integrate — so none of
these run.

**The one changed stage:** `Merging` runs in its **PR-to-main variant** — the ticket's own branch →
RTE opens a PR to `main` → **human merges**. There is **no epic integration branch and no
auto-merge** (see the EXPORT_CRITICAL guardrail, §7). Every other IN stage behaves exactly as it does
for a story inside an epic.

### 5.2 Conditional-flag / SKIP-FORWARD behavior

`Design`, `Security Review`, `Test Prep`, and `Design Test` are **conditional** on the
`design` / `security` / `data` flags (ABS-69 §3.3). When a flag is unset the runner **SKIP-FORWARDs** —
re-transitions to the next status with an audit comment and **no spawn** — identical to the
story-in-epic behavior. `In Test`, `Code Review`, `Story Acceptance`, `Merging`, and `Docs` are
unconditional and always run.

**SKIP-FORWARD-collapsed sequence for a plain, unflagged bug** (`design`/`security`/`data` all unset):

```
PO Triage  →  Implement  →  Code Review  →  In Test  →  Story Acceptance
          →  Merging (PR-to-main)  →  Docs  →  Done
```

(`Design`, `Security Review`, `Test Prep`, `Design Test` each SKIP-FORWARD with an audit comment and
no spawn.) This is the minimum-cost Path-A traversal; a `security`-flagged bug additionally spawns
`Security Review`, a `data`-flagged one `Test Prep`, and a `design`-flagged one `Design` + `Design
Test` — no other routing logic lives in any seat prompt (ADR-A-0009).

**Delivering stories.** The pipeline shape lands under **ABS-105** (Story 3); the PR-to-main tail
under **ABS-106** (Story 4).

---

## 6. Path-B — pre-populated-epic DoR entry gate + auto-fix rework loop

A **pre-populated epic** (row 2: epic, no parent, ≥ 1 child) **skips Grooming decomposition** and
routes **straight into the QAS `Ticket Review` Definition-of-Ready gate as its *entry* gate** over the
pre-existing children (plus epic-prerequisite checks). The DoR **checklist, mandatory
coverage-mapping rule, blind-spot catalog, and three verdicts are reused verbatim** from
[`docs/sop/DEFINITION_OF_READY.md`](../sop/DEFINITION_OF_READY.md) ("Path-B entry-gate reuse") and
ABS-69 §3.10 — **only the point at which the gate runs moves earlier** in the pipeline.

**Verdict routing (unchanged from §3.10):**

- **`ready`** (all children pass) → **`Architecture Review`** with **no story generation**. The
  architect reviews and releases only complete tickets.
- **`rework`** → the **auto-fix rework loop**: mechanical, in-scope ticket defects (a missing/spurious
  `design`/`security`/`data` flag, a missing pattern/spec reference, an implausible `role:` hint) are
  applied mechanically; **only substance gaps** the runner cannot mechanically fix — an untestable AC,
  an unmapped epic goal, an oversized ticket needing a split — **escalate to `Needs PO Decision`**.
  The loop is **capped at 3 bounces by the existing per-ticket rework counter** (ABS-69 §3.2) applied
  to the **epic ticket**; the 3rd bounce escalates to `Needs PO Decision`. **No new guard mechanics.**
- **`open question`** → `Needs PO Decision` (the po-agent that triaged the epic is the product
  authority), exactly as §3.10.

**No story is ever released before this gate passes** — the shift-left invariant of §3.10 holds for
Path-B unchanged.

**Delivering stories.** The DoR entry gate lands under **ABS-107** (Story 5); the auto-fix rework loop
under **ABS-108** (Story 6). The mechanical-fix allowlist vs. escalate boundary is pinned by ABS-108
(see §9-4).

### 6.1 `#PATH_DECISION` (c) — how a pre-filled epic REACHES the gate  *(RESOLVED, ABS-271)*

ABS-107 delivered the gate; ABS-104 delivered the classification. Neither delivered the **routing
between them**, so the gate above was mechanically unreachable: `route_intake()` classified an epic as
`epic-with-children`, posted an audit comment claiming it had "routed to 'Path-B entry gate'", and then
did nothing. There was no status edge to `Ticket Review` from anywhere a pre-filled epic passes.

Verified on the live epic **ABS-278** (2026-07-13T22:03:05Z): it went `Backlog -> Stories In Flight` in
one hop, past the gate, and released 14 children to `Ready for Development` — violating this section's
shift-left invariant ("No story is ever released before this gate passes"). It needs no lenient seat to
happen: a pre-filled epic gets no forward move out of `Backlog`, so the runner's own ABS-214 JOIN-rest
park (`epic_join_rest_complete`) carries it into `Stories In Flight` automatically. `STATION-GUARD`
could not see the hop because `Backlog` is `chain_index` 0 and index-0 sources are exempt.

**Chosen — enforce the gate at the station the epic actually passes, by reusing `STATION-GUARD`.**
A pre-filled epic enters the epic chain with decomposition *satisfied by construction* (its children
exist), so its guard-side source index is **Enrichment's** — the station immediately before the gate
(`prefilled_epic_entry_index`, scripts/orchestrator.sh). Any forward hop that lands beyond
`Ticket Review` therefore reads as a skip of a mandatory station and the guard redirects it to
`Ticket Review`, where the existing qas DoR batch review runs. This honours §6's **"No new guard
mechanics"** literally: no second gate, no new seat, no LLM. Exactly **one** `statuses.yaml` edge makes
it legal — `Stories In Flight -> Ticket Review`, the guard's repair redirect, which no seat takes (the
adapter enforces the next-table, so the redirect would otherwise die as an illegal transition). The
guard is armed only while the epic has never visited the gate (`epic_passed_dor_gate`), which keeps
ABS-214's JOIN-rest edge intact and makes the redirect idempotent.

**The discriminator is `Grooming`, not child-count.** Both epic classes have children — a *decomposed*
epic has them the moment the bsa seat creates them in `Grooming`. So "is an epic AND has children AND
has not passed the gate" matches **both** classes, and clamping on it silently forgives mandatory
`Enrichment` for the decomposed class: the guard redirects a `Grooming -> Architecture Review` skip to
`Ticket Review` instead of to `Enrichment`, weakening ABS-136/ABS-247 exactly where they must hold.
`Grooming` is the station that *creates* children, so the pre-filled epic — which has nothing to
decompose — is precisely the epic that never visits it (`epic_visited_grooming`). This is load-bearing,
not defensive: without it the fix regresses the guard it reuses.

**Rejected — "just add the missing edge".** Adding `PO Triage -> Ticket Review` and stopping there is
**inert**: the pre-filled epic never visits `PO Triage` (it is parked from `Backlog` by JOIN-rest), so
the edge would be legal and untraversed while the gate stayed unreachable and the audit comment kept
claiming otherwise. It is not merely insufficient — it is **dead**, and shipping it would re-commit in
the status model the very sin AC2 removes from the audit comment: asserting a route the runner never
takes. The edge is therefore **not** part of this change.

**Residual gap (NOT closed here, out of this story's scope).** The guard gates the **epic**. A po-agent
seat that releases the children *in the same breath* as parking the epic still front-runs the gate at the
**child** level — the epic is pulled back to `Ticket Review`, but those children already sit in
`Ready for Development`. Closing that requires a child-release gate ("no child leaves `Backlog` while its
parent epic still owes its DoR gate"), which is a new mechanism on the story chain and a redesign of the
epic/story seam that ABS-271 explicitly excludes. Raised for POPM/architect disposition.

---

## 7. EXPORT_CRITICAL — Path-A merge guardrail

Path-A's tail is a merge to `main`. It therefore inherits the ABS-69 §3.5 merge/integration boundary
**unchanged and un-extended**. Stated verbatim:

> `#EXPORT_CRITICAL` — **Path-A merge policy.** A parentless ticket merges on its **own branch**; the
> **RTE opens a PR to `main`**; a **human merges** it. There is **no epic integration branch** and
> **no auto-merge** on Path-A. **ADR-A-0014 is not extended** — auto-merge remains **epic-branch-only**
> (a story auto-merging onto its per-epic integration branch on green CI), and **merges to `main`
> remain human-only** (ADR-A-0004 / ADR-A-0005, both respected). Path-A introduces **no new path to
> `main`** and **moves no `main` boundary**; it reuses the single sanctioned human merge at `main`
> that already governs every epic PR.

Rationale for holding the line: auto-merge was accepted (ADR-A-0014) as a *contained* trust decision
**within** the ADR-A-0004/0005 `main` boundaries — a human still tests and merges every epic PR. A
solo Path-A ticket has **no epic branch and no sibling integration** to gate with CI, so the auto-merge
rationale does not apply; extending it to `main` would move a human-only boundary, which this spec
explicitly does **not** do.

---

## 8. Coverage map — every ABS-102 epic DoD item → delivering story

Stories 1–8 of epic ABS-102: **1** ABS-103 (this spec), **2** ABS-104 (classifier), **3** ABS-105
(Path-A pipeline), **4** ABS-106 (Path-A PR-to-main tail), **5** ABS-107 (Path-B entry gate),
**6** ABS-108 (Path-B rework loop), **7** ABS-109 (diagram + SOP/changelog docs), **8** ABS-110 (E2E).

| # | Epic DoD item (from ABS-102) | Delivering story |
|---|------------------------------|------------------|
| D1 | Bash-only, no-LLM intake classifier reads parent-epic link + child count and routes three ways; writes an audit comment naming the path | **Story 2** (ABS-104) |
| D2 | Empty epic → the **unchanged** v3.0 decomposition flow (backward-compatible; regression-guarded) | **Story 2** (classifier row 1) + **Story 8** (S-B3 regression) |
| D3 | Parentless ticket → **Path-A** solo story pipeline on its **own branch** (pipeline shape) | **Story 3** (ABS-105) |
| D4 | Path-A ends at an **RTE PR-to-main with NO auto-merge** (auto-merge stays epic-only per ADR-A-0014; `main` merges human-only) | **Story 4** (ABS-106) |
| D5 | Epic with pre-existing children → **Path-B**: skip Grooming decomposition, run DoR as the **entry** gate; conformant → `Architecture Review` with **no story generation** | **Story 5** (ABS-107) |
| D6 | Path-B **auto-fix rework loop**: mechanical fixes applied; only substance gaps → `Needs PO Decision`; capped at 3 bounces by the existing rework counter | **Story 6** (ABS-108) |
| D7 | Two new intake heads **feed the existing pipeline** (entry routes, not new stages); DoR checklist / coverage-mapping / blind-spot / verdicts **reused verbatim** | **Story 5 + Story 6** (behavior) + **Story 7** (docs) |
| D8 | **Diagram + SOP + changelog** documentation of the two heads | **Story 7** (ABS-109) |
| D9 | **E2E coverage** of the new routes (S-A1 / S-B1 / S-B2 / S-B3) | **Story 8** (ABS-110) |
| D10 | Both open **`#PATH_DECISION`s resolved** with rationale + a named rejected alternative (Path-A triage seat; bug pipeline shape) | **Story 1** (ABS-103, §3 + §5.1) |
| D11 | **Accepted spec** extending ABS-69 with the decision table + both path shapes + coverage map | **Story 1** (ABS-103, this doc) |

Every epic DoD item maps to at least one delivering story; every story 1–8 delivers at least one item.

### 8.1 Spec-section → E2E-scenario map

| Scenario | What it proves | Spec section(s) | Story |
|----------|----------------|-----------------|-------|
| **S-A1** | Parentless ticket runs Path-A end-to-end: own branch, conditional-stage SKIP-FORWARDs, RTE **PR-to-main**, **no auto-merge**, human merge | §5.1, §5.2, §7 | 8 (ABS-110) |
| **S-B1** | Pre-populated epic, **conformant** children: DoR entry gate → `ready` → `Architecture Review`, **no story generation** | §6 | 8 (ABS-110) |
| **S-B2** | Pre-populated epic, **non-conformant**: auto-fix rework loop applies mechanical fixes; a **substance gap → `Needs PO Decision`**; capped at **3 bounces** | §6 | 8 (ABS-110) |
| **S-B3** | **Empty epic → unchanged v3.0 flow** (additivity / regression guard — v3.1 does not touch the default) | §4 (row 1) | 8 (ABS-110) |

---

## 9. Residual `#PLAN_UNCERTAINTY` — each with a resolution path

None of the following block acceptance; each names how it resolves.

1. **Should a parentless bug ever *skip* `PO Triage`** when it already carries testable AC (a
   fast-path head)? **Resolution path:** default is **always run `PO Triage`** (safe, §3); ABS-104
   (Story 2) measures the head's spawn cost on the first live Path-A run and, if it is pure overhead,
   a follow-up ticket adds an opt-out — decided by data, not now.
2. **Exact adapter primitive names/semantics for `parent` and `child-count`** across providers (mock
   vs. Jira). **Resolution path:** pinned by ABS-104 (Story 2) against the adapter contract
   [`profiles/neutral/adapters/task-tracking.md`](../../profiles/neutral/adapters/task-tracking.md); the
   mock adapter is the reference; conformance asserted in `tests/test-intake-classification.sh`.
3. **CI / branch-protection for the Path-A PR-to-main tail** — does a solo ticket's PR need the same
   required checks as an epic PR? **Resolution path:** ABS-106 (Story 4) **reuses the existing `main`
   branch protection** (human merge, ADR-A-0004/0005) with **no new protection rule**; confirmed at
   Architecture Review.
4. **The auto-fix loop's mechanical-fix allowlist vs. escalate boundary** — which ticket defects may
   be edited mechanically, which must escalate. **Resolution path:** ABS-108 (Story 6) defines the
   explicit allowlist (flag/reference/role-hint fixes are mechanical; untestable AC, unmapped goal,
   oversized scope escalate to `Needs PO Decision`); boundary reviewed at Architecture Review.

---

## 10. Applicable ADRs (respected, not amended)

- **ADR-A-0002** — fresh single-ticket spawn per stage (Path-A/Path-B seats are ordinary fresh spawns).
- **ADR-A-0004 / ADR-A-0005** — `main` merges are human-only (Path-A PR-to-main, §7).
- **ADR-A-0009** — the classifier and SKIP-FORWARD are bash-only, no LLM (§4, §5.2).
- **ADR-A-0010** — minimal-change/additive: the empty-epic route is untouched; heads add entry routes only.
- **ADR-A-0014** — epic-branch-only auto-merge; **not extended** by Path-A (§7).

## 11. References

- [docs/specs/ABS-69-workflow-v3-full-agent-team-spec.md](ABS-69-workflow-v3-full-agent-team-spec.md) §3.5 (merge/integration), §3.10 (Ticket-Review DoR gate), §1.2 (story pipeline stages), §3.2 (rework counter), §3.3 (SKIP-FORWARD)
- [docs/sop/DEFINITION_OF_READY.md](../sop/DEFINITION_OF_READY.md) — DoR checklist + "Path-B entry-gate reuse"
- [docs/sop/ORCHESTRATOR_SOP.md](../sop/ORCHESTRATOR_SOP.md) — "Intake classification — three-way route (v3.1, ABS-102)"
- [docs/specs/assets/workflow-v2.drawio](assets/workflow-v2.drawio) — the two intake-head boxes (Story 7, ABS-109)
- `tests/test-intake-classification.sh` — classifier conformance (Story 2, ABS-104)
