# QA Validation Report — ABS-242

**Ticket**: ABS-242 — Backend S10: Docs + Profil-Binding  
**Actor**: qas  
**Date**: 2026-07-16  
**Branch**: ABS-242-auto  
**Commits reviewed**: dc01f0d · b2cdf4b · f97695c · f836b82 (+ ff93015 QA report)  
**Verdict**: **APPROVED ✅ — Iteration 3 of 3**

---

## Acceptance Criteria Results

### AC1 — Lane-Doktrin in task-tracking.md beschreibt den Backend-Fall normativ; jira-sop trägt den Legacy-Scope-Hinweis

**PASS ✅**

- `profiles/neutral/adapters/task-tracking.md`: Backend binding documented in Provider Bindings list as single-lane (`$TRACKER_CMD` only, no MCP). Lane Doctrine section (line 83) establishes: single `$TRACKER_CMD` lane is the **default** for backend/mock/Linear; Jira is the named two-lane **exception**. Backend gets an explicit "two-lane split disappears entirely" paragraph. Normative wording confirmed.
- `harness/claude/skills/jira-sop/SKILL.md`: frontmatter `description` ends with "LEGACY SCOPE — Jira profile only"; skill body opens with a "Scope: Jira-profile only" callout block naming the agentic-backend profile explicitly as the non-applicable case. Both note locations present.

---

### AC2 — Ein neuer Consumer kann nur mit dem Install-Guide von Null auf laufendes Board + registrierten Orchestrator kommen (Doku-Walkthrough als Test)

**PASS ✅**

`docs/guides/AGENTIC-BACKEND-INSTALL.md` walkthrough verified against spec §9/§10:

| Step | Content | Spec §9 requirement |
| --- | --- | --- |
| Step 1 | Configure secrets (`.env.example`, POSTGRES_PASSWORD, BACKEND_BOOTSTRAP_TOKEN) | `.env` for both vars ✓ |
| Step 2 | `docker compose up --build --wait` + healthz verify | `docker compose up` install path ✓ |
| Step 3 | Create project via admin API | bootstrap-token login → create project ✓ |
| Step 4 | Register orchestrator → project-scoped token returned once | register → export token ✓ |
| Step 5 | Wire TRACKER_CMD env vars + smoke-test + dry-run | `TRACKER_CMD=scripts/backend-tracker.sh` ✓ |
| Step 6 | Board URL (`http://localhost:8420`) + all board views | board URL ✓ |
| Import | Optional tar import from mock adapter | import existing tickets ✓ |
| Backup | Two paths: canonical tarball + pg_dump | backup covered ✓ |

Reference section: all 7 cited paths verified present on branch ✓

---

### AC3 — Profil-Eintrag konsistent zu bestehenden Profilen (Platzhalter-Konventionen, settings-Verweise)

**PASS ✅**

`profiles/agentic-backend/profile.yaml` matches `jira-github-postgres/profile.yaml` conventions: identical top-level keys, `{{PLACEHOLDER}}` config, `implemented_by/required` structure, full `approval_boundaries` set ✓

---

### AC4 — Alle Querverweise (ADR-A-0021, Vision, Spec) verlinkt und korrekt

**PASS ✅**

- ADR-A-0021, Spec ABS-229, Vision: all linked and files present on branch ✓
- Anchor links: commit f97695c repaired both dead anchors in ORCHESTRATOR_SOP.md; both now resolve to `#lane-doctrine-tracker_cmd-adapter-and-the-jira-two-lane-exception` (confirmed anchor in task-tracking.md line 83) ✓
- f836b82 introduces no new markdown links — only backtick code references ✓

---

### SCOPE-APPEND AC (operator, 2026-07-13T07:34:59Z) — priority als kanonisches Feld in task-tracking.md

**PASS ✅** *(was FAIL in Iteration 2; fixed in commit f836b82)*

Commit f836b82 adds to `profiles/neutral/adapters/task-tracking.md` Canonical Model section:

| Requirement | Delivered |
| --- | --- |
| ENUM (ordered high-to-low) | `hotfix \| high \| normal \| low` ✓ |
| Default | `normal` ✓ |
| Seats-never-raise rule | "Seats read priority; they MUST NOT raise it — only a human or the PO-agent may increase urgency" ✓ |
| Backend-Adapter mapping | Native `priority` column (DB; S2 API field) ✓ |
| jira-tracker.sh mapping | Highest→hotfix, High→high, Medium→normal, Low/Lowest→low ✓ |
| mock-tracker.sh mapping | `priority:` frontmatter field; defaults to `normal` when absent ✓ |

Verified: `git show ABS-242-auto:profiles/neutral/adapters/task-tracking.md | grep -c "priority"` → 5 occurrences ✓

---

## DoD Checklist

| Item | Result |
| --- | --- |
| Docs-Review durch QAS-Walkthrough | ✅ Complete |
| Keine toten Links (Link-Check) | ✅ PASS — all file refs exist; anchors repaired in f97695c; f836b82 adds no new links |
| Lane-doctrine normative | ✅ PASS |
| Install Guide complete (spec §9/§10) | ✅ PASS |
| Profile consistent with conventions | ✅ PASS |
| SCOPE-APPEND AC (priority field) | ✅ PASS |

---

## Test Plan Coverage

| Test | Result |
| --- | --- |
| Frisch-Install nach Guide (Doku-Walkthrough) | ✅ PASS — 6-step + import + backup path complete |
| Grep auf verwaiste MCP-Referenzen in Neutral-Profil-Doku | ✅ PASS — remaining MCP mentions correctly scoped to Jira two-lane exception |

---

## Verdict

**APPROVED — all 5 ACs and DoD met. Story cleared for Story Acceptance.**

**Informational follow-up** (not a gate issue; recorded per SA note): adapter shim scripts (`backend-tracker.sh`, `jira-tracker.sh`, `mock-tracker.sh`) do not yet implement the `priority` field at the code level — the backend DB column exists (migration `002_work_item_priority.sql`) but the CLI surface and mock frontmatter handling are not wired. Code is explicitly out of scope for this docs story (ticket Scope: "Out of scope: Code"). A follow-up implementation ticket is recommended to make the adapters conform to the now-documented `priority` MUST contract.
