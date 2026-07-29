# Boilerplate Migration Standard Operating Procedure (SOP)

**Purpose**: Define how a consuming project is upgraded to the current boilerplate version by the Boilerplate Migration Agent — versioning scheme, invocation, ownership classification, worked example, and abort/escalation cases

**Version**: 1.7 (ABS-248)
**Last Updated**: 2026-07-14

---

## Overview

The Boilerplate Migration Agent ([`.claude/agents/boilerplate-migration.md`](../../.claude/agents/boilerplate-migration.md)) has exactly one job:
migrate an existing consuming project to the current boilerplate version. It implements the ownership-and-upgrade model of
[`ADR-A-0008`](../../adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md) under the minimal-change discipline of
[`ADR-A-0010`](../../adrs/agentic/ADR-A-0010-minimal-change-default.md); the resulting branch is merged by a human only
([`ADR-A-0005`](../../adrs/agentic/ADR-A-0005-mandatory-prs.md)).

**Mechanical driver (ABS-227).** Since ABS-227 the migration is executed by a **zero-dep bash driver**,
[`scripts/migrate-project.sh`](../../scripts/migrate-project.sh), not by an LLM stepping through this procedure. The
driver performs every mechanical step (version detection + aborts, strict ownership classification, batch hashing, drift
detection, replace/add including the harness surface (§3.3), declared migrations, marker stamp, branch +
commit, and a report whose conflict section already contains `diff -u` hunks). The agent calls the driver ONCE and then
only reads the report's conflict hunks to write human recommendations — mirroring the ABS-164 token-reduction pattern
(procedure prose → script). This SOP is the reference for the model the driver enforces; the sections below describe
*what the driver does*, not a manual runbook.

---

## 1. Versioning Scheme and the `.boilerplate-version` Marker

### 1.1 Scheme

The boilerplate uses **semantic versioning** (`MAJOR.MINOR.PATCH`, starting at `0.1.0`). The boilerplate is versioned from its **first release** — it has never shipped unversioned, so every project created from it carries a version marker from day one. A project without a marker was, by definition, not created from the boilerplate (see section 5).

### 1.2 The Marker File

`.boilerplate-version` at the repository root contains exactly one line — the semantic version, nothing else:

```text
0.1.0
```

The format is deliberately a plain one-line file (trivially readable by scripts and agents: `cat .boilerplate-version`). Because the format supports **no comments**, this SOP section is the marker's documentation of record.

Two roles, same file:

| Location | Meaning |
| -------- | ------- |
| Boilerplate repository root | The **current** boilerplate version — the "to" side of any migration |
| Consuming project root | The **installed** boilerplate version — the "from" side of any migration |

### 1.3 Stamping at Project Setup

**Project setup MUST stamp the marker into every consuming project**: when a new project is created from the boilerplate (see [`TEMPLATE_SETUP.md`](../../TEMPLATE_SETUP.md)), the boilerplate's `.boilerplate-version` is copied to the new project's root unchanged. The migration agent later updates it as the final step of each successful migration.

---

**Upstream source namespace (ABS-96, updated ABS-248).** The boilerplate maintains the
harness's editable source under `harness/claude/` (ADR-A-0016); the live `.claude/` is the
governor-generated, promoted artifact at the path a consumer actually has. This is an upstream
authoring detail: no consumer has a `harness/` directory. From v2.25.2 (ABS-248), `.claude/`
and the five provider-harness domains enter the ownership map (§3.3), so **harness fixes
reach consuming projects through the standard migration path** — no manual `.claude` delta
between releases. `scripts/sync-claude-harness.sh` remains a standalone consumer sync tool
with an unchanged public contract.

## 2. Invocation

The agent **ships with the boilerplate and runs FROM the current boilerplate checkout against a target project**. This resolves the chicken-and-egg problem: an old project carries old agent definitions, so the upgrade logic must always come from the new version.

```text
Human (in a current boilerplate checkout):
  "Run the boilerplate-migration agent against /path/to/consuming-project"
```

The agent then runs the driver once:

```bash
scripts/migrate-project.sh /path/to/consuming-project     # --format json for a machine summary
```

Rules:

