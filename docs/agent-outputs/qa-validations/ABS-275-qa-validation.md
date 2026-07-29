# QA Validation Report — ABS-275

**Ticket:** ABS-275 — Repo-Config: .gitattributes LF-Normalisierung (CRLF-Working-Trees auf Windows)  
**Branch:** ABS-275-auto  
**Commits:** 3848cfa (fix), 7b6a38b (test), d2082ed (changelog)  
**QAS Run:** 2026-07-14  
**Verdict:** ✅ APPROVED

---

## Evidence: Independent Verification (not taken on trust)

### AC1 — `* text=auto eol=lf` + `*.sh text eol=lf` in `.gitattributes`, coexisting with `merge=union`

**Verified via `git check-attr` (git's own resolver, not file text):**

```
scripts/orchestrator.sh: text: set
scripts/orchestrator.sh: eol: lf
README.md: text: auto
README.md: eol: lf
docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md: merge: union
docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md: text: auto
docs/sop/ORCHESTRATOR_SOP_CHANGELOG.md: eol: lf
```

Coexistence confirmed: the SOP changelog resolves `eol: lf` **and** `merge: union` simultaneously. Git attributes are per-attribute, not per-line — verified, not asserted.

**Verdict: PASS ✅**

---

### AC2 — Regression test asserting the eol-rules are present

**File:** `tests/test-gitattributes-eol.sh` (10 assertions)

**Test run (positive):**
```
Total:  10
Passed: 10
Failed: 0
ALL TESTS PASSED — EXIT: 0
```

**Negative control (QAS-run, pre-fix `.gitattributes` with only `merge=union`):**
```
FAIL '* text=auto eol=lf' is declared
FAIL '*.sh text eol=lf' is declared
FAIL a .sh file resolves text=set
FAIL a .sh file resolves eol=lf
FAIL a .md file resolves text=auto
FAIL a .md file resolves eol=lf
FAIL an extensionless path resolves eol=lf
PASS SOP change log keeps merge=union (ABS-215)
FAIL SOP change log also resolves eol=lf (ABS-275)
PASS no CRLF blobs in the index

Total: 10 | Passed: 2 | Failed: 8 — EXIT: 1
```

The test can fail (exit 1, 8/10 assertions fail against pre-fix content). This is a genuine regression guard, not decoration. The negative control was run by QAS independently.

**shellcheck:** PASS (no warnings)

**CI auto-discovery:** `.github/workflows/tests.yml` line 60 globs `tests/test-*.sh` — the new file is auto-discovered.

**Verdict: PASS ✅**

---

### AC3 — HARNESS_CHANGELOG note with `git add --renormalize` recipe

**`changelog-slice.sh --since 2.25.1 --to 2.25.2` output (abbreviated):**

```
## 2.25.2 (null)

UNRELEASED — collects v2.25.2 stories... ABS-275 (repo config): .gitattributes
gains the LF-normalisation rules '* text=auto eol=lf' and '*.sh text eol=lf'...

### Migration notes
- ABS-275 (line endings): ... forks carrying CRLF blobs ... must run the
  one-time renormalisation ONCE after upgrading:
  `git add --renormalize . && git commit -m 'chore: renormalize line endings to LF'`
  ...
```

The migration note is present and consumer-visible. The recipe matches AC3 requirements.

**Verdict: PASS ✅**

---

## Additional QAS Verifications

### Provenance claims independently verified

```
git cat-file -t 837d464  → blob   (ticket body claims this is a commit — it is not)
git cat-file -t bec814a  → not found in this repo
git cat-file -t f79bb79  → commit (ABS-215, correctly cited in the artifacts)
git log --diff-filter=A -- .gitattributes → f79bb79 (file created here, not modified)
```

The artifacts commit the **correct** hash (`f79bb79`). The ticket description carries bad hashes — the fix did not propagate this error. (BSA/PO should correct the ticket description text.)

### No CRLF blobs in index

```
git grep --cached -I -l -- $'\r'  → (empty)
```

Renormalization would be a no-op for this repo. Only fork-consumers with pre-existing CRLF blobs need the AC3 recipe — exactly as stated.

### Blast-radius check

- Zero tracked `.bat`/`.cmd`/`.ps1` files — no file type that legitimately needs CRLF exists in this repo. The catch-all rule cannot break any executable surface.
- `text=auto` leaves binaries alone (auto-detected).

---

## Pre-Existing Failures (Confirmed Out-of-Scope)

The BE and architect both claimed 2 pre-existing failures (`test-orchestrator.sh`, `test-wrong-entry-guard.sh`) plus `check-skills-parity.sh`. These failures assert worktree/provenance semantics that do not hold in a story worktree and have no causal path from any `.gitattributes` change. Accepted as pre-existing; not counted against ABS-275.

---

## AC Verdict Summary

| AC | Description | Result |
|----|-------------|--------|
| AC1 | `* text=auto eol=lf` + `*.sh text eol=lf` in `.gitattributes`, coexisting with `merge=union` | ✅ PASS |
| AC2 | Regression test asserting eol-rules present (negative control verified by QAS) | ✅ PASS |
| AC3 | HARNESS_CHANGELOG consumer note with `git add --renormalize` recipe | ✅ PASS |

---

## Final Verdict

**APPROVED** — All three acceptance criteria independently verified by QAS.  
The negative control was run by QAS directly (not taken on trust): exit 1, 8/10 fail against pre-fix `.gitattributes`, exit 0 with the fix. The test is a genuine regression guard.  

Non-blocking finding (already recorded by architect): root `.gitattributes` is outside `sync_scope` in `.harness-manifest.yml`, so pure harness-adopters (not fork-consumers) do not receive this fix. This is ABS-248 territory (deferred, pending ADR-A-0008 redesign) — not a defect in this change; no AC claims adopter delivery.
