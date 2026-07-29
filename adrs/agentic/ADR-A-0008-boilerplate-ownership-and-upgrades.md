---
id: ADR-A-0008
title: Boilerplate ownership map and version-tracked upgrades
status: accepted
scope: agentic
date: "2026-07-02"
accepted_by: "Raphael Sahann (Operator)"
accepted_date: "2026-07-12"
---

## Context

A boilerplate that projects patch locally stops being upgradeable within months. Upgradeability
requires an enforceable line between boilerplate-owned and project-owned files.

## Decision

We will treat `.agentic/` as fully boilerplate-owned, with exactly two project-owned exceptions:
`config.yaml` and `overrides/`. The machine-readable map is `.agentic/upgrade/ownership.yaml`;
the installed version is `.agentic/VERSION`. Upgrades hash-compare boilerplate-owned files
(drift is surfaced to the human, never silently overwritten), replace boilerplate-owned files,
run declared migrations, stage agentic-ADR changes as proposals, and land as one PR through the
standard merge gate. Project needs the config/overrides surface can't express become feature
requests to the boilerplate repository (`.agentic/templates/consumer-feedback-item.md`).

## Consequences

Projects stay upgrade-clean by construction; local patches are detected, not forbidden-and-
forgotten. The boilerplate evolves through one channel (upstream feature requests), so
improvements reach every project. `adrs/agentic/` content is boilerplate-owned while its
acceptance frontmatter is project-owned — drift detection ignores those two fields.

## Amendment 2026-07-03 (ABS-5, ADR-A-0012)

Until the `.agentic/` directory layout ships, the installed-version marker is
`.boilerplate-version` at the repository root (plain one-line semver, introduced at `0.1.0`).
The Boilerplate Migration Agent reads and writes this marker; when the `.agentic/` layout
lands, the marker moves to `.agentic/VERSION` as originally specified above.

## Amendment 2026-07-12 (ABS-228) — `scripts/` (runner/adapter/tooling) enters the ownership surface

**Status: accepted** — accepted_by: "Raphael Sahann (Operator)", accepted_date: "2026-07-12".
(The base ADR-A-0008 was also accepted by the operator on 2026-07-12 — see the file frontmatter
`accepted_by`/`accepted_date`; `tests/test-adr-status.sh` requires exactly those fields for an
`accepted` ADR.)

### Context

The original Decision fixed the ownership surface at `.agentic/`. A field report (Florian,
consumer project, 2026-07-12) showed the gap: the orchestrator/tracker-adapter/tooling under
`scripts/` is forked at setup and then **never migrated**, because it sits outside the
ownership map. Upstream runner fixes (e.g. the v2.24.1 Epic-JOIN gate fixes, ABS-210/211/214/216,
which live in `scripts/`) therefore never reach consumer projects via the regular upgrade path —
they must be hand-ported. The mechanical migration driver `scripts/migrate-project.sh`
(ABS-227, merged) already exists and classifies **strictly from the ownership map**; it needs
map entries for the script surface, not new code. This amendment decides the three design
questions ABS-228 mandates.

### Decision

**Q1 — Which `scripts/` are boilerplate-owned? Manifest-enumerated, not a directory blanket.**
`scripts/` is **not** wholesale boilerplate-owned. Consumer projects add their own scripts, so a
`scripts/` directory-blanket would clobber them. The trennlinie is the **explicit path list in
the ownership map** (`.agentic/upgrade/ownership.yaml`, `boilerplate_owned:`): each
boilerplate-owned script is listed as an exact pathspec (e.g. `scripts/orchestrator.sh`,
`scripts/jira-tracker.sh`, `scripts/migrate-project.sh`), and a wholly-owned subtree may be
listed as its directory pathspec (e.g. `scripts/lib/`) only when the *entire* subtree is
boilerplate-managed. Everything else under `scripts/` is project-owned by default and never
touched. This is mechanically checkable with **zero driver change**: the driver already
enumerates the owned set via `git ls-files -- <pathspec>` per map entry (§ Step 3), so a
project's own scripts — being outside the enumerated set — are simply never classified.
*Rejected:* a `scripts/` directory blanket (destroys project-added scripts); glob patterns like
`*-tracker.sh` (implicit, fragile, and unsupported by the pathspec-per-entry parser).

