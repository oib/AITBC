# QA Validation Report: PILOT-80

**Story**: PILOT-80 — Praefix-Amplifikation gemessen: 99,9 % der Eingabe ist Wiederholung, be-developer = 46,5 % der Kosten
**Parent**: PILOT-71
**Date**: 2026-07-27
**Validator**: QAS seat (Claude Sonnet 4.6, headless)
**Branch**: PILOT-80-auto

---

## Commits Verified

| SHA | Description | Reachable |
|---|---|---|
| `da333152` | refactor(agents): trim redundant prose from be-developer def [PILOT-80] | ✓ `refs/heads/PILOT-80-auto` |
| `05915d6c` | docs(work): PILOT-80 prefix-amplification measurement + reduction report [PILOT-80] | ✓ `refs/heads/PILOT-80-auto` |

Both commits exist (`git cat-file -e`) and are reachable from `refs/heads/PILOT-80-auto` (`git for-each-ref --contains`).

---

## AC Verification

### AC1 — Prefix composition measured (size distribution, not guesswork)

The report (`work/improvement-proposals/2026-07-27-PILOT-80-prefix-measurement-and-reduction.md`)
provides a 5-row breakdown:

| # | Component | Size | ~Tokens | Steerable |
|---|---|---|---|---|
| 1 | Claude Code system prompt + tool schemas | — (vendor) | ≈ 23 000 | No |
| 2 | `--agents` JSON: be-developer role body | 13 517 B | ≈ 3 380 | **Yes** ← cut here |
| 3 | `--agents` JSON: `_common-rules` (ABS-174 prepend) | 13 560 B | ≈ 3 390 | Yes (governance-dense) |
| 4 | Spawn packet (policy + ticket body) | 10 600–29 200 B | ≈ 2 650–7 300 | Yes (variable) |
| 5 | `CLAUDE.md` | 7 841 B | ≈ 1 960 | Yes (shared) |

Largest steerable block identified correctly as items 2 + 3 (~27.1 KB / ~6.8k tok). ✓

**AC1: PASS**

### AC2 (BSA-revised) — Cut implemented + baseline + Rechenweg

**(a) Cut in code:**
Independently verified: `awk`-stripped body before (`da333152^`) = **13 517 B**; after = **11 536 B**; delta = **−1 981 B (−14.7 %)**.
Four removed sections confirmed rule-free (see AC4). Provider mirror regenerated in the same commit. ✓

**(b) Baseline + expected reduction with Rechenweg:**
- Pilot-7 BY-ROLE: be-developer `cache_read` = 83 179 216 / 19 Spawns = **4 377 853 / Spawn**
- Removed prefix: 1 981 B ≈ 495 tok; turns ≈ 91 → **≈ 45 045 cache_read / Spawn (≈ 1.03 %)**
- Run-wide (19 be-developer spawns): ≈ 855 855 cache_read tokens ≈ **$1.28 / run** (Opus $1.50/MTok)
- Full Rechenweg documented in report. ✓

Report correctly flags that "1.55M/Spawn" in the BSA-revised AC2 is the run-wide average across
all roles (200 474 607 / 129), not the be-developer-specific figure. The corrected seat-specific
value (4.38M, 2.82× the run average) is used throughout. This correction demonstrates measurement
integrity.

Actual next-run cache_read measurement deferred to **PILOT-82** per BSA auto-fix decision. ✓

**AC2: PASS**

### AC3 — Turn count per role (Prefix × Turns is the product)

`num_turns` sample from Pilot-7 result JSONs:

| Role | `num_turns` (sample) | `cache_read` / Spawn |
|---|---|---|
| be-developer | 91 | 4 377 853 |
| rte | 61 | 1 852 288 |
| qas | 41 | 1 932 534 |
| tech-writer | 28.5 | 1 218 607 |

Conclusion documented: be-developer's 2.3× higher `cache_read` vs. the next costliest seat (qas)
matches its 2.2× higher turn count. Prefix size is comparable across seats; the cost driver is
turns × accumulated context, not prefix size alone. Report labels prefix cut correctly as a real
but secondary lever. ✓

**AC3: PASS**

### AC4 — No rule removed (effectiveness retained)

Verified in repository post-trim (`harness/claude/agents/be-developer.md`):