- The target project path is a **required, human-supplied parameter**. The agent never self-selects targets and never runs unprompted.
- The target repository must have **no tracked modifications** and **no untracked files on the boilerplate-owned
  surface** before migration starts (the driver aborts otherwise, exit 5, naming the offending paths). Unrelated
  untracked files are tolerated and stay out of the migration commit; `--allow-untracked` additionally forces past
  owned-surface collisions (ABS-277).
- **Windows: `git config --global core.longpaths true` is a prerequisite** — set it before cloning or migrating (see below).
- Never invoke the target project's own (older) copy of the migration agent for an upgrade.
- The driver reads the current version from the boilerplate checkout it runs from (override with `--source <path>`).

### 2.1 Windows Prerequisite: `core.longpaths` (ABS-276)

```bash
git config --global core.longpaths true   # BEFORE cloning the boilerplate or the target
```

Git for Windows uses the ANSI Win32 API unless `core.longpaths` is set, so **any path over 260
chars (MAX_PATH) is silently skipped at checkout**: the clone/checkout reports success, the files
never land on disk, and `git status` afterwards lists them as *deleted*.

Two ways this bites a migration:

1. **The clean-tree gate trips for no visible reason.** Dropped files show up as *deleted tracked*
   files, so gate part 1 (tracked modifications, §2) aborts with exit 5 — though the operator
   changed nothing. Two wrong turns: `--allow-untracked` does **not** clear it (that flag only
   governs untracked files on the owned surface, gate part 2), and the abort's "commit or stash
   them" hint would **commit the deletions**. Restore the files instead (below).
2. **Boilerplate-owned files drop out of the migration.** Classification (§3.1) reads both sides
   from disk. An owned file missing from the **source** checkout lands in `MISSING_SRC_LIST` and is
   skipped, so the target never receives it. Missing from the **target**, it classifies as `ADD`,
   so the driver rewrites it — and the write fails again if the path still exceeds MAX_PATH.

The boilerplate keeps its **own** paths within a 100-char repo-relative budget (enforced by
`tests/test-path-budget.sh`; longest tracked path today is 89 chars). That budget cannot save a
deep clone parent (`C:\Users\...\projects\customer\...`) or the orchestrator's per-ticket worktrees
(`.claude/worktrees/<TICKET>-auto/`, which check the whole tree out a second level down) — together
those can still cross 260. `core.longpaths` is the only fix that covers those.

**Already cloned without it?** Set the config, then materialize the dropped files:

```bash
git config --global core.longpaths true
git checkout -- .        # re-materializes files that were silently skipped
git status --short       # must be clean before the migration driver will run
```

---

## 3. Ownership Classification (per ADR-A-0008)

Before classifying anything, the agent excludes a set of paths that must never be walked.
These paths are either gitignored scratch/build output or byte-identical duplicates that
multiply every enumeration for no gain:

| Path | Why it is excluded |
| ---- | ------------------ |
| `.claude/worktrees/` | Nested repo copies, ~39 MB, gitignored |
| `harness/.claude/` | Byte-identical duplicate of `.claude/` — the harness source-of-truth |
| `node_modules/` | Package install cache |
| `graphify-out/`, `tmp/` | Build and scratch output |

These exclusions apply to **both** the boilerplate source checkout and the target project.
Prefer `git ls-files` / `git grep` (index-scoped, respects `.gitignore`) over recursive
`find` / `grep` / `Glob` so these paths are never traversed.

The agent then classifies every file in the **ownership-mapped set** (not the whole tree):

| Class | What it covers | Migration behavior |
| ----- | -------------- | ------------------ |
| **Boilerplate-owned** | The boilerplate-managed surface — per ADR-A-0008, `.agentic/` fully, plus the `scripts/` runner/tracker-adapter/sync-release tooling (Amendment 2026-07-12, ABS-228), plus the six harness domains `.claude/`, `.gemini/`, `.codex/`, `.cursor/`, `.agents/`, `dark-factory/` (Amendment 2026-07-14, ABS-248, see §3.3) — enumerated by the machine-readable ownership map (`.agentic/upgrade/ownership.yaml`) where present | Hash-compared against the installed version's originals (see section 3.1), then replaced with the current version |
| **Project-owned** | The two managed-surface exceptions `config.yaml` and `overrides/`, any script or harness file a project pins via `project_owned_exceptions` (§3.2, §3.3), plus everything outside the managed surface (application code, project docs, project ADRs, project-added scripts) | Never touched by migration |
| **Special case: `adrs/agentic/ADR-*.md`** | Content is boilerplate-owned; the acceptance frontmatter (`status`, `accepted_by`, `accepted_date`) is project-owned | The driver strips acceptance fields and then token-normalizes (§3.1.1) before hashing, so accepting an ADR and the project's token substitution are both invisible to the drift check; unmodified content is replaced while the target's acceptance frontmatter is preserved (`migrate-project.sh` `strip_acceptance_fields` / `copy_adr_preserving_frontmatter`) |

