# QA Validation Report — ABS-274

**Ticket**: ABS-274 — Docs-Truth-Fix: Phantom-Pfad `.agentic/templates/feature-request.md` (ADR-A-0008:24 + 2 Doku-Stellen) auf `consumer-feedback-item.md` korrigieren  
**Branch**: `ABS-274-auto`  
**Commit**: `4818653`  
**Validator**: qas  
**Date**: 2026-07-14  
**Iteration**: 1 of 3 (first run; no prior bounces)

---

## Scope

Residual scope after PO re-scope: three prose-only path fixes in three documentation files.  
Items 1 and 2 from the original ticket were already fixed in `efa9b2a` [ABS-252] — correctly excluded from this ticket.

---

## Pre-Check: Branch & Commit

| Check | Result |
|---|---|
| Branch `ABS-274-auto` exists at origin | ✅ CONFIRMED |
| Commit `4818653` is the single new commit on top of `f7c9a68` | ✅ CONFIRMED |
| Commit message matches scope (`docs(adr,guides,sop): fix phantom feature-request.md path → consumer-feedback-item.md [ABS-274]`) | ✅ CONFIRMED |
| `git show 4818653 --stat`: 3 files changed, 3 insertions(+), 3 deletions(-) | ✅ CONFIRMED |

---

## AC1 — All three references point to `.agentic/templates/consumer-feedback-item.md`; sentence stays correct

| File | Line | Post-fix text | Semantically true? |
|---|---|---|---|
| `adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md` | 24 | `…become feature requests to the boilerplate repository (`.agentic/templates/consumer-feedback-item.md`).` | ✅ YES — template `Type` column is `Bug \| Improvement \| Feature`; feature requests genuinely ride this channel |
| `docs/guides/AGENT_DEF_OVERLAY_GUIDE.md` | 123 | `…it is an upstream feature request (`.agentic/templates/consumer-feedback-item.md`), not a fork or overlay.` | ✅ YES — same channel, same rationale |
| `docs/sop/BOILERPLATE_MIGRATION_SOP.md` | 275 | `…it is an upstream feature request (`.agentic/templates/consumer-feedback-item.md`), not a fork.` | ✅ YES — same channel |

**Additional semantic check**: `.agentic/templates/consumer-feedback-item.md` is the **only** file in `.agentic/templates/` (`git ls-tree origin/ABS-274-auto .agentic/templates/` → `consumer-feedback-item.md` only). The pointer now resolves to a real, git-tracked file. Before the fix it resolved to nothing.

**AC1: PASS**

---

## AC2 — `git grep` returns zero hits outside blueprint/ and docs/agent-outputs/

Command run against branch tree (checked out from `origin/ABS-274-auto`):
```
git grep -n "feature-request.md" -- . ':!blueprint' ':!docs/agent-outputs'
```
**Result**: exit code 1 (zero matches) ✅

**Historical refs correctly preserved** (excluded dirs verified via `git diff f7c9a68 origin/ABS-274-auto -- blueprint/ docs/agent-outputs/` → empty diff):
- `blueprint/CROSSWALK.md:40` — historical design intent, untouched ✅
- `blueprint/IMPLEMENTATION-PLAN.md:50` — historical design intent, untouched ✅
- `docs/agent-outputs/qa-validations/ABS-260-qa-validation.md` (3 refs) — historical QA artefact, untouched ✅

**AC2: PASS**

---

## AC3 — No behaviour change, no code, no new file

| Check | Result |
|---|---|
| Diff: 3 files, +3 lines, -3 lines — pure prose path swap | ✅ CONFIRMED |
| No new files created | ✅ CONFIRMED |
| No code changes | ✅ CONFIRMED |
| No schema/migration/RLS surface | ✅ N/A (docs only) |

**AC3: PASS**

---

## Guardrail Compliance

The alternative "define a separate feature-request channel" was explicitly fenced as ADR territory by PO (ADR-A-0004). Tech-writer did not implement it, and system-architect confirmed the ruling in the `In Review` gate. The only file in `.agentic/templates/` already carries `Type: Bug | Improvement | Feature` — no second channel needed. **Guardrail respected: PASS**

---

## Verdict

| AC | Result |
|---|---|
| AC1: All three refs point to correct path; sentences semantically true | **PASS** |
| AC2: `git grep` returns zero hits outside excluded dirs; excluded dirs untouched | **PASS** |
| AC3: Pure doc fix — no code, no new file, no behaviour change | **PASS** |

**Overall: APPROVED**

---

## Evidence Links

- Commit diff: `git show 4818653`
- Branch: `origin/ABS-274-auto`
- Template verified: `git show origin/ABS-274-auto:.agentic/templates/consumer-feedback-item.md`
- AC2 grep: exit code 1 on branch tree
- Excluded dirs clean: `git diff f7c9a68 origin/ABS-274-auto -- blueprint/ docs/agent-outputs/` → empty

**No design flag on ticket → transitioning to Story Acceptance.**
