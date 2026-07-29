# ABS-223 — Skill-Trigger-Audit

**Question:** Why do seats barely load available skills (be-developer measured at
~0.5 skill-calls/seat), although the pattern-discovery ritual is mandatory?

**Corpus:** 98 role-identified orchestrator seat transcripts from
`~/.claude/projects/*tmp-ABS-*-work/*.jsonl` (106 seat transcripts, 98 with an
extractable `role:` in the spawn packet). Skill invocations detected as
`tool_use name=="Skill"`; the extractor script is `tmp/audit.py` in the work tree.

---

## AC1 — Measurement over the transcripts

### Skill-load rate per role (98 seats)

| role             | seats | skill-calls | calls/seat | seats w/ ≥1 skill |
|------------------|------:|------------:|-----------:|------------------:|
| be-developer     | 58    | 10          | **0.17**   | 7                 |
| qas              | 21    | 18          | 0.86       | 13                |
| system-architect | 17    | 4           | 0.24       | 2                 |
| bsa              | 2     | 0           | 0.00       | 0                 |

Skills actually invoked (all roles): `testing-patterns` 9, `pattern-discovery` 7,
`code-review` 4, `simplify` 4, `ponytail` 2, `verify` 2, `jira-sop` 2,
`safe-workflow` 1, `duplicate-detection` 1. **`stop-slop`: 0 across all 98 seats.**

### What the be-developer seats actually work on

Files edited/written across the substantive be-developer seats:

| count | bucket                    |
|------:|---------------------------|
| 104   | `scripts/*.sh` (HARNESS)  |
| 58    | agent-defs `*.md` (HARNESS) |
| 4     | `statuses.yaml`           |
| 1     | `docs/*.md`               |
| **0** | `patterns_library/` (PRODUCT) |
| **0** | app-source `.ts/.tsx/.prisma` (PRODUCT) |

Every measured be-developer seat did **boilerplate self-hosting work** (orchestrator
scripts, agent charters, status machine). None touched a product API route, RLS
code, or a `patterns_library/` file.

### Sample: skill "due vs. loaded" (18 be-developer seats, >40 transcript entries)

For each seat, an *applicable* skill was counted DUE when the seat made a change
(`verify`/`simplify`/`stop-slop`, the seat-mapped process skills) or touched product
source (`pattern-discovery`).

- `pattern-discovery` DUE: **0 / 18** seats — none touched product source.
- Process-skill applicable-DUE = 48, LOADED = 6 → **hit-rate 12 %** (18-seat sample).

Widening to all 49 substantive be-developer seats (>20 entries), 38 of which made a
change (so `stop-slop`/`verify`/`simplify` were due):

- `stop-slop` LOADED **0 / 38** due.
- `verify` LOADED 2 / 38 due; `simplify` LOADED 4 / 38 due.

(Both tables reproducible via `tmp/audit.py`.)

---

## Root cause — hypotheses verdicts

The observed rate has **two independent layers**:

**Layer 1 — corpus/domain mismatch (dominant, explains most of the "missing" calls;
this is H1 in its strongest form).** The skill catalog is overwhelmingly
product-feature-scoped: `pattern-discovery`, `api-patterns`, `rls-patterns`,
`testing-patterns`, `stripe-patterns`, `frontend-patterns` trigger on "creating API
routes", "Prisma/database code", "payment flows", "UI components". The measured
be-developer seats build the **harness itself** (bash scripts, agent markdown,
orchestrator logic). The model *correctly* declines skills whose descriptions do not
match the task. So a large fraction of the "0.17 calls/seat" is **not a defect** —
it is a skill correctly judged inapplicable. The raw metric conflates
*inapplicable-not-loaded* with *should-have-loaded-but-didn't*.

**Layer 2 — genuine trigger defect for the universal process skills (H2 confirmed).**
`stop-slop`, `verify`, `simplify` are mapped to *every* seat and apply regardless of
domain, yet they fire at 0 %, 5 %, 11 % of due. Cause: in the charter they live in a
passive appendix ("Built-in skills for this seat") placed *after* the Exit Protocol.
At the actual decision point — the Exit Protocol's "Before reporting completion"
checklist — nothing instructs the seat to invoke them. The skill is named, but not
**at the decision point**, so it is reliably skipped.

