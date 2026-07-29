# Feature Guide: Agent-Def Draft-Path Hygiene (ABS-268)

**Story**: ABS-268 — Agent-Def-Hygiene: residualer `/tmp` + inline-`--body` sweep
(ABS-253-Restklasse) + mechanischer Lint-Guard

**Files changed**: `harness/claude/skills/tracker-ops/SKILL.md`,
`harness/claude/agents/` (14 agent defs + skills swept),
`agent_providers/claude_code/prompts/` (regenerated),
`tests/test-agent-def-lint.sh` (new guard)

---

## Overview

A tracker call that drafts its body into `/tmp/` with the **Write/Edit tool**, or
passes its body **inline** (`--body "…"`), silently fails under `--permission-mode
dontAsk`. The comment or transition never lands. No error is surfaced; the seat moves
on and the evidence is lost.

ABS-253 fixed this class in three implementer defs. ABS-268 found it had recurred in
four more places **and** in the doctrine source (`tracker-ops/SKILL.md`) that seats
read before acting. This story:

1. corrects the contradictory doctrine in `tracker-ops/SKILL.md`,
2. sweeps the class across all 14 affected agent defs and skills,
3. adds a lint guard (`tests/test-agent-def-lint.sh`) that makes the class
   mechanically unrepeatable.

---

## The defect class, precisely

Two distinct violations cause the same silent failure:

### Rule A — inline `--body` / `--reason` on a tracker call

```bash
# WRONG — a literal < or > in the value is shell redirection under dontAsk:
"$TRACKER_CMD" comment ABS-123 --kind gate-results --actor be-developer \
  --body "<gate-results here>"
```

Under `--permission-mode dontAsk`, the shell parses `<` and `>` as
input/output redirection, not as literal characters. The adapter call is
**denied** (ABS-163). Use `--body-file` instead:

```bash
# CORRECT:
mkdir -p work/scratch
printf '%s\n' "gate-results here" > work/scratch/abs123-gate.md
"$TRACKER_CMD" comment ABS-123 --kind gate-results --actor be-developer \
  --body-file work/scratch/abs123-gate.md
```

### Rule B — body/reason draft written to `/tmp/` or `$(mktemp)` with the Write tool

```bash
# WRONG — Write tool is denied outside the allowlist:
BODY_FILE="$(mktemp)"
# …seat uses the Write tool to draft into $BODY_FILE…
# The Write is denied; the file never exists; --body-file hard-fails.
```

The `Write`/`Edit` tool allowlist grants **only** `work/scratch/` (see
`.claude/settings.template.json`). A seat trying to write into `/tmp/…` or into a
path returned by a bare `$(mktemp)` is denied under `dontAsk`. The body draft never
appears, and the subsequent `--body-file` reference hard-fails — the comment or
transition silently never lands.

**Bash redirection** (`printf … > path`) is different: it runs inside the Bash tool,
not the Write grant, so `/tmp/…` genuinely works for Bash-authored files. It is still
not the default: use `work/scratch/` regardless of the drafting tool so one habit is
correct under both.

---

## The correct pattern for every seat

```bash
# 1. Create the scratch directory (idempotent):
mkdir -p work/scratch

# 2. Draft the body — use the Write tool or Bash redirection:
#    Both land in work/scratch/, which is allowlisted and gitignored.
printf '%s\n' "Your evidence here." > work/scratch/abs123-gate.md

# 3. Pass to the adapter via --body-file:
"$TRACKER_CMD" comment ABS-123 --kind gate-results --actor be-developer \
  --body-file work/scratch/abs123-gate.md

# Same pattern for transitions:
printf '%s\n' "Transition reason." > work/scratch/abs123-reason.md
"$TRACKER_CMD" transition ABS-123 "Done" --actor be-developer \
  --reason-file work/scratch/abs123-reason.md --expect-from "In Progress"
```

`work/scratch/` is listed in `.gitignore` (`work/scratch/`), so draft files never
get committed accidentally.

---

## What changed

### 1. `tracker-ops/SKILL.md` — doctrine corrected

Before ABS-268, the skill contained:

> "`--body-file` / `--reason-file` read from a path, so the file must exist;
> **`/tmp/…` in the sandbox is fine.**"

This sentence is true for Bash redirection and false for the Write tool. Because
`tracker-ops` is the first skill seats load before posting to the tracker, this
unqualified claim was the **root cause** of the class recurring across three epic
cycles.

The skill now draws the Bash-vs-Write distinction explicitly (lines 121–134) and
names `work/scratch/` as the default. All examples (lines 64–65, 81–82, 153–154)
draft to `work/scratch/`.

### 2. 14 agent defs and skills swept

The following files carried Rule A or Rule B violations and were corrected:

| File | Violations fixed |
| ---- | ---------------- |
| `harness/claude/agents/qas-design.md` | `/tmp` evidence draft; inline `--body` with literal `<`/`>`; placeholder `<design test report>` |
| `harness/claude/agents/bsa.md` | Two `$(mktemp)` body drafts; inline `--body`/`--reason` |
| `harness/claude/skills/issue-enrichment/SKILL.md` | Append-flow drafted to `/tmp`; `$(mktemp)` body draft |
| `harness/claude/agents/qas.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/agents/rte.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/agents/tdm.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/agents/security-engineer.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/agents/self-improvement.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/agents/system-architect.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/agents/tech-writer.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/agents/ui-ux-design.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/agents/data-provisioning-eng.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/skills/docs-station/SKILL.md` | Inline `--body`/`--reason` on tracker calls |
| `harness/claude/skills/duplicate-detection/SKILL.md` | Inline `--body`/`--reason` on tracker calls |