| Rule section | Line | Status |
|---|---|---|
| `## RLS Requirements` | 135 | ✓ present verbatim |
| ESLint guard (`ESLint will error if you use direct prisma calls`) | 143 | ✓ present |
| `## Precondition (Stop-the-Line Gate)` | 35 | ✓ present |
| `## Exit Protocol` | 162 | ✓ present |
| Pattern Execution Workflow Steps 1–5 | 82–127 | ✓ intact |

Removed sections confirmed rule-free:

| Removed block | Rule? | Coverage retained via |
|---|---|---|
| `## 🚀 Quick Start` | No (preview) | Steps 1–5 + Role Overview + Key Principles |
| Step-3 TypeScript example | No (illustration) | RLS Requirements verbatim + ESLint guard (mechanical) |
| `## Common Tasks` | No (pattern-path list) | Step-2 `Reference:` line (unchanged) + `pattern-discovery` skill |
| `## Tools Available` | No (mirror of frontmatter) | `tools:` frontmatter grant (unchanged) |

**AC4: PASS**

### AC5 — Considered and rejected (with reasons)

Report documents 6 options, each with a concrete reason for deferral or rejection:

1. `_common-rules.md` trim — governance-dense (12 rules, each Guard-linked); Ledger-Amendment required per ABS-514; multi-ticket work.
2. Spawn-packet / decision-slot cap — ADR-level decision (ABS-238 AC); not a dev-seat refactoring.
3. `CLAUDE.md` trim — smallest steerable file-item (~2k tok); shared across all seats; broad risk, low yield.
4. Exit Protocol prose trim — every sentence tied to a documented incident (ABS-253, ABS-163, ABS-198); removing = removing a rule without a compensating guard → AC4 violation.
5. Workflow-to-skill migration — correct direction but requires rollenweise comparison + own ticket per the prior analysis.
6. `Key Principles` (6 lines, ~250 B) — considered, kept; reinforces RLS cheaply; risk/yield not worth cut.

**AC5: PASS**

### Messfalle (documented per ticket requirement)

Both RUN-USAGE log blocks verified to sum to **123 Spawns / $185.84** each; 246 / $371.68 if all lines summed (exact double). BY-ROLE block used throughout. ✓

---

## Mirror Parity (ABS-317)

- `generate-governor.sh --providers --check`: **OK** (re-run by this QAS seat)
- `diff harness/claude/agents/be-developer.md agent_providers/claude_code/prompts/be-developer.md`: **IDENTICAL** ✓

---

## Test Suite

No product TypeScript or API surface changed. Change class: harness agent-def (`.md`) + `docs/work/` report. Applicable gates are mirror parity (OK, above) and composer validity (checked by system-architect, `--agents` JSON 24 953 B, valid). `yarn test:unit` / `yarn test:integration` / `yarn lint` / `yarn type-check` do not apply to this change. ✓

---

## Verdict

**APPROVED — Approved for RTE**

All 5 ACs met per BSA-revised AC2. Commits present and reachable. Mirror parity confirmed independently. Rule retention verified line-by-line. Measurement report is factual, calibrated, and correctly scoped: it documents what was cut, why each alternative was rejected, and where the real cost lever lies (turn count, not prefix size). PILOT-82 owns the actual next-run delta.

---

## Forward-Fix Verification (resume spawn, 2026-07-27)

Epic-Integration bounced the story: `test-proposal-contract-lint.sh` (ABS-521) failed because
`work/improvement-proposals/2026-07-27-PILOT-80-prefix-measurement-and-reduction.md` lacked
the 6 required change-contract H2 sections. Be-developer added them in commit `baa3c37d`.

**Commit verified:** `baa3c37d` — +59 lines, docs-only. All 6 sections present:
`## Rationale`, `## Suggested Boilerplate Change`, `## Impact`, `## Invariants Preserved`,
`## Falsifying Eval`, `## Rollback`.

**Gates run this spawn:**

| Check | Result |
|---|---|
| `scripts/proposal-contract-lint.sh` | OK — every post-2026-07-21 proposal carries the change contract |
| `tests/test-proposal-contract-lint.sh` | 5/5 PASS |
| `generate-governor.sh --providers --check` | OK — mirror parity unchanged |
| `diff harness↔mirror` (be-developer.md) | IDENTICAL |
| Commit `baa3c37d` reachable | `refs/remotes/gitlab/PILOT-80-auto` ✓ |

No product TS/API surface touched. AC1–AC5 verdict from prior spawn stands unchanged.

**Verdict: APPROVED — forward-fix resolves the Epic-Integration bounce; all gates green.**
