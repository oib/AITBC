# QA Validation Report — ABS-457

**Ticket**: ABS-457 — Retro: docs-station Done-precondition must test remote main, not stale local HEAD  
**Branch**: `ABS-457-auto`  
**Commit**: `b1ec3f7`  
**QAS**: qas  
**Date**: 2026-07-19  
**Verdict**: ✅ APPROVED

---

## Validation Method

Inspection-only (skill/recipe text change; no runtime code surface, no test files added or
changed → ABS-453 green-run proof obligation does NOT apply).

Files changed in `b1ec3f7` (single commit):
```
harness/claude/skills/docs-station/SKILL.md   (+32 / -9)
```
Live `.claude/` directory: **untouched** (confirmed by `git show b1ec3f7 --name-only`).

---

## AC Verification

### AC1 ✅ — `TARGET="HEAD"` removed; default is now remote-tracking branch name

Evidence (line 40 of `harness/claude/skills/docs-station/SKILL.md` on `ABS-457-auto`):
```bash
TARGET="main"   # the target/epic branch NAME (e.g. main, or the epic branch)
                # — a branch name, NEVER local HEAD.
```
And the test at line 51:
```bash
if git merge-base --is-ancestor "$STORY_SHA" "$ORIGIN/$TARGET"; then
```
`$ORIGIN/$TARGET` = remote-tracking ref. No copy-paste run tests local `HEAD`.

### AC2 ✅ — Explicit `git fetch <remote> <target>` immediately before `--is-ancestor`

Evidence (line 48):
```bash
git fetch -q "$ORIGIN" "$TARGET"
```
Immediately precedes the `--is-ancestor` test (line 51) — byte-aligned with the proven
`merge-status.sh:49-50` pattern (`git fetch -q "$ORIGIN" "$target"` →
`git merge-base --is-ancestor "$commit" "$ORIGIN/$target"`).

Cross-checked against sibling helper:
```
merge-status.sh line 49: git fetch -q "$ORIGIN" "$target" || die …
merge-status.sh line 50: if git merge-base --is-ancestor "$commit" "$ORIGIN/$target" …
```
Pattern alignment: exact.

### AC3 ✅ — ABS-452 stale-HEAD conformance example present

Evidence (lines 59–73):
- Narrative: `e518a6b` merged on `gitlab/main` (MR !109, tip `7d57500`); local `HEAD`
  stale/unfetched.
- Old behaviour: `git merge-base --is-ancestor e518a6b HEAD` → exit 1 → "NOT MERGED" loop
  (trapped Docs twice, ~4 wasted seats).
- New behaviour:
  ```bash
  ORIGIN=gitlab STORY_SHA=e518a6b TARGET=main
  git fetch -q gitlab main                                   # pulls tip 7d57500
  git merge-base --is-ancestor e518a6b gitlab/main && echo MERGED   # -> exit 0, MERGED
  ```
  Merged-on-remote story detected correctly; Docs → Done proceeds.

### AC4 ✅ — `generate-governor.sh --providers --check` EXIT=0; only harness edited

```
$ scripts/generate-governor.sh --providers --check
generate-governor.sh --providers --check: OK (agent_providers/claude_code == generated(harness/claude)).
EXIT=0
```
`git show b1ec3f7 --name-only` confirms single file touched:
`harness/claude/skills/docs-station/SKILL.md` — zero `.claude/` paths.

`git show ABS-457-auto:.claude/skills/docs-station/SKILL.md | grep TARGET` → still has
`TARGET="HEAD"` (pre-fix state from last governor promotion) confirming the live harness is
intentionally untouched and will be regenerated at next release.

---

## Out-of-Scope Confirmed

- `harness/claude/skills/merge-status/merge-status.sh` — **untouched** (already correct).
- ABS-132 respawn-limit logic — **untouched** (out of scope).

---

## Test-Touching Obligation (ABS-453)

No `*.spec.ts` / `*.test.ts` files added or modified in `b1ec3f7`. Obligation: **N/A**.

---

## Summary

| Criterion | Result |
|-----------|--------|
| AC1: `TARGET="HEAD"` removed, test against `$ORIGIN/$TARGET` | ✅ PASS |
| AC2: `git fetch -q "$ORIGIN" "$TARGET"` before `--is-ancestor` | ✅ PASS |
| AC3: ABS-452 stale-HEAD conformance example present | ✅ PASS |
| AC4: governor `--check` EXIT=0; only `harness/claude/skills/` edited | ✅ PASS |
| Out-of-scope respected (merge-status.sh, ABS-132 untouched) | ✅ PASS |

**Final Verdict: APPROVED** — all 4 ACs verified; minimal diff (+32/-9); no runtime surface;
pattern-aligned with proven `merge-status.sh` sibling. Story is release-ready.