**Q2 — Drift semantics & override surface: existing CONFLICT class + `project_owned_exceptions`,
no new machinery.** A locally patched boilerplate-owned script is exactly the existing **CONFLICT**
class: hash != `v<from>` baseline -> surfaced in the migration report with its `diff -u` hunk,
**never silently overwritten** — identical semantics to `.claude`/`.agentic` today (§3.1). No
special script-only drift rule. The override surface analog to `overrides/` already exists: a
project that *intentionally and permanently* forks a specific boilerplate-owned script adds that
exact path to the map's **`project_owned_exceptions:`** list, which reclassifies it project-owned
so migration never touches it and it stops generating recurring CONFLICT noise. *Rejected:* a new
`scripts/overrides/` directory — new machinery for a need the existing exceptions list already
covers (ADR-A-0010 minimal-change).

**Q3 — Cut vs ABS-227: ABS-227 is the mechanism (done); ABS-228 is data + docs only.** The driver
(ABS-227, merged) is the complete mechanism — it consumes the map's explicit pathspecs and
CONFLICT-reports drift with **no code change required** for the script surface. ABS-228 therefore
ships only: (a) the enumerated boilerplate-owned script paths added to
`.agentic/upgrade/ownership.yaml`; (b) SOP §3 + the migration agent-def updated to name the
script domain and its `project_owned_exceptions` opt-out; (c) the changelog decision below.
Sequencing: ABS-227 first (satisfied — Done), then ABS-228. No driver re-work, no conflict.

**Changelog (ABS-228 AC4) — surfaced by the migration report; a HARNESS_CHANGELOG `scripts/`
category is optional, not load-bearing.** The migration report already lists per-file
REPLACE/ADD/CONFLICT for every mapped script from the map diff, so the upgrade path does **not**
depend on a changelog category to convey script changes. Adding a `scripts/` category to the
existing `HARNESS_CHANGELOG` / `changelog-slice.sh` (today `.claude/`-only) is worthwhile for
human-readable upgrade notes and is the recommended execution choice, but it is not required for
migration correctness — recording that here satisfies the ticket's "category OR documented
decision against" as: *add the category (recommended), and if deferred, rely on the report*.

### Consequences

- Orchestrator/adapter/tooling fixes now reach consumer projects through the regular migration
  path; the boilerplate<->project trust boundary for `scripts/` is mechanically checkable (explicit
  map entries), consistent with the rest of the ownership model.
- No driver change and no new directory: the whole extension is ownership-map data + doc updates,
  honoring ADR-A-0009 (zero-dep bash) and ADR-A-0010 (minimal change).
- Projects retain a clean, documented escape hatch for a deliberately forked script
  (`project_owned_exceptions:`), so frequent local script patching does not drown the report in
  CONFLICTs.

## Amendment 2026-07-13 (ABS-259) — fork budget: `upstream_ref` duty + de-fork check in the report

**Status: proposed** — human acceptance required (ADR-A-0004). The base ADR's frontmatter stays
`accepted`; this section is the proposal under review.

### Context

The Amendment 2026-07-12 (Q2) gave projects an escape hatch: add a locally patched
boilerplate-owned file to `project_owned_exceptions:` and migration stops touching it. The hatch
has no exit. An exception is a permanent, silent, unattributed fork: nothing records *why* it
exists, *whether* an upstream fix was ever requested, or *when* it may be dropped. Over a few
releases a project accretes exceptions, each one a hole in the upgrade path, and the migration
report — the one artifact a human actually reads — says nothing about them. That is the same
"patch locally, stop being upgradeable" failure the base ADR exists to prevent, merely relocated
from undeclared drift into a declared list.

The consumer migration-report census (BUSCH-15) shows the driver already computes everything the
fix needs: it hashes the target file, the `v<from>` baseline, and the current source. Making a
fork visible, justified, and time-bounded is therefore a **schema + report** change, not new
machinery.

