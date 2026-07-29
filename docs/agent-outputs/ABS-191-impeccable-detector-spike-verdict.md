# ABS-191 Spike — impeccable detector as qas-design gate evidence

**Verdict: GO (with caveats).** The `impeccable detect --json` output maps cleanly
to per-rule PASS/FAIL evidence that a `Bash`-only `qas-design` seat can post via
`$TRACKER_CMD`. The caveats below are design constraints for the Tier-1 story
(ABS-192), not blockers.

- **Ticket:** ABS-191 (spike, verdict-only; parent ABS-190)
- **Governing ADR:** ADR-A-0017 (proposed)
- **Date run:** 2026-07-10
- **Scope honored:** read-only investigation. No adapter/gate/hook/profile wiring,
  no vendoring/commit of the dependency. This document + raw JSON are the only
  artifacts.

---

## 1. What was run (AC: detector run + JSON captured)

The boilerplate repo contains **zero real FE files** (`git ls-files` for
`*.tsx/*.jsx/*.css/*.scss/*.html/*.vue/*.svelte` → 0), so per ticket scope
("…or a representative fixture") I used fixtures that reproduce the AI-design-tell
classes the ADR names (homogeneous fonts, gray-on-color, purple→blue gradient,
sub-44px targets).

Install was done in a scratch dir outside the repo (`/tmp/impeccable-spike`), not
in the governed tree.

| Fixture | Mode | Result | Exit |
|---|---|---|---|
| `bad.html` (AI tells) | static HTML/CSS | **7 findings** across 4 rules — fires | `2` |
| `good.html` (accessible, distinct type) | static HTML/CSS | `[]` — stays quiet | `0` |
| `styles.css` (Inter + gradient) | regex/text | only `overused-font` (line 1) | `2`* |
| `Button.tsx` (inline-style object, same tells) | regex/text | `[]` — **missed everything** | `0` |

\* `styles.css` returns `[]`/exit `0` once a project config waives `overused-font`
(see §4), demonstrating live waiver application.

**Test-plan coverage:** ≥1 known-bad (fires), ≥1 known-good (quiet), ≥1
representative source file — all executed. Raw JSON in
`docs/agent-outputs/ABS-191-evidence/` mirror (see §7).

### JSON shape (from `bad.html`)

```json
{
  "antipattern": "low-contrast",
  "name": "Low contrast text",
  "description": "Text does not meet WCAG AA contrast requirements ...",
  "severity": "warning",
  "file": "/private/tmp/impeccable-spike/fixtures/bad.html",
  "line": 0,
  "snippet": "2.0:1 (need 4.5:1) — text #9ca3af on #2563eb"
}
```

Top-level output is a **flat JSON array of finding objects**. Stable keys:
`antipattern` (rule id), `name`, `description`, `severity`, `file`, `line`,
`snippet`.

---

## 2. Evidence-mapping sketch (AC: rule → PASS/FAIL → tracker comment)

The gate is a pure Bash transform over the JSON. A rule **PASSES by absence** and
**FAILS by presence** of ≥1 finding — there is no explicit "rules passed" list, so
the seat derives PASS from the scanned rule set minus the fired set.

```bash
# qas-design gate skeleton (Tier-1 shape, illustrative — not wired here)
OUT="$(impeccable detect --json "$CHANGE_REF")"; RC=$?
# RC: 0 = clean, 2 = findings present  -> gate signal
echo "$OUT" | jq -r '
  group_by(.antipattern)[]
  | "FAIL " + .[0].antipattern + " (" + (length|tostring) + "×): "
    + ([.[].snippet] | unique | join(" | "))'
# absent rules = PASS; post the digest via the handed adapter:
"$TRACKER_CMD" comment "$TICKET" --kind gate-results --actor qas-design \
  --body "design-system-check (impeccable@<pin>): $VERDICT
$PER_RULE_LINES"
```

