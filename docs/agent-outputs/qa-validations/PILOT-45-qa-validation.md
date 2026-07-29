# QA Validation Report — PILOT-45

**Title**: Cutover-Enabler: einmaliger Jira->Backend-Backlog-Import (Projekt ABS), idempotent mit Dry-Run  
**Ticket**: PILOT-45 / Jira ABS-545  
**Branch**: PILOT-45-auto  
**Commit reviewed**: c7bcd53b  
**QA run date**: 2026-07-25  
**Verdict**: ✅ APPROVED

---

## Scope & Implementation

Single file added: `scripts/cutover-jira-to-backend-import.py` (+519 lines)  
Counterpart to `work/scratch/end-of-run-jira-export.py` — one-time operator tool for Jira ABS → Backend ABS cutover.

---

## Acceptance Criteria Verification

### AC 1 — Imports all open ABS tickets (statusCategory != Done), title/desc/labels/role-lane-flag/parent-epic/links/priority into NEW backend project 'ABS'

- ✅ JQL: `project = ABS AND statusCategory != Done ORDER BY key ASC`
- ✅ `BACKEND_TARGET_PROJECT = "ABS"` hard-pinned; `self.env["TRACKER_PROJECT"] = BACKEND_TARGET_PROJECT` overrides any inherited TRACKER_PROJECT (prevents accidental write to PILOT)
- ✅ `derive_fields()` extracts `role:`, `lane:`, `flag:` prefixes into backend fields; unknown `flag:*` values demoted to plain labels (no create abort)
- ✅ Epics sorted first (`rank = {"epic": 0, "ticket": 1, "subtask": 2}`) so parent twins exist when children are created
- ✅ `jira2backend` dict tracks created twins; `parent_bkey = jira2backend.get(parent_jkey)` wires parent
- ✅ Pass 2 wires `depends-on` (from Blocks links) and `relates` links when both endpoints are imported
- ✅ `PRIORITY_MAP` with `"highest": "high"` clamp — ABS-261 hotfix never auto-set
- ✅ `/search/jql` endpoint used (410-safe); `nextPageToken` pagination handles >100 issues

### AC 2 — Idempotent (no duplicates; marker comment with Jira key on backend item, jira_key as back-reference)

- ✅ `find_by_jira()` searches backend by label `jira:ABS-N` before every create → SKIP-CREATE on hit
- ✅ Backend marker comment: `[cutover-import <- ABS-N]` with `jira_key={key}` in body posted after create
- ✅ Link dedup: `planned_links` set prevents duplicate `depends-on`/`relates` links
- ✅ Jira-side marker guard: `has_marker = JIRA_MARKER in json.dumps(comments)` — idempotent on re-run

### AC 3 — Dry-run default, --execute explicit; report table

- ✅ `--execute` is `action='store_true'` (default `False`) → dry-run by default; nothing written without explicit flag
- ✅ `--only` flag for partial/test imports
- ✅ Report table: `Jira / Aktion / Detail/Ergebnis` printed for all actions (CREATE, SKIP-CREATE, LINK, JIRA-MARK, etc.)
- ✅ Summary: "N Jira->Backend-Twins gesamt, M neu geplant/angelegt" + READ-FEHLER / WRITE-FEHLER sections

### AC 4 — Jira ticket gets '[cutover-import] -> <BACKEND-KEY>' comment + 'migrated-to-backend' label

- ✅ `JIRA_MARKER = "[cutover-import]"` — Posted via `POST /issue/{jkey}/comment`
- ✅ `JIRA_MIGRATED_LABEL = "migrated-to-backend"` — Applied via `PUT /issue/{jkey}` label add
- ✅ Idempotent: `has_marker` / `need_label` guards prevent duplicate marking; `JIRA-SKIP` action logged when both already present

### AC 5 — No status mapping; everything lands as Backlog analog to Intake

- ✅ No `--status` parameter in `be.create()` call
- ✅ Comment in docstring: "KEIN Statusmapping: alles landet per Default auf Backlog (analog Intake)"

---

## Additional Validation Points

| Check | Result |
|-------|--------|
| Python syntax (`py_compile`) | ✅ PASS — no syntax errors |
| `--help` invocation | ✅ PASS — dry-run default documented, `--execute` explicit |
| Operator guardrail: no `TRACKER_PROJECT` inheritance from env | ✅ PASS — explicit `env["TRACKER_PROJECT"] = "ABS"` override |
| ABS-261: hotfix never auto-set | ✅ PASS — `"highest": "high"` clamp in PRIORITY_MAP |
| Project separation from PILOT | ✅ PASS — `BACKEND_TARGET_PROJECT = "ABS"` with env override |
| Scratch files in worktree, not /tmp | ✅ PASS — default `--scratch work/scratch`, no /tmp usage |
| Jira /search/jql (not 410-dead /search) | ✅ PASS — `/search/jql` endpoint used throughout |
| Pagination: nextPageToken loop | ✅ PASS — handles >100 issues |
| Single file scope (no unrelated changes) | ✅ PASS — only `scripts/cutover-jira-to-backend-import.py` changed vs main |
| Commit on story branch PILOT-45-auto | ✅ PASS — c7bcd53b reachable from refs/heads/PILOT-45-auto |
| No test files added/changed | N/A — operator-only CLI tool, no test suite files touched (ABS-453 green-run proof not required) |

---

## Architecture Alignment (from Architect Review c7bcd53b)

Architect verified:
- Live adapter + backend capability flags (ABS-66 check) match every driven flag
- `search`/`create` output parsers correct (key-first after `cut -f3-`; bare-key create)
- Comment kind `notification` valid; link kind `relates` valid (migration 015_work_item_link_relates.sql)
- Label dedup `= ANY(w.labels)` — no false match on `jira:ABS-5` vs `jira:ABS-54`
- No RLS concerns (operator Python tool via adapter CLI, no direct DB access)
- No over-engineering

---

## Flags Check

Ticket labels: `[orchestrator-ready]` — no `design` flag → exit target is `Story Acceptance`.

---

## Final Verdict

**✅ APPROVED for Story Acceptance**

All 5 acceptance criteria verified. Python syntax clean. Dry-run default confirmed. Idempotency (label dedup + marker guards on both sides) verified. ABS-261 hotfix clamp confirmed. Project isolation from PILOT confirmed. Architecture review already approved the live-adapter compatibility. No blocking findings.

Operator note (out of scope for this story, not a blocker): Before running `--execute`, the backend project `ABS` must exist. The architect's handoff noted create-output parse was proven vs mock parity; operator is advised to eyeball the first key on a small `--only ABS-XXX` subset before full cutover.
