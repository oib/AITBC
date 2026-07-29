# Epic ABS-392 — Merge-Reihenfolge + Rebase-Gate Merge Log

> Append-only. Each entry records one story merge onto `epic/ABS-392-merge-readiness-rebase-gate`.
> Entries are never edited or removed.

---

## Entry 1 — ABS-395 (2026-07-17)

| Field | Value |
|-------|-------|
| **Story** | ABS-395 — Backend computed field merge_readiness (base_sha vs epic-tip) + webhook recompute + packet delivery |
| **MR** | !43 (GitLab gitlab.haemosan.at/boilerplate/agentic-boilerplate/-/merge_requests/43) |
| **Story commit** | `a41844e` feat(backend): computed merge_readiness (base_sha vs epic-tip) in packet [ABS-395] |
| **QA report commit** | `6d049b2` docs(qa): ABS-395 QA validation report — merge_readiness APPROVED |
| **Merge commit** | `0066293` (merge into `epic/ABS-392-merge-readiness-rebase-gate`) |
| **Merged at** | 2026-07-17T19:11:57Z |
| **Method** | Auto (GitLab, no CI pipeline on self-hosted fallback; agent pipeline: architect + QAS APPROVED) |
| **Epic branch tip** | `0066293` post-merge |

---

## Entry 2 — ABS-396 (2026-07-17)

| Field | Value |
|-------|-------|
| **Story** | ABS-396 — Topological merge-token queue: grant ADR-A-0014 token in `depends_on` topo-order (not FIFO) |
| **MR** | !48 (GitLab gitlab.haemosan.at/boilerplate/agentic-boilerplate/-/merge_requests/48) |
| **Story commit** | `e433464` feat(orch): grant merge token in depends_on topo-order not FIFO [ABS-396] |
| **QA report commit** | `b2ccebf` docs(qa): ABS-396 QA validation report — topo merge-token APPROVED [ABS-396] |
| **Merge commit** | `947a80e` (merge into `epic/ABS-392-merge-readiness-rebase-gate`) |
| **Merged at** | 2026-07-17T19:46:10Z |
| **Method** | Auto (GitLab, no CI pipeline on self-hosted fallback; agent pipeline: architect + QAS APPROVED, PO ACCEPTED) |
| **Epic branch tip** | `947a80e` post-merge |

---

## Entry 3 — ABS-397 (2026-07-17)

| Field | Value |
|-------|-------|
| **Story** | ABS-397 — Rebase-gate on Story Acceptance → Merging edge (backing lever 2 of epic ABS-392) |
| **MR** | !50 (GitLab gitlab.haemosan.at/boilerplate/agentic-boilerplate/-/merge_requests/50) |
| **Story commit** | `7de8cab` feat(transitions): rebase-gate on Story Acceptance -> Merging [ABS-397] |
| **QA report commit** | `8a7deba` docs(qa): ABS-397 QA validation report — APPROVED |
| **Merge commit** | `fb2ec4b` (merge into `epic/ABS-392-merge-readiness-rebase-gate`) |
| **Merged at** | 2026-07-17T19:57:15Z |
| **Method** | Auto (GitLab, no CI pipeline on self-hosted fallback; agent pipeline: architect + QAS APPROVED, PO ACCEPTED) |
| **Epic branch tip** | `fb2ec4b` post-merge |

---

## Entry 4 — ABS-398 (2026-07-17)

| Field | Value |
|-------|-------|
| **Story** | ABS-398 — Degraded merge-base rebase check for the jira/mock profile + behaviour docs |
| **MR** | !53 (GitLab gitlab.haemosan.at/boilerplate/agentic-boilerplate/-/merge_requests/53) |
| **Story commit** | `91f351d` feat(rebase-gate): degraded merge-base check for the jira/mock profile + docs [ABS-398] |
| **QA report commit** | `2d0cc95` docs(qa): ABS-398 QA validation report — APPROVED |
| **Merge commit** | `8d610dc` (merge into `epic/ABS-392-merge-readiness-rebase-gate`) |
| **Merged at** | 2026-07-17T20:51:38Z |
| **Method** | Auto (GitLab, no CI pipeline on self-hosted fallback; agent pipeline: architect + QAS APPROVED, PO ACCEPTED) |
| **Epic branch tip** | `8d610dc` post-merge |

---

## Entry 5 — ABS-399 (2026-07-18)

| Field | Value |
|-------|-------|
| **Story** | ABS-399 — Epic acceptance test: 3-story shared-file sequential-merge end scenario passes Merging with zero conflict-bounce |
| **MR** | !60 (GitLab gitlab.haemosan.at/boilerplate/agentic-boilerplate/-/merge_requests/60) |
| **Story commit** | `5424c1d` test(orchestrator): epic-end 3-story shared-file sequential-merge acceptance test [ABS-399] |
| **QA report commit** | `3e5d778` docs(qa): ABS-399 QA validation report — APPROVED |
| **Merge commit** | `62ee2f4` (merge into `epic/ABS-392-merge-readiness-rebase-gate`) |
| **Merged at** | 2026-07-18 |
| **Method** | Auto (GitLab, no CI pipeline on self-hosted fallback; agent pipeline: architect + QAS APPROVED, PO ACCEPTED) |
| **Epic branch tip** | `62ee2f4` post-merge |

---

## Entry 6 — ABS-427 (2026-07-18)

| Field | Value |
|-------|-------|
| **Story** | ABS-427 — Backend event feed delivers create-events (ORCH_REQUIRE_START_LABEL=0 fix) |
| **MR** | n/a — QAS bundled story code + QA report into direct commit on epic branch |
| **Story commit** | `249962a` fix(events): deliver create-events on the event feed [ABS-427] |
| **QA report commit** | `f6f6b57` docs(qa): ABS-427 QA validation report — APPROVED (bundled code + report) |
| **Merge commit** | `f6f6b57` (direct QAS commit onto `epic/ABS-392-merge-readiness-rebase-gate`) |
| **Merged at** | 2026-07-18 |
| **Method** | QAS direct-commit — story code and QA report bundled into `f6f6b57` directly on the epic branch. `git rebase --onto` confirmed: story commit `249962a` dropped as patch already upstream. No MR created. arch + QAS APPROVED, PO ACCEPTED. |
| **Epic branch tip** | `f6f6b57` (unchanged; content already present) |