Mapping is clean:
- **Rule id → PASS/FAIL:** `antipattern` is the stable id; group by it, presence = FAIL.
- **FAIL → evidence:** `snippet` + `description` are human-readable, one line per rule.
- **Overall verdict:** exit code (`0` PASS / `2` FAIL) is a reliable Bash gate signal;
  no JSON parse needed for the boolean, only for the digest.
- **Adapter fit:** the digest is plain markdown text → posts directly through
  `$TRACKER_CMD ... --kind gate-results` (ADR-A-0007), no MCP, no LLM call. This is
  exactly the `qas-design` headless contract (`.claude/agents/qas-design.md` §Evidence).

**Handling notes for Tier-1 (not blockers):**
- **Duplicate findings** — the same rule/snippet repeats (gray-on-color ×2,
  low-contrast ×3 on one file). Dedup with `unique` before posting.
- **`line: 0` for HTML** — the static-HTML path reports `line: 0`; the regex/text
  path reports real line numbers (`styles.css` → line 1). Evidence should lean on
  `snippet`, not `line`, for HTML inputs.
- **`severity` is `"warning"`** for the tell rules observed — Tier-1 must decide the
  FAIL threshold (any finding vs. error-only). Exit `2` already fires on warnings.

---

## 3. Coverage finding (de-risking — the key caveat)

Detection strength is **file-type dependent**:

- **HTML / live URL** → full static/DOM analysis: computed contrast, gray-on-color,
  palette, fonts. Strongest, most valuable rules. URL mode needs Puppeteer/Chromium
  (see §5).
- **CSS / JSX / TSX (raw source)** → regex/text engine only, referencing ~17 of the
  46 rules; **DOM-composition rules (contrast, gray-on-color) do not reliably fire**
  because they need rendered color composition. `styles.css` caught only
  `overused-font`; `Button.tsx` with an inline `style={{…}}` object (camelCase JS
  keys) matched **nothing**.

**Implication for Tier-1:** for a React/Next.js codebase, running the detector
against raw `.tsx` source yields weak/misleading results. To get the high-value
rules the gate should run against **rendered HTML output or a running URL**
(Playwright is already mandated for UI QA per the design-system adapter — the URL
path aligns with that), or accept that source-file scanning covers only the
font/keyword-class subset. This shapes *what* `change_ref` the gate feeds the
detector; it does **not** affect the JSON→evidence mapping.

---

## 4. Waiver system (AC-adjacent: monorepo sanity check) — PASS

Three independent, working mechanisms, verified:

1. **Project config** `.impeccable/config.json` → `detector.ignoreRules`,
   `detector.ignoreFiles` (globs), `detector.ignoreValues`. Verified: `ignoreRules:
   ["overused-font"]` suppressed that rule live (fired set dropped from 4 rules to 3).
2. **Inline comments** `impeccable-disable` / `-line` / `-next-line <rule> -- reason`
   travel with the file. Verified: `impeccable-disable-next-line overused-font` →
   `styles`-style CSS returned `[]`.
3. **CLI** `impeccable ignores add-rule|add-file|add-value` with `--shared`
   (`config.json`) vs `--local` (`config.local.json`) scope, `--file <glob>`
   scoping, and `--reason`.

**Monorepo fit:** file globs (`packages/vendor/**`, `**/legacy/**`) and the
shared-vs-local config split map directly onto a monorepo layout — committed
baseline waivers in `config.json`, developer-local overrides in
`config.local.json`. Minor: `ignoreValues: ["#9ca3af"]` did not visibly suppress the
gray-on-color/low-contrast findings in my run (value-format/pairing may differ);
Tier-1 should prefer rule/file waivers and validate value-waivers if needed.

---

## 5. False-positive assessment for our design system — documented

- **Neutral profile / backend stacks:** N/A — the gate is profile-gated on
  `config.design_system.enabled: true` (ADR-A-0017 constraint 3). Nothing runs, so
  no false positives there.