### Decision

**Q1 — Schema: block-mapping entries with `path` / `kind` / `upstream_ref` / `since`;
bare-path entries stay valid and report as unjustified.**

```yaml
project_owned_exceptions:
  # Structural override surface (base ADR-A-0008): project-owned BY DESIGN, permanent.
  - path: .agentic/config.yaml
    kind: structural
  - path: .agentic/overrides/
    kind: structural
  # Fork: a locally patched boilerplate-owned file. Temporary by construction.
  - path: scripts/orchestrator.sh
    kind: fork
    upstream_ref: ABS-231      # the filed upstream ticket — REQUIRED for kind: fork
    since: "2026-07-12"        # ISO date the fork was taken — REQUIRED for kind: fork
```

`kind` defaults to **`fork`** when absent. That default is what makes the migration backward
compatible in the direction the ticket demands: a legacy bare-path entry (`- scripts/foo.sh`)
remains a *valid* exception — migration still never touches it — but it is a `fork` with neither
`upstream_ref` nor `since`, so it reports as **UNJUSTIFIED**. Nothing breaks; the debt becomes
visible.

`kind: structural` is load-bearing and must be explicit. *Rejected:* inferring "structural" from
"the boilerplate source ships no file at this path". It looks free — in the current boilerplate
`.agentic/config.yaml` and `.agentic/overrides/` are indeed untracked — but it is a coincidence of
today's tree, not a semantic truth: a boilerplate may legitimately ship a **default**
`config.yaml` that projects then customize (the driver's own test fixture,
`tests/test-migrate-project.sh:80`, creates exactly that). Under the inference rule those projects
would see their config and overrides reported red **forever**, with no action that could ever clear
them — and a permanently red report trains humans to ignore red. *Also rejected:* encoding the
metadata in a trailing YAML comment (`- scripts/foo.sh  # upstream_ref: ABS-231`). It would need
zero parser change, because `parse_yaml_list` already strips trailing comments — and it is data
masquerading as a comment, invisible to every YAML consumer that is not this one awk function.

**Q2 — Verdict taxonomy, and the budget NEVER blocks the upgrade.** The report gains one section,
`## Fork Budget (project_owned_exceptions)`, with one line per exception:

| Verdict | Condition | Meaning |
|---|---|---|
| ✅ `DE-FORK` | target content == current upstream content | upstream now ships your fix — **delete the exception entry** |
| 🔴 `UNJUSTIFIED` | `kind: fork` without `upstream_ref` and/or `since` (incl. every legacy bare-path entry) | an unattributed fork — file the upstream ticket or drop the fork |
| 🟡 `STALE` | justified fork, age > budget | the upstream ticket is not landing — chase it or accept the fork permanently |
| 🟢 `JUSTIFIED` | justified fork, age ≤ budget | healthy: forked, filed, in budget |
| ⚪ `STRUCTURAL` | `kind: structural` | the designed override surface — informational, never red |
| ⚠️ `ORPHAN` | `kind: fork`, upstream ships no file at that path | upstream removed the file; the exception is moot |

`DE-FORK` takes precedence over the justification verdicts (an upstreamed fork is deletable whether
or not it was ever justified). Budget default **90 days**, overridable via
`MIGRATE_FORK_MAX_AGE_DAYS`.

The fork budget is **report-only: it never changes the driver's exit code and never blocks a
migration.** A stale fork must not fail the upgrade — that would punish the consumer at exactly the
moment they are trying to get back onto upstream, inverting the incentive this amendment exists to
create. The driver reports; the human decides and deletes the entry (ADR-A-0004, ADR-A-0005).