### 3.1 Hash-First Drift Detection

**The driver (`scripts/migrate-project.sh`) does this mechanically** — the description below is
the model it implements, not a manual runbook. It reads the ownership map STRICTLY (no LLM
tree-classification fallback; a missing `.agentic/upgrade/ownership.yaml` is a deterministic
abort, exit 6) and classifies every owned file by batch hash.

Hash comparison is done in Bash, in **batch**, using `shasum -a 256` — never by reading
file contents into context. Reading the boilerplate-owned tree into the model's context
would ingest it twice (once per side), which is precisely the waste the batch approach
avoids.

**Drift baseline: the target's ORIGINAL installed-version files.** The baseline is each
boilerplate-owned file exactly as it shipped in the `<from>` version — the version recorded
in the target's `.boilerplate-version`. These files are **not** in the current working tree
(which is the `<to>` version, the replacement source). They are materialized from this
checkout's git history at the installed version's release tag (`v<from>`) using `git show`:

```bash
# <from>  = target's installed version (read from TARGET_PROJECT_PATH/.boilerplate-version)
# <path>  = a boilerplate-owned file's path as it existed in the installed version
# Materialize the ORIGINAL installed-version baseline from the v<from> git tag:
original_digest=$(git show "v<from>:<path>" | shasum -a 256 | awk '{print $1}')
# Hash the target project's current copy of the same file:
target_digest=$(shasum -a 256 "<TARGET_PROJECT_PATH>/<path>" | awk '{print $1}')
```

In batch form, materializing originals from the tag before comparing:

```bash
# For each boilerplate-owned path in the ownership-mapped set (exclusions applied):
# Extract pristine originals from the v<from> tag — NOT from the working tree:
git show "v<from>:<path>" | shasum -a 256 >> /tmp/original.sha256  # repeat per file, then sort
( cd "$TARGET_PROJECT_PATH" && shasum -a 256 <same relative paths...> | sort ) > /tmp/target.sha256
diff /tmp/original.sha256 /tmp/target.sha256   # differing lines = drift candidates
```

Comparing against the current checkout instead of the `v<from>` tag would misreport every
legitimate upstream change between `<from>` and `<to>` as local drift, flooding the report
with false CONFLICTs.

Files whose hashes **match** are never read into context. A file is read only when its hash
**differs** and the conflict summary for the migration report requires it.

**Drift** (a locally modified boilerplate-owned file) is *detected, not forbidden-and-forgotten*: it is never silently overwritten — it becomes a conflict listed for human decision. Customizations the `config.yaml`/`overrides/` surface cannot express go back upstream as **consumer-feedback items** (section 6, `.agentic/templates/consumer-feedback-item.md`). Before editing a boilerplate-owned **agent def** into drift, see §3.4 — an additive customization belongs in an overlay, which never conflicts.

### 3.1.1 Setup-Token Normalization (ABS-249)

**The problem.** Consuming projects are setup-instantiated: `setup-template.sh` replaces
boilerplate `{{TOKEN}}` placeholders with project-specific values — `AITBC` becomes
`ACME`, `main` becomes `main`, and so on. The boilerplate source still carries the
literal placeholder strings. Comparing a raw upstream baseline against an instantiated target copy
flags every tokened file as a conflict on every migration, even when the only difference is the
expected substitution. (Evidence: ADR-A-0005, ADR-A-0012, ADR-A-0014 re-conflicted across three
consecutive releases; v2.24.1→v2.25.0 pilot run reported 6 spurious conflicts from 340 files.)

