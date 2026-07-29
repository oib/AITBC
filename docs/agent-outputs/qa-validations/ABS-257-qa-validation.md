# QA Validation — ABS-257: Stack-Applicability-Guard

**Branch:** `ABS-257-auto` | **Commits:** `96108fd` (initial) + `d54b62a` (worktree fix)
**QAS run:** 2026-07-13 | **Verdict:** APPROVED

---

## AC1 — Applicability-Taxonomie definiert

**Result: PASS**

`patterns_library/README.md` documents the 9-tag closed vocabulary with a table:
`generic`, `nextjs`, `react`, `clerk`, `prisma`, `postgres-rls`, `stripe`, `github-actions`, `playwright`.

Test evidence:
- `test-pattern-applicability.sh` case 1: all 24 `patterns_library/**/*.md` carry `stack:` frontmatter — **PASS**
- `test-pattern-applicability.sh` case 2: every tag in use falls inside the documented taxonomy — **PASS**

Spot-checked manually:
- `patterns_library/api/user-context-api.md` → `stack: [nextjs, clerk, prisma, postgres-rls]`
- `patterns_library/config/structured-logging.md` → `stack: [generic]`
- `patterns_library/database/prisma-transaction.md` → `stack: [prisma]`
- `patterns_library/ui/authenticated-page.md` → `stack: [nextjs, react, clerk, prisma]`

---

## AC2 — pattern-discovery filtert nach Profil; generische Patterns bleiben sichtbar

**Result: PASS**

`scripts/pattern-applicability.sh` reads the active profile's `stack:` list and applies the
APPLICABLE/EXCLUDED classification. `harness/claude/skills/pattern-discovery/SKILL.md` line 40:
"Step 0: Stack-Applicability-Guard (MANDATORY FIRST)" calls `scripts/pattern-applicability.sh`
before any recommendation. `allowed-tools: Read, Grep, Glob, Bash` on line 6 grants the necessary
runtime access.

Live output counts (verified in this QAS run):

| Profile | `stack:` key | Applicable patterns |
|---------|-------------|-------------------|
| `neutral` | absent | 24/24 (unfiltered, back-compat) |
| `saw-stack` | `[nextjs, react, clerk, prisma, postgres-rls, stripe, github-actions, playwright]` | 24/24 |
| `jira-github-postgres` | `[github-actions]` | 12/24 |

For `jira-github-postgres`: 12 excluded patterns are all tagged with `nextjs`, `prisma`,
`postgres-rls`, `playwright`, or `react` — none of which appear in `[github-actions]`. All 12
`generic`-tagged and `github-actions`-tagged patterns survive. Filtering is correct.

Generic patterns always visible in the FastAPI output: `config/structured-logging.md`,
`security/input-sanitization.md`, `config/environment-config.md` — all confirmed present.

Test cases: 8 of the 22 cases directly exercise AC2 (filter by profile, generic visibility, block-form
stack: parsing, empty stack `[]` behaviour) — all PASS.

---

## AC3 — FastAPI-Profil bekommt keine Next.js-Empfehlung

**Result: PASS** (on the production activation path, not just the env-var seam)

This is the AC the architect bounced Iteration 1 over. The original test activated the profile via
`ACTIVE_PROFILE=fastapi-firestore bash "$GUARD"` — an env seam production never sets. Seats run
in git worktrees where `.active-profile` (gitignored) cannot exist, and the spawn seam does not
export `ACTIVE_PROFILE`. The original AC3 was green through a door the runtime never opens.

The fix in `d54b62a`: `get_active_profile()` in `scripts/lib/profile.sh` now resolves
`env > local .active-profile > MAIN CHECKOUT's .active-profile > neutral`. The main checkout is
located via `git -C "$REPO_ROOT" rev-parse --git-common-dir`. Relative paths from `rev-parse`
are re-anchored to `REPO_ROOT` explicitly — the implementation detail the architect flagged.

The new AC3 case in the test (lines 179–239) builds the real topology:

1. Own sandbox git repo with no `.active-profile` checked in (untracked, gitignored by analogy)
2. `fastapi-firestore` profile written to `profiles/fastapi-firestore/profile.yaml` in the main
   checkout, `.active-profile` written there too
3. `git worktree add` creates a linked worktree
4. Guard invoked from the worktree with `env -u ACTIVE_PROFILE` and `cwd=/`

Output: `config/structured-logging.md` present, `api/user-context-api.md` absent — **PASS**.
Back-compat case (no `.active-profile` anywhere): all patterns visible — **PASS**.

The architect independently mutation-checked the test (restoring `96108fd`'s `scripts/lib/profile.sh`
turns the case RED at 21/22). I read the test code and verified the topology matches the description.

---

## Additional checks

### Empty stack `[]` fix (defect caught by developer in verify)

`profile_declares_stack()` now distinguishes key-absent (filtering off, back-compat) from
key-present-but-empty (filtering on, only generic applies). Test case confirms `stack: []` gives
only `config/structured-logging.md`, not `api/user-context-api.md` — **PASS**.

### Non-blocking notes (both taken)

- `read_stack_list` scan bounded to frontmatter block (`NR==1 /^---$/` .. closing `---`): a
  `stack:` line in prose or fenced code can no longer be misread. Verified in `pattern-applicability.sh`
  lines 65–89.
- `--all` EXCLUDED branch uses `${tags:-untagged}` fallback. Verified in `pattern-applicability.sh`
  line 155.

### Migration reach

`scripts/pattern-applicability.sh` registered in `.agentic/upgrade/ownership.yaml` — confirmed
present in the file.

### Harness parity

Only `harness/claude/skills/pattern-discovery/SKILL.md` edited; `.claude/` left generated (pin).
`test-harness-parity` confirms — PASS.

---

## Test suite results (run by this QAS seat)

| Suite | Result |
|-------|--------|
| `tests/test-pattern-applicability.sh` | **22/22 PASS** |
| `tests/test-profile-activation.sh` | **17/17 PASS** |
| `tests/test-harness-parity.sh` | **6/6 PASS** |
| `tests/test-hooks-config.sh` | **PASS** |
| `tests/test-migrate-project.sh` | **53/53 PASS** |
| `tests/test-evolver-lifecycle.sh` | **PASS** |
| `shellcheck scripts/lib/profile.sh scripts/pattern-applicability.sh` | **clean (SC1091 info only)** |

---

## Verdict: APPROVED

All three ACs met on the production activation path. The worktree fail-open is closed and covered
by a mutation-verified test. Generic patterns remain visible on every profile. The guard is
registered for consumer migration. No regressions in any of the six suites.

RTE note: consumers who ran `setup-template.sh` will see seats resolve the project's actual profile
(stack filter and capability providers in `evolver-lifecycle.sh`) where they previously resolved
`neutral`. Intended — but call it out in the release notes.