**Q3 — The de-fork check is hash equality against the CURRENT SOURCE, not the `v<from>` baseline.**
For a `kind: fork` exception, the driver compares the target's file content against the file the
*incoming* boilerplate version ships (`$SOURCE/$path`, i.e. the `<to>` content). Equal means
upstream has converged on the project's local version — the fork is redundant and the exception
line is deletable. This is the identical comparison the driver already performs to reach its
existing `SKIP` ("already current") class (`scripts/migrate-project.sh:265`), applied to paths the
classify loop currently `continue`s past (`:238`). Agentic-ADR exceptions use the
acceptance-frontmatter-stripped content hash (`hash_adr_content_file`), consistent with the base
ADR. For a directory pathspec, `DE-FORK` requires **every** source file under it to match.

Hash equality is deliberately conservative: it yields **no false "deletable"** verdicts, at the
cost of missing a fork that upstream absorbed *semantically* but not byte-for-byte (upstream took
the fix plus unrelated changes). A false `DE-FORK` would push a human to delete an exception and
silently lose a local fix on the next migration; a missed one merely leaves a fork in the report
for another cycle. We take the safe error.

**Q4 — Cut: one script, one test, plus map data. No new dependency, no new file.** The change is
confined to `scripts/migrate-project.sh` (the only consumer of the map besides its own test —
verified with `git grep`) and `tests/test-migrate-project.sh`:
(a) `parse_yaml_list` strips an optional leading `path:` from a list entry, so both the mapping and
the bare-path form yield a plain path and `is_exception` is untouched;
(b) a small awk helper reads a named field of an exception entry;
(c) Step 6 of the report gains the Fork Budget section.
Classification, application, and exit codes are unchanged. Age arithmetic must be computed in awk
(days-from-civil) rather than `date -d` / `date -j`, whose flags differ between GNU and BSD — the
driver runs on both consumer Linux CI and macOS dev machines.

### Consequences

- Every fork of a boilerplate-owned file becomes visible, attributed to an upstream ticket, and
  aged — the escape hatch acquires an exit. The upgrade path's holes are now countable, and
  `DE-FORK` verdicts mechanically retire them as upstream lands the fixes.
- Forking gains a small, deliberate cost (file a ticket, date the entry) and a recurring reminder,
  which is the intended pressure: the cheap path becomes "get it upstream", not "keep it local".
- Backward compatible by construction: existing maps keep working unchanged and simply start
  reporting their exceptions as UNJUSTIFIED. No consumer migration step is required to adopt this.
- The `structural` / `fork` split means the report's red entries are always actionable, which is
  the property that keeps the report worth reading.
- Accepted limitation (Q3): a fork upstreamed with non-identical bytes keeps reporting until the
  human drops it. No automation deletes an exception entry — deletion stays human (ADR-A-0004).

## Amendment 2026-07-13 (ABS-264) — consumer-declarable exceptions: SOURCE ∪ TARGET map union, subtract-only

**Status: proposed** — human acceptance required (ADR-A-0004). The base ADR's frontmatter stays
`accepted`; this section is the proposal under review.

### Context

The ownership map is read only from `$SOURCE` (`scripts/migrate-project.sh`, pre-existing since
ABS-227 `b8b96b3`). A consuming project therefore cannot reach the escape hatch this ADR grants
(Amendment 2026-07-12, Q2 — add a path to `project_owned_exceptions:`): its declaration lives on
the TARGET side, which the driver never reads. A consumer that instead edits the boilerplate-owned
`ownership.yaml` drifts that file, so the edited map AND the fork it was meant to exempt both land
in permanent CONFLICT on every migration. SOP §3.2 instructed exactly this broken flow. The fork
budget (Amendment 2026-07-13, ABS-259) can then only grade upstream's own exception list — the
consumer end of the de-fork loop (epic ABS-245) stays open. This is not data loss (both files are
PRESERVED as CONFLICT, never overwritten); the cost is a silently ignored opt-out plus permanent
doubled conflict noise.

### Decision

**Q1 — `project_owned_exceptions` is the union of the SOURCE map and a project-owned TARGET map.**
The driver reads exceptions from `$SOURCE/.agentic/upgrade/ownership.yaml` ∪
`$TARGET/.agentic/upgrade/ownership.local.yaml`. `ownership.local.yaml` is project-owned by design:
a consuming project declares its own forks/opt-outs there, and both the classifier and the fork
budget consume the unioned list. The union is read **once** into a single exceptions table and
reused for classification and the report, preserving the ABS-259 invariant that the report can
never grade an entry the classifier ignored.