- **Design-system-aware rules** (`design-system-color/font/font-size/radius`) only
  fire when a local `DESIGN.md`/`.impeccable/design.json` is present — they are
  inert until a design contract exists, so they cannot false-positive on a repo
  without one.
- **Text/content rules are the real FP risk.** Several of the 46 rules judge *copy*,
  not layout: `marketing-buzzword`, `em-dash-overuse`, `theater-slop-phrase`,
  `aphoristic-cadence`, `all-caps-body`, `numbered-section-markers`,
  `repeated-section-kickers`. Verified FP: legitimate marketing prose
  ("…leveraging cutting-edge technology") tripped `marketing-buzzword`. On real
  product copy these will produce noise.
  - **Mitigation:** run the gate with `--scope` limited to layout/type domains, or
    waive the content-rule class via `ignoreRules`, so the design gate judges design,
    not prose. (`--scope type` filtering exists but behaved narrowly in my run —
    Tier-1 should confirm the exact scope taxonomy.)
- **Overall FP posture:** the DOM rules (contrast, gray-on-color, palette, fonts)
  were accurate on the fixtures — no false positives on `good.html`. The tell-class
  rules for *text* are the ones to fence off. Acceptable with waiver/scope config.

---

## 6. Vendoring pin + Apache-2.0 attribution (AC) 

- **Pin:** `impeccable@3.2.1` (latest; published 2026-07-09).
  - `dist.shasum`: `22d097c515239f27856fd405653491f594fd1708`
  - `dist.integrity`: `sha512-Lnh8BeLNj493iYuKRijVLP5nvdeKvReYtqGeov6tfsqECiKDSHBY5JfkxzfsC912AASMreCwzha0ZY3PC2pw+g==`
  - repo: `git+https://github.com/pbakaus/impeccable.git`
- **Runtime deps (all pure-JS, no native/LLM):** `css-select`, `css-tree`,
  `domutils`, `fflate`, `htmlparser2`, `marked`. Confirms the ADR's "no LLM/API
  call" claim.
- **Puppeteer is an `optionalDependency`**, needed **only for URL scanning**. For a
  file/dir gate, vendor with `--omit=optional` to avoid the ~Chromium download
  (its postinstall was auto-blocked by npm here anyway). This materially shrinks the
  vendored payload — a point in favor of the file/HTML path over URL scanning.
- **Attribution:** license is Apache-2.0 (author Paul Bakaus, homepage
  impeccable.style). The package bundles a `LICENSE` but **no `NOTICE`** file, so
  Apache §4(d) NOTICE-propagation does not apply. Requirement for vendoring: retain
  the upstream `LICENSE` in the vendored payload and add an attribution line to the
  repo's `NOTICE` (as ADR-A-0017 constraint 2 already directs).

---

## 7. Verdict summary

**GO** on the spike's central question: impeccable's `--json` output is a clean,
deterministic, LLM-free evidence source that a `Bash`-only `qas-design` seat can
transform into per-rule PASS/FAIL and post via `$TRACKER_CMD`. Exit code gives the
gate boolean; the findings array gives the per-rule digest.

**No blockers.** The following are **Tier-1 (ABS-192) design constraints**, carried
forward, not reasons to re-scope or close ABS-190:

1. Feed the detector **rendered HTML or a live URL** (not raw `.tsx`) to exercise
   the high-value DOM rules; align with the already-mandated Playwright UI QA.
2. Vendor with `--omit=optional` (skip Puppeteer) if the gate scans files/HTML.
3. Waive/scope the **text-content rule class** so the design gate judges design, not
   prose (verified FP: `marketing-buzzword`).
4. Dedup findings and rely on `snippet` (not `line`) for HTML inputs.
5. Decide the FAIL threshold (any warning vs. error-only).
6. Pin `impeccable@3.2.1` (shasum/integrity above); retain `LICENSE`, add `NOTICE`
   attribution.

This verdict gates ABS-192 and informs POPM acceptance of ADR-A-0017.