**How the driver resolves it.** Before hashing, the driver runs the upstream side — the `v<from>`
baseline and the `v<to>` replacement source — through the project's substitution map:

- **Substitution map.** Built from the target's `.harness-manifest.yml`: explicit `substitutions:`
  entries (highest precedence), then `identity:` entries, then four tokens derived by
  `setup-template.sh` from those values (`TICKET_PREFIX_LOWER`, `GITHUB_REPO_URL`,
  `AUTHOR_INITIALS`, `HARNESS_VERSION`). The baseline sed script uses `v<from>` for
  `HARNESS_VERSION`; the source sed script uses `v<to>`.
- **CR normalization.** Both streams also have carriage returns stripped (`tr -d '\r'`), applied
  at the same seam as the token substitution.
- **No manifest → graceful degrade.** When the target carries no `.harness-manifest.yml`, the map
  is empty and only CR normalization applies — identical to pre-ABS-249 behavior.

After normalization, a file whose only local change is token substitution produces matching hashes
and is classified `already_current`, not a conflict. A file with genuine local amendments differs
after normalization and still conflicts (negative case verified in `tests/test-migrate-project.sh`).

**Write path.** The same substitution pipeline runs when the driver writes a file into the target
(replace or add path). No literal `{{TOKEN}}` reaches the consumer; conflict hunks diff against
the instantiated incoming file.

**The `setup-template.sh` exclusion — a deliberate invariant.** `setup-template.sh` is the one
boilerplate-owned file excluded from normalization. Its source contains the `{{TOKEN}}` strings as
*data* — elements of the `REPLACEMENT_KEYS` array the wizard uses at project setup (`l.522–553`);
`setup-template.sh:507` also excludes itself from its own sweep for the same reason. Substituting
it would destroy the wizard; comparing it token-normalized would make it a permanent phantom
conflict. The driver mirrors setup's sweep set exactly, including this exclusion. A parity test in
`tests/test-migrate-project.sh` guards the two lists against divergence.

**The invariant.** A boilerplate-owned file that setup sweeps must not carry a literal replacement
key as data. `setup-template.sh` is the single sanctioned exception.

### 3.1.2 Integrity Check of Adopted Copies (ABS-273)

ABS-249 stopped the driver from *creating* this damage. It does not repair a copy already damaged
by the **pre-ABS-249 driver**, which wrote setup-instantiated files into the consumer with their
literal tokens intact and left the consumer to hand-substitute them afterwards (the "Group 3"
caveat of the v2.24.1→v2.25.0 migration report).

**Why the wizard is the dangerous one.** For `scripts/setup-template.sh` that hand-fix is
**inverted**: the wizard stores the tokens as *data* (§3.1.1), so a **healthy copy still contains
them literally**. An instantiated wizard is corrupt twice over — the next `setup-template.sh` run
substitutes the wrong strings (or nothing), and since the driver never substitutes the wizard, the
file conflicts on **every** future migration, forever. "Resolving" that conflict by keeping the
local copy cements the corruption.

