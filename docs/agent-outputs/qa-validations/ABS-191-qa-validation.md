# QA Validation — ABS-191
**Spike: validate impeccable detector JSON as qas-design gate evidence**

- **Validator:** QAS
- **Date:** 2026-07-10
- **HEAD reviewed:** f4973cc
- **Ticket status at review:** In Test
- **Prior review:** System Architect APPROVED (Stage 1, Iteration 1 of 3, 2026-07-10T21:08:49Z)
- **Governing ADR:** ADR-A-0017 (proposed)

---

## Evidence files verified

| File | Contents | Status |
|---|---|---|
| `docs/agent-outputs/ABS-191-impeccable-detector-spike-verdict.md` | 215-line verdict doc, 7 sections | Present, readable |
| `docs/agent-outputs/ABS-191-evidence/bad-html.json` | 6 findings, 3 rules (gray-on-color ×2, low-contrast ×3, ai-color-palette ×1) | Present |
| `docs/agent-outputs/ABS-191-evidence/good-html.json` | `[]` | Present |
| `docs/agent-outputs/ABS-191-evidence/styles-css.json` | `[]` (post-waiver; overused-font suppressed) | Present |
| `docs/agent-outputs/ABS-191-evidence/button-tsx.json` | `[]` | Present |
| `adrs/agentic/ADR-A-0017-design-quality-detector-backing.md` | Proposed ADR, status: proposed | Present |

---

## Acceptance Criteria — per-item verdict

### AC 1: Detector run against ≥1 real FE change, JSON output captured

**PASS.**

The repo contains zero tracked FE files (`git ls-files *.tsx *.jsx *.css *.html` = 0). Per ticket scope ("…or a representative fixture"), representative fixtures were used. The test plan required ≥1 known-bad, ≥1 known-good, ≥1 source file — all executed:

- `bad.html` → 6 findings (post-waiver), exit 2 — fires correctly.
- `good.html` → `[]`, exit 0 — stays quiet.
- `styles.css` → `[]` (post-waiver), exit 0 — demonstrates live waiver application.
- `Button.tsx` → `[]`, exit 0 — confirms raw-source miss, which the verdict doc flags as the Tier-1 coverage caveat (§3).

Raw JSON committed under `docs/agent-outputs/ABS-191-evidence/`.

**Finding note (carries ARCH nit):** `bad-html.json` contains 6 findings across 3 rules, while the §1 table narrates "7 findings across 4 rules." §4 explains this: after `ignoreRules: ["overused-font"]` was applied the fired set dropped from 4 rules to 3. The committed JSON is the post-waiver capture; the table reports the pre-waiver run. This is internally consistent and documented in §4. The evidence label does not say "post-waiver" explicitly. Non-blocking; reconcile in a one-line doc amend or ABS-192 records (ARCH nit, same finding).

### AC 2: Written go/no-go verdict + evidence-mapping sketch (rule → PASS/FAIL → tracker comment)

**PASS.**

Verdict: **GO (with caveats)**. Stated unambiguously in the document header and §7.

The mapping sketch in §2 is concrete and complete:
- Rule id: `antipattern` field is the stable key; group by it.
- FAIL signal: presence of ≥1 finding for a rule.
- PASS signal: absence (derived from scanned rule set minus fired set).
- Gate boolean: exit code — `0` (clean) / `2` (findings present). No JSON parse required for the boolean.
- Digest format: `jq -r 'group_by(.antipattern)[] | "FAIL " + .[0].antipattern + ...'`.
- Tracker post: `"$TRACKER_CMD" comment "$TICKET" --kind gate-results --actor qas-design` with plain markdown body.
- No MCP, no LLM call — fits the headless qas-design contract.

### AC 3: False-positive assessment for our design system documented

**PASS.**

§5 covers four distinct FP surfaces:
1. Neutral/backend profiles: N/A — gate is profile-gated on `config.design_system.enabled: true`.
2. Design-system-aware rules: inert without a local `DESIGN.md`/`.impeccable/design.json`; cannot FP on a repo without one.
3. Text/content rules: the real FP risk. Verified FP: legitimate marketing prose tripped `marketing-buzzword`. Seven content rules named (`marketing-buzzword`, `em-dash-overuse`, `theater-slop-phrase`, `aphoristic-cadence`, `all-caps-body`, `numbered-section-markers`, `repeated-section-kickers`).
4. Mitigation: run with `--scope` limited to layout/type domains, or waive the content-rule class via `ignoreRules`.

DOM rules (contrast, gray-on-color, palette, fonts) produced zero false positives on `good.html`. Assessment is specific and actionable.

### AC 4: Pinned version/tag identified for vendoring; Apache-2.0 attribution requirement noted

**PASS.**

§6 provides:
- Pin: `impeccable@3.2.1`
- `dist.shasum`: `22d097c515239f27856fd405653491f594fd1708`
- `dist.integrity`: `sha512-Lnh8BeLNj493iYuKRijVLP5nvdeKvReYtqGeov6tfsqECiKDSHBY5JfkxzfsC912AASMreCwzha0ZY3PC2pw+g==`
- Runtime deps: all pure-JS (`css-select`, `css-tree`, `domutils`, `fflate`, `htmlparser2`, `marked`). No native modules, no LLM/API call.
- Puppeteer: `optionalDependency` for URL scanning only. Vendor with `--omit=optional`.
- Apache-2.0, author Paul Bakaus. Upstream bundles `LICENSE`, no `NOTICE`. Action: retain `LICENSE` in vendored payload, add attribution line to repo's `NOTICE` (aligns with ADR-A-0017 constraint 2).

### AC 5: If no-go — blockers enumerated so ABS-190 can be re-scoped or closed

**N/A (GO verdict).**

§7 explicitly states "No blockers." Six Tier-1 carry-forward constraints enumerated for ABS-192 (rendered HTML/URL vs. raw source; `--omit=optional`; content-rule scope/waiver; dedup + `snippet`-over-`line`; FAIL threshold; pin + attribution). These are design constraints, not blockers.

---

## Scope compliance

| Check | Result |
|---|---|
| No dependency vendored/committed | PASS |
| No adapter/gate/hook/profile/agent-def modified | PASS |
| No package.json changes | PASS |
| Verdict-only deliverable | PASS |
| ADR cites A-0017 (renumbered from A-0016 per PO decision) | PASS |
| ABS-66 procedure sketch lands observably via `$TRACKER_CMD` | PASS |

---

## Outstanding nit (non-blocking)

**Evidence-count label (carried from ARCH Stage 1):**  
`bad-html.json` committed with 6 findings/3 rules; §1 table narrates 7/4 (pre-waiver). §4 explains the discrepancy (post-waiver capture). Recommend one-line clarification in §1 or in the ABS-192 Tier-1 records. Does not affect any AC or the GO verdict.

---

## QAS Verdict

**APPROVED.**

All five acceptance criteria met. Scope respected. ADR-A-0017 correctly cited. The GO verdict is well-evidenced: the JSON shape maps cleanly to per-rule PASS/FAIL, the exit code gives the gate boolean, and the full digest posts through `$TRACKER_CMD` without MCP or LLM. One non-blocking nit on evidence labeling, inherited from ARCH Stage 1 review. Advance to Done.

Iteration 2 of 3 (no bounce; ARCH was Iteration 1).
