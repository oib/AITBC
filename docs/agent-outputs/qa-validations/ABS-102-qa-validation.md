# QAS Ticket Review (Definition-of-Ready) — ABS-102

**Epic**: ABS-102 — Workflow v3.1: flexible intake (parentless tickets + pre-populated epic validation)
**Gate**: QAS Ticket-Review DoR gate (v3 epic pipeline, spec §3.10 / docs/sop/DEFINITION_OF_READY.md)
**From → To**: Enrichment → Ticket Review (batch review of all children before any story release)
**Date**: 2026-07-06
**Reviewer**: QAS (fresh spawn, independent of BSA/issue-enrichment authors)
**Iteration**: First Ticket-Review pass — no prior `Ticket Review → Grooming` bounce comments on the epic
(the stray `gate-results` entries at 14:52–15:02 are inert issue-enrichment sandbox probes, not DoR bounces).

## Children under review (8)

| ID | Title | role | flags | depends_on |
|----|-------|------|-------|------------|
| ABS-103 | Author v3.1 flexible-intake spec + resolve two PATH_DECISIONs | be-developer | — | — |
| ABS-104 | Three-way intake classification + adapter parent-link/child-count reads | be-developer | — | ABS-103 |
| ABS-105 | Path-A parentless-ticket solo pipeline | be-developer | — | ABS-104 |
| ABS-106 | Path-A tail: own branch + RTE PR-to-main (no auto-merge) EXPORT_CRITICAL | be-developer | security | ABS-105 |
| ABS-107 | Path-B: DoR gate as entry gate + epic-prerequisite checks | be-developer | — | ABS-104 |
| ABS-108 | Path-B auto-fix rework loop (substance-only escalation, 3-bounce cap) | be-developer | — | ABS-107 |
| ABS-109 | Diagram + SOP + changelog updates | be-developer | — | ABS-104..108 |
| ABS-110 | E2E dry-runs S-A1..S-B3 + mutation check | be-developer | data | ABS-103..108 |

## DoR checklist per child

Legend: T=all ACs testable/measurable · F=flags consistent · R=role plausible · S=single-spawn scope · P=pattern/spec refs present · U=no unresolved #PLAN_UNCERTAINTY without a path.

| ID | T | F | R | S | P | U | Verdict |
|----|---|---|---|---|---|---|---------|
| ABS-103 | ✅ (file exists, exactly-ONE-seat, exact status sequence, decision table, verbatim merge policy, coverage map) | ✅ none (spec doc) | ✅ | ✅ one spec doc | ✅ ABS-69 §3.5/§3.10, DoR SOP, spec_template | ✅ both PATH_DECISIONs resolved here | PASS |
| ABS-104 | ✅ (classify returns 1-of-3, per-input mapping, adapter reads, dry-run values, bash-only/no-LLM, audit comment) | ✅ none | ✅ | ✅ classify fn + adapter reads | ✅ ABS-69 §3.3, ORCHESTRATOR_SOP, adapters | ✅ | PASS |
| ABS-105 | ✅ (exact solo seats + SKIP-FORWARD w/ audit + zero spawns, no epic status in transition log, JOIN never evals, security variant) | ✅ none | ✅ | ✅ pipeline wiring | ✅ ABS-69 §1.2/§3.3, Story 1 | ✅ | PASS |
| ABS-106 | ✅ (branch off origin/main, no epic/ ref, auto-merge NOT invoked, A-0014 path not reached, human-merge unchanged, idempotent no-dup-PR) | ✅ security (merge-to-main authz boundary) | ✅ | ✅ RTE merge seam | ✅ ABS-69 §3.5, A-0004/0005/0014, CONTRIBUTING | ✅ | PASS |
| ABS-107 | ✅ (no Grooming decomposition spawn, gate runs unchanged, epic-prereq check, conformant→Arch Review no story, v3.0 tail unchanged) | ✅ none | ✅ | ✅ gate routing + prereq | ✅ ABS-69 §3.10, DoR SOP | ✅ | PASS |
| ABS-108 | ✅ (rework bounce to Grooming, enumerated auto-fix set asserted, substance→Needs PO Decision, §3.2 counter, 3-bounce cap, re-run→Arch Review) | ✅ none | ✅ | ✅ rework loop wiring | ✅ ABS-69 §3.2/§3.10, PO_AGENT_SOP, A-0004 | ✅ | PASS |
| ABS-109 | ✅ (drawio 2 heads opens w/o error, ORCH_SOP section, AGENT_WORKFLOW note, CHANGELOG entry, DoR reuse note, md-lint) | ✅ none (doc-only; .drawio is documentation not UI-under-test → no design flag, correct) | ✅ | ✅ doc edits | ✅ all target files listed | ✅ | PASS |
| ABS-110 | ✅ (S-A1/S-B1/S-B2/S-B3 concrete assertions, mutation check, deterministic bash dry-run, wired to exit gate) | ✅ data (seeded mock-adapter fixtures) | ✅ | ✅ four scenarios in one test file | ✅ tests/e2e-workflow-v3.sh, ABS-69 §5 | ✅ | PASS |

