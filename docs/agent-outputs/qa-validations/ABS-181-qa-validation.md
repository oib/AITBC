# Ticket Review (DoR Gate) — ABS-181

**Epic**: Distributed ticket claim for multi-orchestrator coordination
**QAS seat**: Ticket Review (Definition-of-Ready batch gate, v3 epic pipeline)
**Date**: 2026-07-10
**Children reviewed**: ABS-182, ABS-183, ABS-184, ABS-185, ABS-186, ABS-187, ABS-188, ABS-189

---

## Verdict: REWORK

5 of 8 children fail the DoR checklist. 3 epic ACs are unmapped to any child story AC. 1 epic AC is partially uncovered.

---

## Epic Prerequisites (Path-B check)

| Prerequisite | Result |
|---|---|
| Goal present | PASS — "Let two or more orchestrators cooperate without ever double-spawning the same ticket" |
| Scope present | PASS — explicit in-scope/out-of-scope in epic ticket and specs/distributed-ticket-claim-spec.md |
| ACs / DoD present | PASS — 8 ACs in epic ticket |
| ADR context present | PASS — ADR-A-0007, ADR-A-0002, ADR-A-0003, ADR-A-0009 named |

---

## DoR Per Child

### ABS-182 — Adapter: add 'claim' comment kind (mock + jira + contract)

**DoR checklist**:
- Measurable ACs: **FAIL** — the ticket title and scope include "comment-pagination verification/fix in cmd_get." The enrichment gate-results comment marks it LOAD-BEARING: "truncated comment list makes both machines adjudicate themselves winner." No AC verifies pagination. Epic AC-7 ("cmd_get provably returns the full comment list") has no child story AC.
- Flags consistent with content: PASS (none needed)
- Role hint plausible: PASS (`role: be-developer`)
- Single-spawn scope: PASS
- Pattern/spec references: PASS (`specs/distributed-ticket-claim-spec.md §5`)
- No unresolved `#PLAN_UNCERTAINTY`: PASS

**Result: FAIL** — Defect 1 (pagination AC missing)

---

### ABS-183 — Orchestrator: mint + persist ORCH_INSTANCE_ID

**DoR checklist**:
- Measurable ACs: **FAIL** — 4 ACs cover mint, unique-ids, env override, and per-run stability. None cover the restart-reuse invariant. Epic AC-5 reads: "A restarted runner reuses its persisted instance id and recognizes its own claims (no self-yield)." ABS-183 AC-4 says "id stable for the lifetime of a run" — this tests intra-run stability, not cross-restart reuse. The enrichment DoR note flags this explicitly.
- Flags consistent: PASS
- Role hint: PASS (`be-developer`)
- Single-spawn scope: PASS
- Spec references: PASS (`spec §4.1`)
- No open uncertainty: PASS

**Result: FAIL** — Defect 2 (restart-reuse AC missing, epic AC-5 unmapped)

---

### ABS-184 — Orchestrator: acquire_remote_claim (settle/jitter/TTL/refresh)

**DoR checklist**:
- Measurable ACs: **FAIL** — two gaps:

  **Gap A (epic AC-6)**: No AC specifies that TTL staleness reads the server-assigned `### <at>` header, not the body `at:` field. ABS-184 AC-2 says "Adjudication uses dump order, not the `at:` timestamp" — this covers winner selection, not staleness computation. An implementation could use body `at:` for TTL math and pass all current ACs, yet be incorrect under cross-machine clock skew (the exact hazard spec §4.3 guards against).

  **Gap B (epic AC-2)**: No AC tests the mid-spawn heartbeat scenario: "a spawn running longer than ORCH_CLAIM_TTL keeps its claim fresh; a peer's acquire_remote_claim returns false for the full spawn duration." ABS-184 AC-5 ("Refresh is throttled") tests that over-staking is suppressed, not that the peer loses throughout the spawn. The spec test strategy (§9, heartbeat case) is in scope but has no corresponding AC in the ticket.