**Check it by hand** (from the consuming project's root — no migration needed). Scope the check to
the `REPLACEMENT_KEYS` array and compare its entries against the ones still token-**shaped**. Two
weaker checks each report a corrupt wizard as **healthy**, so do not use them:

- *A whole-file `grep '{{'`.* A corrupt wizard still holds `{{` hits outside the array — the
  wizard's own grep patterns (`'{{[A-Z_]*}}'`) and its `{{PLACEHOLDER}}` doc examples, text no
  consumer `sed` reaches.
- *"Does the array still contain any `{{`?"* Your substitution ran from your manifest's token map,
  which covers a *subset* of the keys, so the damage is usually **partial**: some entries
  instantiated, the rest still literal (e.g. 26 of 30).

For reference, the pristine wizard has 10 such non-array lines and 30 keys inside the array.

```bash
BLOCK=$(sed -n '/^declare -a REPLACEMENT_KEYS=(/,/^)/p' scripts/setup-template.sh)
ENTRIES=$(printf '%s\n' "$BLOCK" | grep -c '^[[:space:]]*"')
TOKENS=$(printf '%s\n' "$BLOCK" | grep -c '^[[:space:]]*"{{[A-Z_]*}}"')
echo "$TOKENS/$ENTRIES replacement keys still literal"
# healthy: TOKENS == ENTRIES (currently 30/30)
# corrupt: any shortfall — 0/30 (fully substituted) or e.g. 26/30 (partially)
```

**Repair.** The wizard is boilerplate-owned and has no legitimate local drift, so the fix is a
restore from upstream — which is exactly what the driver now does for you: a corrupt wizard is
detected, reclassified from `CONFLICT` to `REPLACE`, and restored verbatim from the boilerplate
source. To repair it outside a migration, copy it from a boilerplate checkout:

```bash
cp <boilerplate-checkout>/scripts/setup-template.sh scripts/setup-template.sh
```

**The lower-severity class.** The other files the old driver wrote with literal tokens
(`scripts/promote-release.sh`, `scripts/sync-claude-harness.sh`) *are* substitutable, so the
consumer's hand-substitution was directionally right; the only residual risk is that it was
**incomplete**. The driver reports those as `TOKEN RESIDUE` — take the incoming upstream version
when they also appear under Conflicts — but never rewrites them silently.

Every migration report carries an **`## Integrity Check (adopted copies, ABS-273)`** section: a
clean verdict when nothing is corrupt, otherwise one row per finding with its repair.

### 3.2 The `scripts/` domain (ADR-A-0008 Amendment 2026-07-12, ABS-228)

The orchestrator runner, tracker adapters, and sync/release tooling under `scripts/` are
boilerplate-owned, so upstream fixes reach consuming projects through this migration path instead
of being hand-ported. Ownership is **manifest-enumerated, never a directory blanket**: the
ownership map lists each boilerplate-owned script as an explicit pathspec — an exact file (e.g.
`scripts/orchestrator.sh`, `scripts/jira-tracker.sh`, `scripts/migrate-project.sh`) or a
wholly-owned subtree directory (e.g. `scripts/lib/`, `scripts/hooks/`). A consuming project's own
scripts under `scripts/` are **not** listed and are therefore project-owned by default — migration
never touches them. The driver enumerates exactly the listed set with `git ls-files -- <pathspec>`
(§3.1), so no code change is needed to classify scripts.

- **Drift** on a boilerplate-owned script is the ordinary CONFLICT case: it is reported with its
  `diff -u` hunk and **never overwritten**, identical to any other owned file.
- **Override surface (opt-out).** To keep a *deliberately* forked boilerplate script permanently,
  declare its exact path under `project_owned_exceptions:` in **`.agentic/upgrade/ownership.local.yaml`**
  (a consumer-owned map in your project) — **not** in the boilerplate-owned `.agentic/upgrade/ownership.yaml`.
  The driver unions the two lists (`ownership.yaml` ∪ `ownership.local.yaml`, ABS-264), so a local
  declaration is honored: the pinned file is reclassified project-owned, migration skips it, and it
  stops generating recurring CONFLICT noise — the `overrides/`-analog for the script domain
  (Amendment 2026-07-12, Q2). No `scripts/overrides/` directory is introduced. Editing the
  boilerplate-owned `ownership.yaml` directly would itself drift and produce permanent CONFLICT on
  every migration; `ownership.local.yaml` is carried as a `kind: structural` exception, so it has
  zero conflict surface and is never overwritten. The declaration is **subtract-only**: it can only
  add an exception (remove a file from the managed surface), never extend `boilerplate_owned` — that
  stays boilerplate-authoritative so upstream fixes always reach you unless you explicitly opt a file
  out. Each entry is graded in the report's `## Fork Budget` table exactly as an upstream exception is:
  a fork owes an `upstream_ref:` + `since:`; a `kind: structural` entry is permanent and never red.
  The same honoring applies to harness-surface files (§3.3).
- **Changelog (Amendment 2026-07-12, decision).** The migration report already lists every mapped
  script as REPLACE/ADD/CONFLICT, so the upgrade path does not depend on a changelog category to
  convey script changes. Adding a `scripts/` category to `HARNESS_CHANGELOG.yml` (today
  `.claude/`-oriented; `scripts/changelog-slice.sh` already accepts any `category` string, so no
  code change is required) is **recommended** for human-readable upgrade notes but **not
  load-bearing**; if deferred, the per-file report is the source of truth.

### 3.3 The harness surface (ADR-A-0008 Amendment 2026-07-14, ABS-248)

Agent-defs, skills, hooks, and commands live under six harness domains: `.claude/`, `.gemini/`,
`.codex/`, `.cursor/`, `.agents/`, and `dark-factory/`. From v2.25.2 all six are boilerplate-owned
entries in `.agentic/upgrade/ownership.yaml`, so **harness fixes reach consuming projects through
the ordinary migration path** — no manual `.claude` delta between releases.

**Which tree ships.** The driver runs from a release tag, where `.claude/` is the
governor-generated, promoted artifact — the file a consumer actually has. `harness/claude/`
(ADR-A-0016) is the **inert seat-edit source**: no consumer has a `harness/` directory, and the
driver's same-path model cannot remap between paths. Only `.claude/` (the artifact) is mapped;
`harness/claude/` remains excluded (see the exclusion table in §3).

**Provider-domain gate (`sync_scope`).** A project receives only the harnesses it adopted. The
five non-`.claude` domains are gated on the target manifest's existing `sync_scope` field (default
`[".claude"]`). A Claude-only project receives zero `.gemini/` ADDs. To receive a provider harness
in the next migration, add its domain to `sync_scope` in `.harness-manifest.yml`. No new
configuration field is introduced (ADR-A-0010).

