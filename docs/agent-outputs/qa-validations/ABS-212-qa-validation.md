# QA Validation — ABS-212

**Ticket**: ADR-Acceptance-Closeout: Tracker-Akzeptanz muss das ADR-File-Frontmatter nachziehen  
**Branch**: `ABS-212-auto`  
**Commit**: `0c017d7`  
**QAS actor**: qas  
**Date**: 2026-07-12  
**Verdict**: APPROVED

---

## Validation runs

All commands executed independently (not trusting prior handoffs).

### Test suite
```
bash tests/test-adr-acceptance-closeout.sh
→ Passed: 6  Failed: 0  Total: 6
```

### Syntax checks
```
bash -n scripts/adr-acceptance-drift.sh    → OK
bash -n scripts/pre-release-check.sh       → OK
```

### Live drift check
```
bash scripts/adr-acceptance-drift.sh
→ exit 0, no drift in current adrs/ tree
```

---

## AC results

### AC1 — PASS
`scripts/adr-acceptance-drift.sh` flags ADRs accepted in the record (agentic index row `— **Accepted**` [signal-a] or `accepted_by`/`accepted_date` present [signal-b]) while file `status:` is still `proposed`. Wired into `scripts/pre-release-check.sh` lines 366–376 as a `check_warn` (non-blocking warning tier). Missing-script case also issues a warning. Test cases 1–6 cover: clean tree, signal-b drift, signal-a drift, closed-out (no alert), false-positive guard (in-text mention in Accepted row), live tree scan. All 6 pass.

Architect ruling on AC1 design deviation (local proxy vs. tracker-comment heuristic): accepted. Pre-release check is credential-free; the proxy deterministically catches the A-0017 partial-closeout class.

### AC2 — PASS
`docs/sop/ADR_AUTHORING_GUIDE.md` line 112: "ADR Acceptance Closeout (ABS-212)" section documents who flips (`accepted_by`, `accepted_date`, index row), when (same acceptance PR), via which PR. `adrs/agentic/README.md` line 18: supporting note referencing the closeout requirement.

### AC3 — PASS
`specs_templates/spec_template.md` lines 146–151: conditional DoD line for ADR-bearing stories. Requires frontmatter + index row flip in the same acceptance PR; cites `scripts/adr-acceptance-drift.sh` and references `docs/sop/ADR_AUTHORING_GUIDE.md`. Acceptance stays human-only (ADR-A-0004) — out-of-scope carve-out intact.

---

## Scope check

No new external dependencies. No product code modified. The ADR acceptance mechanism stays human-only (ADR-A-0004). Smallest diff satisfying 3 ACs.

Residual limitation recorded by architect (non-blocking): a pure tracker-only acceptance leaving zero local trace is invisible to the credential-free check. Mitigation is procedural via AC2/AC3.

---

## DoD checklist

- [x] All 3 acceptance criteria met (verified against file content)
- [x] Test suite: 6/6 PASS
- [x] `bash -n` syntax clean
- [x] Live ADR tree: no drift
- [x] No RLS/DB/auth/TS surface (bash + docs + template)
- [x] No new dependencies
- [x] Out-of-scope carve-out intact (agents never accept ADRs)
- [x] Evidence committed and pushed on branch under review

---

## Final verdict

**APPROVED** — all 3 ACs satisfied, tests green, no scope violations. Advancing to Story Acceptance.