| Hypothesis | Verdict |
|---|---|
| H1 descriptions don't match seat language | **CONFIRMED (dominant).** Product-domain descriptions vs. harness-engineering seats. |
| H2 packet/charter doesn't name skills at the decision point | **CONFIRMED.** Process skills sit in an appendix after the Exit Protocol, not inside it. |
| H3 seats in worktrees see a different skill set (provisioning) | **REJECTED.** 45/58 be-developer seats were shown the skill menu; skills were visible, just not triggered. |
| H4 skill call costs turns, seats optimize it away | **NOT SUPPORTED as primary cause.** Seats spend 15–71 Bash calls each; a single Skill call is not the bottleneck. Secondary at most. |

---

## AC3 — Linkage to ABS-168 (pattern-discovery fork redirect)

ABS-168 (Done) redirected the mandatory pattern-discovery ritual onto the fork skill.
**The fix landed and is intact:** `CLAUDE.md:120` now reads "invoke the
`pattern-discovery` skill (isolated Explore fork) … never bulk-read
`patterns_library/` or `docs/`", and the be-developer Context Sequence references the
skill. **Does it "greift" (take effect)?** It changed *how* pattern discovery is
procured (fork vs. main-context bulk-read), not *whether* the seat's task triggers it.
Because the measured corpus is harness work with **0** product-source touches,
pattern-discovery was legitimately never due — so the low be-developer rate is **not**
evidence that ABS-168 failed. ABS-168's benefit is realized on product-feature seats,
which this self-hosting corpus does not contain. No regression to ABS-168 found.

---

## AC2 — Fix (minimal-change, no new mechanism)

**Applied diff (this ticket):** `harness/claude/agents/be-developer.md` — the
seat-mapped process skills are wired into the Exit Protocol as an explicit **step 3
"Skill Gates"** (invoke `verify` / `simplify` / `stop-slop`), between the AC/DoD
checklist and the Handoff Statement. This moves them from a passive tail-appendix to
the decision point where the seat decides to hand off. No new mechanism: the skills
already exist and are already mapped to the seat; only the trigger *location* changes.

The live `.claude/agents/be-developer.md` twin is a governor-synced artifact and is
byte-identical to the `harness/claude/` source at a tag (ABS-96); it reconciles at the
next governor promotion. Direct edits to `.claude/` are blocked in the headless
`dontAsk` seat (ABS-168 constraint), so this seat commits the authoritative source
only.

**Recommendations for architect ratification (NOT applied here — broader blast radius):**

1. **Generalize the Exit-Protocol "Skill Gates" step to the other implementer/review
   charters** (fe-developer, data-engineer, qas, system-architect …), or hoist the
   process-skill trigger into `_common-rules.md` (the DRY home for cross-seat rules,
   ABS-174) so it lands on every seat exactly once. Left to the System Architect
   because it changes every seat.
2. **Fix the metric, not just the trigger (Miner, ABS-218):** the skill-mining report
   should split "skill applicable but not loaded" from "skill inapplicable", e.g. by
   scoping product-domain skills to seats that touch `patterns_library/` or app-source.
   Otherwise harness-work seats permanently depress the average and hide Layer 2.

---

## AC4 — Success metric

**Metric:** process-skill hit-rate on *applicable-DUE* occasions per seat, from the
Miner report, split by the Layer-1/Layer-2 buckets above.

- **Baseline (this audit):** `stop-slop` 0/38 DUE; combined process-skill hit-rate
  12 % (6/48) over the 18-seat sample; `stop-slop` 0/98 all seats.
- **Target next run:** with the Exit-Protocol Skill-Gates step live, `stop-slop`
  invocations on be-developer handoff seats should rise from 0 toward ~1/seat, and the
  process-skill hit-rate should rise measurably. Verified by re-running `tmp/audit.py`
  (or the ABS-218 Miner) over the next run's transcripts.