- Flags consistent: PASS
- Role hint: PASS (`be-developer`)
- Single-spawn scope: PASS (`model:opus` per enrichment — appropriate for core distributed algorithm)
- Spec references: PASS (`spec §4.3, §4.4, §6`)
- `#PLAN_UNCERTAINTY`: PASS — two timing uncertainties have resolution paths named (ABS-187 validates both via measurements)

**Result: FAIL** — Defects 3 and 4 (server-timestamp AC missing, mid-spawn AC missing)

---

### ABS-185 — Orchestrator: wire remote claim into dispatch behind ORCH_CLAIM_MODE

**DoR checklist**:
- Measurable ACs: PASS — all 5 ACs name distinct observable behaviors: ORCH_CLAIM_MODE=off unchanged, deferred-not-claimed, lost-claim-releases-slot, won-claim-proceeds, cap-limit enforced
- Flags consistent: PASS
- Role hint: PASS (`be-developer`)
- Single-spawn scope: PASS
- Spec references: PASS (`spec §7, §4.6`)
- No open uncertainty: PASS

**Result: PASS**

---

### ABS-186 — Orchestrator: optional ORCH_CLAIM_ASSIGN human-visibility layer

**DoR checklist**:
- Measurable ACs: PASS — 4 ACs cover flag-off/on, won-claim-assigns, failure-non-fatal, assignee-not-authoritative
- Flags consistent: PASS
- Role hint: PASS (`be-developer`)
- Single-spawn scope: PASS
- Spec references: PASS (`spec §3, §6`)
- No open uncertainty: PASS

**Result: PASS**

---

### ABS-187 — Tests: claim mutual-exclusion (unit + concurrency + E2E + smoke)

**DoR checklist**:
- Measurable ACs: **FAIL** — two gaps:

  **Gap A (role hint)**: `role:` field absent from frontmatter. Enrichment recommended `role:be-developer` and flagged it for the DoR gate; the update was not applied.

  **Gap B (live smoke AC)**: AC-2 reads "Live smoke shows exactly one spawn for contested ticket." The test matrix explains this requires two live checkouts and real Jira access to measure comment-visibility latency. A single subagent cannot provision two independent orchestrator environments against a live Jira project. The AC is correct as a goal but unachievable by a single subagent as written. It needs to distinguish what the agent delivers (runnable smoke test script + documented procedure) from what a human operator executes.

- Flags consistent: PASS (no design/security/data flags needed)
- Role hint: **FAIL** (missing)
- Single-spawn scope: PASS (CI portion is automatable; smoke procedure document is achievable)
- Spec references: PASS (`spec §8, §9`)
- Open uncertainty: PASS — three timing uncertainties named with resolution via measurement ACs

**Result: FAIL** — Defects 5 and 6

---

### ABS-188 — Docs: multi-orchestrator operating mode in ORCHESTRATOR_SOP

**DoR checklist**:
- Measurable ACs: **FAIL** — missing AC for the PO-mandated fleet spend statement. The triage decision (2026-07-09T13:07:07Z) and BSA handoff both require the SOP to state "fleet spend = N × SPAWN_BUDGET (budget is per runner)." The SOP content description in the ticket mentions it; the ACs do not. Without an AC, the implementation gate cannot verify this requirement.
- Flags consistent: **FAIL** — `skip-review` and `skip-test` flags are not set. Enrichment recommended both for this docs-only ticket (no executable code, no schemas). Without them the pipeline spawns a Code Review seat and a Test seat unnecessarily.
- Role hint: **FAIL** — `role:` field absent from frontmatter. Enrichment recommended `role:be-developer`; update not applied.
- Single-spawn scope: PASS
- Spec references: PASS (`spec §6, §10, §4.5, §4.6`)
- No open uncertainty: PASS

**Result: FAIL** — Defects 7, 8, and 9

---

### ABS-189 — Orchestrator: optional claim-comment janitor