**Identity-file protection.** `.claude/team-config.json` and `.claude/hooks-config.json` are
listed in `project_owned_exceptions:` — they carry the consumer's own team roster and hook wiring
and are never overwritten by migration. The driver also folds the target manifest's `protected:`
list into its exception set, so a per-consumer `protected:` declaration is respected without a
separate `project_owned_exceptions` entry.

**Drift and override.** A locally modified harness file follows the same drift semantics as any
other boilerplate-owned file: CONFLICT, never silently overwritten, reported with its `diff -u`
hunk. To keep a deliberate fork permanently, declare its exact path under
`project_owned_exceptions:` in `.agentic/upgrade/ownership.local.yaml` (the consumer-side
override surface, §3.2). To add project-specific rules to an **agent def** without forking it,
use an **overlay** instead (§3.4) — the preferred mechanism that keeps the def receiving upstream
improvements.

**`sync-claude-harness.sh` is unchanged.** The `DELEGATE_CLAUDE` block previously in
`migrate-project.sh` is retired: it was dead code, broken three ways, and redundant after ABS-249
made the generic path substitution-aware. `scripts/sync-claude-harness.sh` remains a
boilerplate-owned **standalone consumer tool** with an unchanged public contract; consumers who
invoke it directly are unaffected.

### 3.4 Customizing an agent def: use an OVERLAY, not a fork (ADR-A-0022, ABS-258)

**This is the standard way to adapt a shipped agent def to your project.** Editing the def file
itself is the trap: the customization is almost always *additive* (a project section appended to
the role prompt), but an edit makes the whole file drift, so every migration reports it as a
CONFLICT and the same section has to be re-appended by hand — forever.

Instead, **add** a file; never edit the def:

```bash
# Project-specific rules for the QAS seat — the def itself stays untouched.
mkdir -p .agentic/overrides/agents
$EDITOR .agentic/overrides/agents/qas.append.md     # plain markdown, no frontmatter
```

At spawn time the orchestrator composes the seat prompt as
**`_common-rules.md` body + role-def body + overlay body** (`scripts/orchestrator-spawn-claude.sh`,
`build_agents_json()`); later text refines earlier text, so the overlay wins where it contradicts
the def. The def file on disk is never modified, so migration keeps classifying it **REPLACE** —
the project takes upstream improvements to the def *and* keeps its own section, which editing the
def cannot do.

**Which mechanism do I want?**

| Your change to a def | Mechanism | What migration does |
| -------------------- | --------- | ------------------- |
| **Additive** — append project rules, test commands, conventions to the role prompt | `.agentic/overrides/agents/<role>.append.md` (overlay) | Def: REPLACE (keeps receiving upstream updates). Overlay: never touched. **No conflict.** |
| **Wholesale** — you have genuinely rewritten the def and want to keep your version | Add the def's path to `project_owned_exceptions:` (§3.2) | Def: never touched — and it **stops receiving upstream improvements entirely**. |