**Q2 — Subtract-only: the local map may add exceptions, never extend `boilerplate_owned`.** Only
`project_owned_exceptions` is unioned from the local map; `boilerplate_owned` stays
SOURCE-authoritative. A `boilerplate_owned:` block in `ownership.local.yaml` is ignored with a
warning. This keeps two guarantees: upstream never loses the ability to grow its managed surface (a
release adding files to `boilerplate_owned` always reaches a consumer running an older local map),
and a consumer cannot withhold upstream files it never explicitly declared. **Rejected: reading
`boilerplate_owned` from TARGET** — a consumer running an older map would silently drop files
upstream newly manages, including security fixes.

**Q3 — `ownership.local.yaml` is itself a `kind: structural` exception.** It is carried in the
SOURCE map's `project_owned_exceptions` as structural, so migration never overwrites the consumer's
declaration file: it has zero conflict surface, unlike the boilerplate-owned `ownership.yaml` a
consumer used to edit.

**Q4 — The delegated `.claude/**` sync honors the unioned list.** `scripts/migrate-project.sh`
delegates the `.claude` domain to `scripts/sync-claude-harness.sh`, which did not read the exception
list (verified: zero references). A `.claude/**` exception was therefore graded by the fork budget
yet clobbered by the delegated sync — the exact report/classifier divergence ABS-259 eliminates
elsewhere. The driver now exports the unioned exception list as `MIGRATE_EXCEPTIONS`; the sync skips
any declared path (exact file or directory-subtree prefix), so a graded `.claude/**` fork is
preserved exactly as the budget reports it.

**Q5 — The fork budget is the safety control that makes the union safe.** An over-broad local
exception (`- scripts/` withholding every upstream fix, including security) is exactly what the
ABS-259 fork budget renders visible and red. The union does not weaken the upgrade path because
every exception it admits is graded and aged in the report a human reads.

### Consequences

- The de-fork loop closes at the consumer end: a project declares its forks in a project-owned map
  the driver honors and the budget grades, without drifting any boilerplate-owned file.
- The consumer-facing escape hatch acquires a conflict-free home; SOP §3.2 is corrected to point
  consumers at `ownership.local.yaml` (never the boilerplate-owned `ownership.yaml`).
- The classifier, the report, and the delegated `.claude` sync now agree on one exception list — no
  path the budget grades can be silently overwritten.
- Backward compatible: a project with no `ownership.local.yaml` is unaffected; the union degrades to
  the SOURCE-only read.

## Related decisions

- **ADR-A-0022** (agent-def overlays, proposed) refines the `overrides/` surface decided here: an
  *additive* customization of a shipped agent def belongs in
  `.agentic/overrides/agents/<role>.append.md` (composed at the spawn seam, base file stays
  upstream-pure → REPLACE, never CONFLICT), while `project_owned_exceptions:` remains the hatch for
  a *wholesale* forked file.

## Amendment 2026-07-14 (ABS-248) — the harness surface enters the ownership map

**Status: proposed** — requires human acceptance (ADR-A-0004). The base ADR and the ABS-228
amendment remain `accepted` and are unchanged by this section.

### Context

The ownership map lists `.agentic/`, `adrs/agentic/` and the enumerated `scripts/` set — but **no
harness domain**. The driver classifies strictly from the map, so `git ls-files -- <pathspec>` never
yields a `.claude/` path, the REPLACE/ADD lists never contain one, and the `.claude` delegation in
`scripts/migrate-project.sh` is unreachable **dead code**. Consequence in the field: consumers
hand-applied the `.claude` delta for three consecutive releases (consumer-feedback CSV item 8;
BUSCH-15 migration reports, all three: "`.claude` delta manuell"). Agent-defs, skills and hooks —
the core of the harness — never migrated.