**DoR checklist**:
- Measurable ACs: PASS — observable behaviors named: only stale claim comments removed, live claim kept, correctness independent of janitor
- Flags consistent: PASS
- Role hint: PASS (`be-developer`)
- Single-spawn scope: PASS
- Spec references: PASS (`spec §8 edge case 4`)
- No open uncertainty: PASS

**Result: PASS**

---

## Coverage Map: Epic AC → Child Story ACs

| Epic AC | Child story coverage | Status |
|---|---|---|
| AC-1: exactly one spawns; other logs SKIP-CLAIMED | ABS-185 AC-4 (won claim spawns); ABS-187 unit test (single winner) | PASS |
| AC-2: watchdog heartbeat keeps claim fresh; peer never wins mid-episode | ABS-184 AC-5 (throttle only — peer-perspective absent) | PARTIAL GAP |
| AC-3: machine holds at most ORCH_MAX_CONCURRENT claims; deferred unclaimed | ABS-185 AC-5 (cap limit); ABS-185 AC-2 (deferred not claimed) | PASS |
| AC-4: takeover only after ORCH_CLAIM_TTL without refresh | ABS-184 AC-4 (stale reclaimed); ABS-184 AC-3 (idempotent re-dispatch) | PASS |
| AC-5: restarted runner reuses persisted instance-id; no self-yield | ABS-183 AC-4 ("stable per-run") — does NOT cover cross-restart reuse | UNMAPPED |
| AC-6: staleness from server-assigned `### <at>` header, not body `at:` | ABS-184 AC-2 (adjudication order) — does NOT cover TTL timestamp source | UNMAPPED |
| AC-7: cmd_get returns full comment list (pagination) | ABS-182 scope description only — no AC | UNMAPPED |
| AC-8: ORCH_CLAIM_MODE=off is byte-for-byte current behaviour | ABS-185 AC-1 | PASS |

**Unmapped: AC-5, AC-6, AC-7. Partial gap: AC-2.**

---

## Blind-Spot Catalog

| Category | Status |
|---|---|
| Error/edge cases | ok — adapter failure, non-fatal assign, TTL reclaim, idempotent re-reads covered; minor: ABS-183 has no AC for corrupt or empty instance-id file on startup |
| Authz/RLS | N/A — orchestrator-internal bash; no user-facing auth surface |
| Migrations | N/A — no schema or database changes; claim kind and instance-id file are additive |
| Idempotency | ok — ABS-184 AC-3 (no double-stake), spec §4.3 step-0 idempotency explicit |
| Observability | ok — intents CLAIM/CLAIM-WON/SKIP-CLAIMED, instance-id logged at startup, assign-failure warning; minor: ABS-189 janitor has no logging AC |
| Rollback | ok — ORCH_CLAIM_MODE=off is the disable switch; ABS-185 AC-1 tests it explicitly |

---

## Defect List (rework — normalization class)

All 9 defects below are normalization-class fixes: tighten or add an AC, set a missing role hint, apply flags. None change what a story delivers.

1. **ABS-182** — Add AC: "cmd_get returns the full comment list for a ticket with comments spanning multiple Jira API pages, or the implementation verifies the default page size provably exceeds any realistic comment count and documents the proof." [Epic AC-7 coverage gap]

2. **ABS-183** — Add AC: "After a runner stops and restarts, ORCH_INSTANCE_ID loaded from `work/.orchestrator/instance-id` matches the pre-restart value; the runner recognizes pre-restart claims as its own and does not self-yield for up to ORCH_CLAIM_TTL." [Epic AC-5 coverage gap]

3. **ABS-184** — Add AC: "Staleness computation reads the server-assigned `### <at>` comment header (UTC-normalized via jira_ts_to_z), not the body `at:` field; a claim whose body `at:` appears fresh but whose server header exceeds ORCH_CLAIM_TTL is reclaimed." [Epic AC-6 coverage gap]