Reach for the exception list only when you truly mean to fork. It is the heavier trade: it buys
silence from CONFLICTs by giving up upstream updates to that def. An overlay gives you both.

Limits (ADR-A-0022): the overlay is **append-only and body-only**. Frontmatter in an overlay is
stripped and ignored — it cannot widen the seat's `tools` (that is the seat's privilege grant; use
`ORCH_TOOLS`/`ORCH_MODEL` at the runner instead), change its model, or rename it. Overlays apply to
orchestrator-spawned seats only; interactive Task-tool subagent use loads the def directly and does
not see them (the same limit `_common-rules.md` has). If a customization cannot be expressed as an
append, it is an upstream feature request (`.agentic/templates/consumer-feedback-item.md`), not a fork.

---

## 4. Worked Example: Migrating a Project from 0.1.0 to 0.2.0

**Setup**: `~/projects/acme-shop` was created from boilerplate `0.1.0` (its `.boilerplate-version` reads `0.1.0`). The boilerplate checkout at `~/boilerplate` is at `0.2.0`.

### Step 1 — Run the driver

The human invokes the agent from `~/boilerplate` against `~/projects/acme-shop`. The agent runs the driver once:

```bash
scripts/migrate-project.sh ~/projects/acme-shop
```

The driver mechanically (no file contents read into any LLM context):

1. Reads both markers: target `0.1.0`, current `0.2.0` → migration `0.1.0 -> 0.2.0`.
2. Verifies the target has no tracked modifications and no untracked files on the boilerplate-owned surface
   (ABS-277). Unrelated untracked files (build artefacts, a stray `package-lock.json`) neither block the run
   nor enter the migration commit.
3. Classifies files per section 3 (`git ls-files` enumeration over the ownership map) and batch-hashes the
   ownership-mapped set via `shasum -a 256`, extracting the original baseline from the `v0.1.0` git tag (see section 3.1):
   - 14 boilerplate-owned files changed between 0.1.0 and 0.2.0, hashes match target → replaced
   - 1 new file in 0.2.0 → added
   - 1 drifted file (hash differs; project locally patched an agent definition) → conflict, NOT overwritten
4. Creates the branch `boilerplate-migration-0.1.0-to-0.2.0`, applies the replace/add set, runs any declared migrations,
   updates `.boilerplate-version` to `0.2.0`, writes the report, and commits — one reviewable diff, nothing merged.

It prints a machine-readable summary to stdout (`replaced=14 added=1 conflicts=1 ...` and the report path).

### Step 2 — Report

The driver writes `work/migration-reports/2026-07-02-0.1.0-to-0.2.0.md` in the target project (included in the commit):
versions, the 15 files changed, the breaking-change slice of the changelog (`scripts/changelog-slice.sh`), and the 1
conflict awaiting human decision **with a pre-computed `diff -u` hunk**. The agent reads ONLY that hunk to append a human
recommendation (keep as an `overrides/` entry, or drop and file an upstream feature request) — never the full files.

### Step 3 — Human Merge

The human reviews the branch, resolves the drift conflict (keep the local patch as an `overrides/` entry, or drop it and file an upstream feature request), opens a PR, and merges it. **Merging is human-only** — the agent's deliverable ends at the committed branch plus the report.

---

## 5. Abort and Escalation Cases

The driver stops immediately with a distinct **exit code** and escalates to the human when:

| Exit | Case | Why | Human action |
| ---- | ---- | --- | ------------ |
| 3 | Target has **no `.boilerplate-version` marker** | Every boilerplate-derived project is versioned from day one; a missing marker means the project was not created from the boilerplate | Treat as existing-project **adoption** (analysis → migration plan → human approval), not a version upgrade |
| 4 | Target version **newer** than the running checkout's | The agent would be downgrading; it is running from a stale checkout | Update the boilerplate checkout, re-invoke |
| 0 | Target version **equals** current | Nothing to do | None — reports "already up to date" and creates no branch |
| 5 | Tracked modifications, or untracked files **on the boilerplate-owned surface** (ABS-277) | Migration diff must be isolated and reviewable; an untracked file on an owned path would be classified and committed as boilerplate | Commit or stash the paths named in the message, re-invoke. `--allow-untracked` migrates colliding untracked files anyway. Unrelated untracked files never block |
| 6 | **Ownership map missing** | Classification is strict from `.agentic/upgrade/ownership.yaml`; there is no LLM tree-classification fallback (ABS-227) | Ensure the source checkout ships the map (generated at setup/release), re-invoke |
| 7 | A **declared migration step fails** partway | No half-applied, unreported state is acceptable — the marker is not stamped and nothing is committed | Review the reported failing step; decide fix vs. drop the branch |