ABS-248's stop-the-line (BE seat, 2026-07-13) rejected the ticket's literal fix. Both of its premises
were **re-verified against `origin/main` (f7c9a68)** before this decision:

- **Delegation defects — confirmed, all three.** `PROJECT_ROOT` derives from `BASH_SOURCE`
  (`sync-claude-harness.sh:26`), so the driver's `cd "$TARGET" && bash "$SOURCE/scripts/…"` operates
  on the **boilerplate**, not the target; `sync` sources upstream over the network (`curl` tarball,
  ~`:1333`/`:1371`) and cannot consume the local `--source` checkout the migration is defined
  against; `do_sync` never parses `--yes` (bare `*)` catch-all), while `sync` hard-requires a
  manifest — so the `team-config.json`-only trigger delegates into a guaranteed failure swallowed by
  a `warn`.
- **Substitution-blindness — NO LONGER HOLDS.** Sibling **ABS-249 (Done, merged after the
  stop-the-line)** made the driver substitution-aware in *both* directions: `norm_upstream()`
  instantiates `{{TOKEN}}`s in the baseline *and* source streams before hashing, and
  `subst_in_place()` instantiates on write. `is_substitutable()` keys on **file extension**
  (`*.md|*.json|*.yml|*.sh|…`), not on path — so harness files are already covered *by construction*.
  The "193 phantom conflicts" premise is obsolete. This discharges the PO's reconciliation
  precondition, and it is what collapses the design space below.

The question **neither the ticket nor the stop-the-line asked** is the one that actually blocks:
**which tree ships?** Upstream carries two harness trees — `harness/claude/` (inert, seat-editable
source; ADR-A-0016) and the live `.claude/` (`generated(pin)` from `.governor-tag`; ABS-94). A
consumer has `.claude/` and **no `harness/` directory at all**. The driver's model is strictly
same-path (`$SOURCE/$path` ↔ `$TARGET/$path` ↔ `git show v<from>:<path>`); it cannot express a
source→target remap. Mapping the wrong tree therefore fails outright.

### Decision

**Q1 — Map the generated artifact at its shipped path, never the source tree.** The owned harness
domains are `.claude/`, `.gemini/`, `.codex/`, `.cursor/`, `.agents/`, `dark-factory/`.
**`harness/claude/` is NOT mapped.** Migration always runs its source checkout **at a release tag**,
and at a tag the live `.claude/` is by construction the promoted, governor-generated artifact —
verified identical to `harness/claude/` at `v2.25.1`, and divergent on `main` exactly as ADR-A-0016
intends (`harness/claude` diverges freely between promotions). The shipped artifact is also already
at the path the consumer has, so the same-path model is preserved and **no remap machinery is
needed**. *Rejected:* mapping `harness/claude/` — it is inert work-product at a path no consumer
owns, and would ship un-promoted mid-release state.

**Q2 — Provider domains are gated by the target manifest's existing `sync_scope`** (default
`[".claude"]`, already read by `sync-claude-harness.sh:138-147`). A project receives only the
harnesses it adopted. Without this gate a Claude-only consumer would receive **232 unwanted files**
(`.gemini` 87, `.agents` 95, `dark-factory` 19, `.cursor` 18, `.codex` 13) as ADDs on its next
upgrade. The principle: **the migration surface equals the install surface.** No new config surface
is introduced (ADR-A-0010) — `sync_scope` is an existing, consumer-authored field.

**Q3 — Retire the delegation; the generic path becomes the single mechanism.** Delete the
`DELEGATE_CLAUDE` block and its `apply_copy` guard (`migrate-project.sh` ~552–588). It is dead
today, broken three ways on `main` (above), and — post-ABS-249 — **redundant**: the generic path
already normalizes tokens for hashing and instantiates them on write. The harness then inherits the
**uniform ADR-A-0008 Q2 drift semantics** (REPLACE / ADD / CONFLICT-reported with its `diff -u` hunk,
**never silently overwritten**) that already govern `.agentic/`, `adrs/agentic/` and `scripts/`.
`scripts/sync-claude-harness.sh` stays a boilerplate-owned **standalone consumer tool** and its
public contract is **unchanged**.