## Cross-story checks

- **Overlap/duplication**: none — spec / classify / solo-body / tail / gate / rework / docs / tests are distinct, non-overlapping.
- **Dependencies explicit & acyclic**: 103→∅, 104→103, 105→104, 106→105, 107→104, 108→107, 109→{104..108}, 110→{103..108}. All forward edges; no cycle. ✅

## Coverage map (epic goal / DoD → covering story AC)

| Epic goal / DoD item | Covering story AC |
|----------------------|-------------------|
| Spec authored + two #PATH_DECISIONs resolved | ABS-103 (all ACs) |
| Three-way intake classification | ABS-104 AC1–5 |
| Adapter reads parent-epic link + child count | ABS-104 AC6 |
| Path-A parentless-ticket pipeline + SKIP-FORWARD reuse | ABS-105 AC1–5 |
| Path-A PR-to-main seam / #EXPORT_CRITICAL merge policy | ABS-106 AC1–6 |
| DoR gate repositioned as Path-B entry gate | ABS-107 AC1–5 |
| Auto-fix rework loop, substance-only escalation, 3-bounce cap | ABS-108 AC1–5 |
| Diagram intake heads + SOP + HARNESS_CHANGELOG | ABS-109 AC1–6 |
| E2E S-A1 (parentless, zero epic machinery, no auto-merge) | ABS-110 AC1 (+ ABS-105/106 behavior) |
| E2E S-B1 (conformant epic → Arch Review, no story gen) | ABS-110 AC2 (+ ABS-107) |
| E2E S-B2 (auto-fix; substance→Needs PO Decision; 3 bounces) | ABS-110 AC3 (+ ABS-108) |
| E2E S-B3 (empty epic still v3.0 generate-stories, no regression) | ABS-110 AC4 (+ ABS-104 classification) |
| Intake mutation binding | ABS-110 AC5 |

**No epic goal is left unmapped.** Full coverage. ✅

## Blind-spot catalog (child set as a whole)

- **Error/edge cases** — ok: Bug/Story WITH parent-link mis-map guarded (ABS-104 AC5); security-flagged parentless variant (ABS-105 AC4); substance gap + 3-bounce (ABS-108); S-B3 no-regression (ABS-110).
- **Authz / merge boundary** — ok: merge-to-main authorization boundary is the security-flagged surface (ABS-106); auto-merge explicitly NOT extended to parentless tickets (A-0014 guard asserted).
- **Migrations for existing data** — n/a (correct): orchestrator-bash + docs + tests only; no schema/data-model change requiring backfill.
- **Idempotency** — ok: no-duplicate-PR on re-run (ABS-106 AC6); auto-fix loop bounded by §3.2 counter (ABS-108).
- **Observability** — ok: audit comment naming chosen path (ABS-104 AC7); SKIP-FORWARD audit comments (ABS-105); transition-log assertions throughout.
- **Rollback** — ok: additive intake heads; existing paths unchanged and regression-guarded (S-B3); parentless path ends at human PR-to-main, reverts human-only per spec §3.5.

**No material blind-spot gap.**

## Non-blocking observations (not defects)

1. ABS-104 AC6 references "a seeded parentless ticket and a seeded epic-with-children" for a classification dry-run but carries no `data` flag. This is consistent, not a defect: the heavyweight fixture set (parentless / conformant / non-conformant-with-substance-gap / empty) is correctly centralized in ABS-110 under the `data` flag; ABS-104's two-ticket dry-run seed is trivially inline and does not require the data-provisioning-eng seat.
2. ABS-105 directly consumes Story 1's (ABS-103) PATH_DECISION resolutions but lists `depends_on: [ABS-104]` only. Acceptable: ABS-104 depends_on ABS-103, so ABS-103 lands first transitively; the dependency graph stays acyclic and correctly ordered.

## Verdict: **READY**

Every child passes DoR, cross-story checks hold, coverage mapping is complete (no unmapped epic goal), and no blind-spot category is silently ignored. The two open #PATH_DECISIONs (Path-A triage seat; bug pipeline shape) have an explicit resolution path assigned to ABS-103. Guardrails carried verbatim from PO Triage (Path-A no-auto-merge/#EXPORT_CRITICAL on ABS-106; Path-B auto-fix-vs-substance boundary on ABS-108).

**Exit transition**: Ticket Review → Architecture Review (actor qas).