Anything the agent notices that is out of migration scope (project bugs, stale docs, refactor opportunities) is recorded in the migration report's manual follow-ups — never acted on (ADR-A-0010).

---

## 6. Consumer-Feedback Channel (ABS-260)

Drift is not only a conflict to resolve locally — it is **evidence about the boilerplate**. Every fork a project keeps is a
fix or a missing feature that upstream does not have. This section makes that return path a fixed part of the migration
cycle instead of an ad-hoc courtesy (precedent: the 2026-07-13 consumer CSV batch, which became epic ABS-245).

### 6.1 Consumer Side — Export Duty

When a migration ends with conflicts, or the project patched a boilerplate-owned file between migrations, the project
**exports one consumer-feedback item per local fix/fork**:

- **Format**: [`.agentic/templates/consumer-feedback-item.md`](../../.agentic/templates/consumer-feedback-item.md) — five
  CSV columns (`Summary,Type,Priority,Labels,Description`), the `Description` carrying **Finding / Repro / Fix / Fork**.
- **Location**: `work/consumer-feedback/YYYY-MM-DD-<project-slug>.csv` in the consuming project, committed on the
  migration branch (so it travels with the diff the human reviews).
- **Who writes it**: the **boilerplate-migration agent** — one item per conflict the project keeps, as part of its LLM job
  ([`.claude/agents/boilerplate-migration.md`](../../.claude/agents/boilerplate-migration.md)) — and the
  **self-improvement agent** for boilerplate-level findings
  ([`SELF_IMPROVEMENT_SOP.md`](SELF_IMPROVEMENT_SOP.md) section 5).
- **A kept fork without an exported item is a WARNING, never a failure.** Migration does not abort over a missing item; it
  simply never lets a fork stay invisible. Today the migration agent records that warning in the report's Manual
  Follow-Ups; the **driver-side** check (a mechanical warning per unexported fork) lands with the
  `project_owned_exceptions` aging / `upstream_ref` work in ABS-259, which shares this report slot.
- **Forwarding is human-only** (ADR-A-0004): a human sends the CSV upstream. Agents never write to the boilerplate
  repository.

### 6.2 Upstream Side — Intake

Each received batch runs the same three gates the 2026-07-13 batch ran:

1. **Dedup gate** — every item is searched against the tracker BEFORE anything is created (`duplicate-detection` skill).
   A match is appended to the existing ticket, never filed twice.
2. **Verification against HEAD** — reproduce or refute each item against the **current boilerplate HEAD**, not against the
   version the consumer runs. An item HEAD already fixes is not re-implemented. Items without a usable `Repro` are bounced
   back to the consumer rather than guessed at.
3. **One verdict per item** — exactly one of:

| Verdict | Meaning | Upstream action |
| ------- | ------- | --------------- |
| `integrate` | Reproduced on HEAD; the boilerplate should carry the fix | Ticket filed (under an epic where a batch warrants one) and scheduled like any other work |
| `already-fixed` | HEAD already contains the fix — the consumer is behind | No ticket; the consumer is told which version carries it |
| `works-as-designed` | The behavior is intended; the local change is a project preference | No ticket; the fork stays a `project_owned_exceptions` entry with a rationale |

**Then: the verdict goes back to the consumer** — one reply per item: the ticket key (`integrate`), the fixing version
(`already-fixed`), or the rationale (`works-as-designed`). The consumer records a returned ticket key as the
`upstream_ref` of its exception entry (ABS-259) — that is what later lets the driver report the fork as **de-forkable**
once HEAD ships the fix.

No item is silently dropped: every exported row ends in a verdict, and every kept fork ends in either an `upstream_ref` or
a recorded `works-as-designed` rationale.