*Both options routed to this seat are rejected.* **Option A** (`--from-path` local-source mode +
delegate to the target's own copy) would change a shared script's public contract *and* require
fixing all three defects — to regain a capability the driver now has natively. **Option B** (make the
driver substitution-aware) is moot: **ABS-249 already built exactly that, in the driver, once.**
Choosing either would leave two sync engines to keep in step. One engine, one semantics.

**Q4 — Project-owned exceptions target the *tracked* identity files.** `.claude/team-config.json`
and `.claude/hooks-config.json` enter `project_owned_exceptions:`. The ticket's AC3
(`.claude/settings.json`, `.claude/launch.json`) is **vacuous**: those files are untracked upstream,
and the driver enumerates only from the source index, so it can never reach them — that test would be
green in a vacuum. Additionally, the driver **folds the target manifest's existing `protected:` list
into its `EXCEPTIONS` set**: it already opens `.harness-manifest.yml` and parses `identity:` /
`substitutions:` (ABS-249, `migrate-project.sh:270-274`) and already computes `EXCEPTIONS` /
`is_exception()` (ABS-264, `:426-429`) — so per-consumer protection becomes authoritative for one
additional parsed field, not new machinery.

**Q5 — Manifest `renames:` is a known, bounded, non-destructive gap — explicitly out of scope.** A
consumer that renamed a harness file (`agents/fe-developer.md` → `agents/ui-engineer.md`) has no
target counterpart at the upstream path, so the driver classifies **ADD** and re-adds the upstream
original. Nothing is overwritten and the ADD is listed in the migration report, so the failure mode
is *noise, not data loss*. Rename-awareness is **not** built here (ADR-A-0010, YAGNI); it is recorded
as a follow-up and the first consumer that actually hits it drives the design.

### Consequences

- Harness fixes (agent-defs, skills, hooks) reach consumers through the **one** regular upgrade path.
  The three-release manual `.claude`-delta ends — the actual consumer pain behind CSV item 8.
- **One sync mechanism, not two.** The broken second engine stops being load-bearing in migration;
  `sync-claude-harness.sh` survives untouched as a standalone tool, so nothing regresses for consumers
  who invoke it directly.
- **The ADR-A-0016 boundary is now explicit and must stay explicit:** `harness/claude/` is the
  **seat-edit source**; the pinned `.claude/` is the **migration-ship artifact**. A well-meaning
  future "fix" repointing the map at `harness/claude/` would break **every** consumer (no `harness/`
  directory). ADR-A-0016 carries a cross-reference back to this amendment for exactly that reason.
- A project can never be handed a provider harness it never adopted (`sync_scope` gate).
- The `renames:` noise gap stays open — deliberately, non-destructively, and reported.
- Scope is ownership-map **data** plus two bounded driver deltas (delete the delegation; gate on
  `sync_scope`; fold `protected:`), honoring ADR-A-0009 (zero-dep bash) and ADR-A-0010.

### Implementation notes (input to the ABS-248 re-spec; supersedes its AC1–AC3)

1. `.agentic/upgrade/ownership.yaml`: add the six domains to `boilerplate_owned:`; add
   `.claude/team-config.json` and `.claude/hooks-config.json` to `project_owned_exceptions:`.
2. `scripts/migrate-project.sh`: delete the `DELEGATE_CLAUDE` block + `apply_copy` guard; gate the
   five non-`.claude` domains on the target manifest's `sync_scope`; fold manifest `protected:` into
   `EXCEPTIONS`.
3. `tests/test-migrate-project.sh`: (a) the harness census is non-empty; (b) a token-substituted
   harness file classifies **REPLACE, not CONFLICT** (the ABS-249 regression guard — this is the test
   that would have caught the original design error); (c) `team-config.json` / `hooks-config.json` are
   byte-unchanged after migration; (d) `sync_scope` gate: a Claude-only target receives **zero**
   `.gemini/` ADDs; (e) no delegation is invoked (the dead path is gone).
