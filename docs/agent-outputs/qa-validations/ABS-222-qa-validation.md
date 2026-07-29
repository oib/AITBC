# QA Validation Report — ABS-222

**Ticket**: ABS-222 — Skill `tracker-ops`: Adapter-CLI Quick Reference  
**Branch**: ABS-222-auto  
**HEAD**: f9f3b0b (tree clean)  
**QAS run**: 2026-07-12  
**Verdict**: **APPROVED**

---

## Deliverable type

Pure docs/skill deliverable — no runtime, schema, or app code surface. Test suite
commands (yarn test:unit etc.) are N/A. Validation gates: skills-parity check,
harness-parity check, and live smoke execution of every documented op against an
isolated mock-tracker sandbox.

---

## AC Checklist

### AC1 — Skill + apply-copies; description matches "ticket lesen/kommentieren/transitionieren"

**PASS**

- `harness/claude/skills/tracker-ops/SKILL.md` — present, checked
- `harness/claude/skills/tracker-ops/README.md` — present, checked
- `.agents/skills/tracker-ops/SKILL.md` — diff against harness source: IDENTICAL
- `.gemini/skills/tracker-ops/SKILL.md` — diff against harness source: IDENTICAL
- `.gemini/skills/tracker-ops/README.md` — one provider badge line added; parity
  script accepts this (SKILL.md is the functional file; README.md badge is
  provider-local cosmetic)
- Frontmatter `description`: "Use to **read a ticket**, **comment on or attach
  evidence to a ticket**, **transition a ticket's status** …" — covers all three
  DE verbs (lesen / kommentieren / transitionieren)
- README trigger keywords: `ticket lesen | kommentieren | transitionieren` (explicit)
- `check-skills-parity.sh`: **PASS — 24/24 skills in sync** across all three
  provider trees

### AC2 — All examples run against mock-tracker in isolated sandbox

**PASS** — QAS independently re-ran all five ops:

| Op | Command | Result |
|----|---------|--------|
| `get` | `mock-tracker.sh get DEMO-1` | ticket YAML printed, exit 0 |
| `search` | `--status "Backlog" --type ticket` | two rows TAB-separated, exit 0 |
| `comment` | `--kind gate-results --body-file /tmp/c.md` | "comment added", exit 0 |
| `transition` | `"Ready for Development" --expect-from "Backlog"` | status changed, exit 0 |
| `transition NOOP` | stale `--expect-from "Backlog"` after status moved | logged NOOP, exit 0 |
| `link` | `DEMO-1 DEMO-2 parent-child` | linked, exit 0; idempotent re-link also exit 0 |

The `--body-file` redirection-char trap and the `--expect-from` compare-and-set
(both applied and NOOP paths) verified explicitly.

### AC3 — `_common-rules` references skill instead of `help`

**PASS**

`harness/claude/agents/_common-rules.md` §4 (Tracker-Protokoll), lines 49–52:

> For the CLI surface (get / search / comment / transition / link and the
> mandatory `--body-file` / `--expect-from` flags), invoke the `tracker-ops`
> skill — a copy-paste quick reference. **Do NOT run `$TRACKER_CMD help`** to
> relearn the CLI.

### AC4 — help-calls = 0 in next run (Miner-Report)

**DEFERRED BY DESIGN** — post-run miner measurement; cannot be produced at seat
time. The enabling change (skill + `_common-rules` pointer) is confirmed in place.
Prior gates (be-developer, system-architect) documented the same deferral.
Measurement belongs to the next orchestrator run's retro.

---

## Gate results

| Gate | Result |
|------|--------|
| `check-skills-parity.sh` | PASS — 24/24 |
| `tests/test-harness-parity.sh` | 6/6 PASS |
| Five smoke ops (isolated sandbox) | all exit 0 |
| `generate-governor.sh --providers --check` | OK (no provider drift) — confirmed by system-architect; harness-parity already re-runs this |

---

## Findings

No defects. The `.gemini/README.md` provider badge divergence is cosmetic and
accepted by the parity script (SKILL.md is identical). The AC4 deferral is
documented and consistent across all prior gate reviews.

---

## Final verdict

**APPROVED for Story Acceptance.**  
AC1, AC2, AC3: PASS. AC4: deferred by design (next-run miner). All gates green.