The ABS-253 precedent defs (`be-developer`, `fe-developer`, `architect`) were already
clean and were not modified.

`agent_providers/claude_code/prompts/` was regenerated from `harness/claude/` via
`scripts/generate-governor.sh --providers`. `.claude/` is generated(pin) at v2.25.1
under the ABS-94 governor-pin model and picks the fix up at the next promotion
(ABS-95); it was correctly left untouched.

### 3. `tests/test-agent-def-lint.sh` — new guard (7 tests)

```
=== agent-def lint: draft-path + inline-body guard (ABS-268) ===
  PASS guard FAILS on the pre-fix content (regression proof)
  PASS   detects RULE-A: inline --body on a tracker call
  PASS   detects RULE-B: draft redirected into /tmp
  PASS   detects RULE-B: body draft in a bare $(mktemp)
  PASS   detects an inline flag on a backslash-CONTINUED tracker call
  PASS no false positives on the sanctioned forms
  PASS harness/claude agents + skills are clean
Results: Total: 7  Passed: 7  Failed: 0
```

The guard covers `harness/claude/agents/*.md` and `harness/claude/skills/**/*.md`.
It auto-registers via the `tests/test-*.sh` glob in `tests.yml`.

**Regression proof**: the guard was run against a `git archive` of the pre-fix tree
and flagged every line named in the ticket, plus the 11 siblings. Fixtures contain
verbatim defective lines — not synthetic approximations — so the proof is real.

**False-positive guards** ensure the guard does not flag:
- `gh pr create --body "…"` — a GitHub CLI call, not a tracker adapter call
- Prose that *explains* `/tmp` or `$(mktemp)` (the rule text itself)
- `mktemp -d` sandbox directories used for test isolation (not body drafts)
- `harness/claude/skills/spec-creation/SKILL.md` — its `$(mktemp)` snippet drafts
  via Bash redirection in an executed-AC simulation; that path genuinely works under
  `dontAsk` (ABS-268 anti-overreach note)

---

## Acceptance criteria (verified)

| AC | Result |
| -- | ------ |
| AC1: no inline `--body`/`--reason` on tracker calls in `harness/` | PASS — 1 hit: `release-patterns/SKILL.md:81` (`gh pr create`), not a tracker call |
| AC2: no `/tmp` redirects or `$(mktemp)` in qas-design, bsa, issue-enrichment | PASS — 0 hits; all recipes carry `mkdir -p work/scratch` |
| AC3: `tracker-ops/SKILL.md` draws Write/Edit vs Bash distinction; unqualified `/tmp` sentence gone | PASS |
| AC4: `tests/test-agent-def-lint.sh` exists, 7/7, proven to fail on pre-fix tree | PASS |
| AC5: `test-harness-parity.sh` green (corrected premise: `.claude/` is generated(pin)) | PASS — 6/6; `--providers --check` OK |
| AC6: `spec-creation/SKILL.md:194` unchanged (anti-overreach) | PASS — byte-identical |

---

## Troubleshooting

### Symptom: tracker comment or transition posted but never appears on the ticket

**Likely cause**: seat drafted the body into `/tmp/` with the Write tool, or passed
`--body` inline with `<`/`>` characters.

**Diagnosis**:

```bash
# Check the seat definition for the defect class:
grep -n '\-\-body "' harness/claude/agents/<seat>.md
grep -n '/tmp/' harness/claude/agents/<seat>.md
grep -n '$(mktemp)' harness/claude/agents/<seat>.md
```

**Fix**: route the draft through `work/scratch/` and pass `--body-file`.

### Symptom: `tests/test-agent-def-lint.sh` FAILS after editing an agent def

**Cause**: the edit introduced an inline `--body`/`--reason` or a `/tmp`/`$(mktemp)`
draft on a tracker call.

**Fix**: replace the inline body with a `--body-file` form and draft to
`work/scratch/`. The test output names the exact file and line.

### Symptom: guard incorrectly flags a legitimate `/tmp` use

The guard matches the redirect/assignment form, not the bare string `/tmp`. Pure prose
that says "do not use `/tmp`" is not flagged. If you believe the flag is a false
positive, check whether the match is on an *assignment* (`BODY_FILE=/tmp/…`) or
*redirect* (`> /tmp/…`) form. If it is, the draft path should move to `work/scratch/`.

---

## Related

- `harness/claude/skills/tracker-ops/SKILL.md` — canonical tracker CLI quick reference
  (now contains the corrected Write/Edit vs Bash doctrine)
- `tests/test-agent-def-lint.sh` — the lint guard (7 tests)
- `docs/guides/JIRA_TRACKER_ATFILE_WRITE_PATH_GUIDE.md` — the write-path argv fix
  (ABS-263); a complementary guard on the adapter side
- ABS-253 (Done) — the three implementer-def fixes that established the pattern this
  story generalises
- ABS-163 — inline `--body`/`--reason` shell-redirection denial; root of Rule A
- `.claude/settings.template.json` — the `Write|Edit` allowlist (grants `work/scratch/`)
- `.gitignore` line 164 — `work/scratch/` gitignore entry