4. **ABS-184** — Add AC: "In a simulated spawn running longer than ORCH_CLAIM_TTL, the watchdog heartbeat re-stakes the claim before it expires; a concurrent peer's acquire_remote_claim returns false for the full spawn duration." [Epic AC-2 partial gap]

5. **ABS-187** — Set `role: be-developer` (frontmatter field missing; flagged by enrichment). [DoR role hint]

6. **ABS-187** — Reword AC-2: "A runnable two-machine smoke test script and documented execution procedure are delivered; the procedure is marked as a human-run step requiring live Jira access and two separate checkouts; it records Jira comment-visibility latency and the recommended ORCH_CLAIM_SETTLE_MS value." [DoR single-subagent scope]

7. **ABS-188** — Set `role: be-developer` (frontmatter field missing; flagged by enrichment). [DoR role hint]

8. **ABS-188** — Add AC: "The SOP section states explicitly: total fleet spend = N × SPAWN_BUDGET, where N is the number of orchestrator machines; budget is not shared across machines." [PO mandate, triage decision 2026-07-09T13:07:07Z]

9. **ABS-188** — Apply `skip-review` and `skip-test` flags (docs-only ticket; without them the pipeline spawns unnecessary Code Review and Test seats). [DoR flags consistent with content]

---

## Cross-Story Checks

**Dependency graph**: acyclic and correct — ABS-182 and ABS-183 have no deps; ABS-184 depends on both; ABS-185 depends on ABS-184; ABS-186/187/188 depend on ABS-185; ABS-189 depends on ABS-182. No cycles.

**Overlap / duplication**: none — each ticket addresses a distinct layer (adapter kind, identity, algorithm, dispatch, visibility, tests, docs, cleanup).

---

## Exit

**Verdict**: REWORK — 5 children fail DoR, 3 epic ACs unmapped.

**Transition**: ABS-181 → Grooming

**BSA action**: auto-normalize ABS-182, ABS-183, ABS-184, ABS-187, and ABS-188 against the 9-item defect list above (all normalization-class); re-enter Ticket Review.

ABS-185, ABS-186, ABS-189: PASS — no rework needed; do not re-decompose.

---

## Round 2 Review (2026-07-10) — READY

**Iteration**: 2 of 3 (first was rework; second is ready — no third needed)

**BSA Normalization Applied (all 9 defects)**:
All 9 defects from Round 1 resolved via BSA decision comments (amendment pattern — adapter has no in-place description edit; BSA comments are DoR-of-record). Verified against live ticket data:

| Defect | Child | Fix Applied | Verified |
|---|---|---|---|
| 1 — pagination AC missing | ABS-182 | BSA decision comment adds AC | ✅ frontmatter + comment present |
| 2 — restart-reuse AC missing | ABS-183 | BSA decision comment adds AC | ✅ |
| 3 — server-timestamp TTL AC missing | ABS-184 | BSA decision comment adds AC | ✅ |
| 4 — mid-spawn heartbeat AC missing | ABS-184 | BSA decision comment adds AC | ✅ |
| 5 — role: hint missing | ABS-187 | Applied to frontmatter | ✅ role: be-developer in frontmatter |
| 6 — live-smoke AC not single-spawn-achievable | ABS-187 | BSA decision comment rewrites AC-2 | ✅ |
| 7 — role: hint missing | ABS-188 | Applied to frontmatter | ✅ role: be-developer in frontmatter |
| 8 — fleet-spend AC missing | ABS-188 | BSA decision comment adds AC | ✅ |
| 9 — skip-review + skip-test flags unset | ABS-188 | Applied to frontmatter | ✅ flags: [skip-review, skip-test] |

**DoR Round 2 Results**: All 8 children PASS.
**Coverage Map**: All 8 epic ACs have child story coverage.
**Blind-Spot Catalog**: All categories ok (N/A for authz/RLS and migrations).

**Final verdict**: READY
**Exit transition**: ABS-181 → Architecture Review (performed by QAS)
