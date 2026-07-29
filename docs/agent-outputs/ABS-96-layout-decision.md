# ABS-96 — Shipped-Harness Namespace: Layout Audit + #PATH_DECISION

**Ticket**: ABS-96 (parent ABS-93, epic ABS-91 "self-hosting: stable governs dev")
**Author**: System Architect
**Date**: 2026-07-05
**Status**: Decided — implemented in this ticket

---

## 1. Problem statement

Under self-hosting (ABS-91), the boilerplate develops itself under a *pinned stable
checkout* that governs a *dev repo* (the work target). Today the SHIPPED harness — the
`.claude/` files a consuming project receives — lives on the **live config path**
(`.claude/` is what Claude Code actually reads at runtime). That makes the shipped harness
simultaneously (a) the product we ship and (b) the config that governs our own sessions.
Editing it as work product risks mutating the governing config.

ABS-96 moves the shipped harness OUT of the live config path into an inert **product
namespace**, so tickets can edit it freely as work product. The namespace becomes the
**source of truth**; the live `.claude/` keeps a byte-identical copy until Phase 2b starts
generating `.claude/` from the namespace.

---

## 2. Layout audit (canonical / shipped today)

### 2.1 `.claude/` top-level classification

| Item | Tracked? | Class | Moves to namespace? | Rationale |
|------|----------|-------|---------------------|-----------|
| `agents/` | yes | SHIPPED | **yes (source)** | Agent role defs — core shipped product |
| `skills/` | yes | SHIPPED | **yes (source)** | Auto-loaded skills — shipped product |
| `commands/` | yes | SHIPPED | **yes (source)** | Slash commands — shipped product |
| `hooks/` | yes | SHIPPED | **yes (source)** | Hook scripts — shipped product |
| `hooks-config.json` | yes | SHIPPED | **yes (source)** | Hook wiring — shipped product |
| `settings.template.json` | yes | SHIPPED | **yes (source)** | Settings template — shipped product |
| `README.md` | yes | SHIPPED | **yes (source)** | Harness docs — shipped product |
| `SETUP.md` | yes | SHIPPED | **yes (source)** | Harness docs — shipped product |
| `TROUBLESHOOTING.md` | yes | SHIPPED | **yes (source)** | Harness docs — shipped product |
| `AGENT_OUTPUT_GUIDE.md` | yes | SHIPPED | **yes (source)** | Harness docs — shipped product |
| `team-config.json` | yes | **LOCAL-RUNTIME** | **NO** | Fork-specific identity/runtime config; ticket-forbidden to touch; a consuming project's own file, not generic shipped content |
| `settings.local.json` | no (gitignored) | **LOCAL-RUNTIME** | **NO** | Per-machine local overrides; gitignored |
| `worktrees/` | no (gitignored) | **LOCAL-RUNTIME** | **NO** | Orchestrator worktree state; gitignored |
| `.harness-sync.json` | no (gitignored) | **LOCAL-RUNTIME** | **NO** | Sync metadata; gitignored (legacy .claude/ location) |
| `.harness-backup/` | no (gitignored) | **LOCAL-RUNTIME** | **NO** | Sync backups; gitignored |
| `.harness-patches/` | no (gitignored) | **LOCAL-RUNTIME** | **NO** | Sync patches; gitignored |
| `.sync-exclude*` | (fallback) | **LOCAL-RUNTIME** | **NO** | Legacy exclusion files; stay in `.claude/` |

**Confirmed via**: `git ls-files .claude/<item>`, `git check-ignore`, `.gitignore` lines 133-135.

### 2.2 `dark-factory/` and provider domains — SEPARATE sync domains, STAY PUT

`sync-claude-harness.sh` treats every sync domain as an independent top-level directory:
the domain loop resolves `DOMAIN_DIR="$PROJECT_ROOT/$CURRENT_DOMAIN"` for each entry of
`SYNC_SCOPE`. `ALLOWED_DOMAINS` today is
`(".claude" ".gemini" ".codex" ".cursor" ".agents" "dark-factory")`.

| Domain | Tracked files | Classification | Moves? |
|--------|---------------|----------------|--------|
| `.gemini/` | 77 | Separate provider domain (Gemini harness) | **NO — stays a top-level sync domain** |
| `.codex/` | 13 | Separate provider domain (Codex harness) | **NO** |
| `.cursor/` | 18 | Separate provider domain (Cursor rules/mcp) | **NO** |
| `.agents/` | 88 | Shared cross-provider domain | **NO** |
| `dark-factory/` | many | Separate namespace (Codex dark-factory guides/scripts/templates) | **NO** |

These are NOT part of the `.claude` harness namespace — they are peer domains, each synced
independently, each read at its own runtime path by its own tool. `.gemini/skills` is NOT a
byte-copy of `.claude/skills` (confirmed by `diff -rq` — they differ). ABS-96 scope is the
`.claude` domain ONLY; provider-domain namespacing (if ever wanted) is a separate future
decision and explicitly out of scope here.

### 2.3 What `setup-template.sh` does with these paths

The bootstrap wizard operates **in place**: it `find`s files under `REPO_ROOT` by extension
and applies `sed` token replacement. It does NOT copy `.claude/` to a target directory. Its
only literal `.claude` reference is emitting the generated manifest's default
`sync_scope: [".claude/"]` (line 716). Therefore the wizard's *file-transformation* output
is independent of where the shipped source lives — as long as the live `.claude/` tree still
exists at bootstrap time (it does; we keep a byte-identical copy). The one line that would
change consuming-project output is the emitted `sync_scope` default — see §5.

### 2.4 `scripts/orchestrator-spawn-claude.sh` (ABS-92 seam)

`AGENTS_DIR="${ORCH_AGENTS_DIR:-$ORCH_HARNESS_HOME/.claude/agents}"` (line 50). The stable
checkout at the current release tag (v2.16.0) has **no namespace dir** — only `.claude/`.
So the default MUST keep resolving to `.claude/agents`. `test-orchestrator.sh` builds a temp
`$HARNESS/.claude/agents` and points `ORCH_HARNESS_HOME` at it, hard-asserting the
`.claude/agents` path resolves. See §6.

---

## 3. #PATH_DECISION — namespace choice

### Options considered

**Option A — new root namespace `harness/`** (mirrors the domain 1:1: `harness/.claude/…`).
**Option B — fold into existing `templates/` + `agent_providers/`** (scatter shipped items
into two pre-existing dirs).

### Decision: **Option A — a new root namespace `harness/`, with the shipped `.claude`
domain as `harness/.claude/…`**

`git mv .claude/<shipped-item>` → `harness/.claude/<shipped-item>`, then copy back into the
live `.claude/` so the runtime path stays byte-identical.

### Why `harness/.claude/` (not `harness/` flat, not `templates/`)

1. **Consumer sync simplicity — trivial UPSTREAM_PATH mapping per domain.** The sync script
   already keys everything on a domain name that is *both* the upstream subpath *and* the
   local subpath (`$TMP_DIR/$domain` ↔ `$PROJECT_ROOT/$domain`). Keeping the inner directory
   named `.claude` means the namespace path `harness/.claude` maps to the consumer's local
   `.claude` by stripping the single `harness/` prefix. A flat `harness/agents/…` would force
   a per-file domain-name rewrite. Aliasing `harness/.claude → .claude` is a one-line prefix
   strip.
2. **Phase-2b generation simplicity.** Generating the live `.claude/` becomes a pure copy:
   `cp -R harness/.claude/. .claude/`. No path rewriting, no rename table — source tree shape
   == destination tree shape. This is the single biggest reason to preserve the inner
   `.claude` name.
3. **Minimal churn / clean separation.** `templates/` is nearly empty (a README) and
   `agent_providers/` holds provider *bindings* (augment, claude_code), a different concept
   from the shipped harness content. Folding shipped agents/skills/commands into those dirs
   would overload two unrelated namespaces and scatter the product. A dedicated `harness/`
   root says exactly what it is: the shipped harness product, inert work product.
4. **Provider domains stay orthogonal.** `harness/` houses only the `.claude` domain for now.
   `.gemini/.codex/.cursor/.agents/dark-factory` remain peer top-level domains, untouched —
   no coupling, no scope creep.

### Rejected: Option B (fold into `templates/`+`agent_providers/`)

- Breaks the domain-name == path-segment invariant the sync loop relies on.
- Forces a rename table and per-file path rewriting for both consumer sync AND Phase-2b
  generation.
- Overloads `agent_providers/` (bindings) with shipped content (roles) — a concept collision.
- Higher churn in scripts/tests/docs for no upside.

---

## 4. Legacy-consumer compatibility (the compat story)

`.claude` **stays listed in `ALLOWED_DOMAINS`** alongside the new `harness/.claude`. Reasons:

- Existing consumer manifests declare `sync_scope: [".claude/", …]`. They pull `.claude`
  from upstream. Post-move the committed `.claude/` at any tag is a byte-identical copy of
  `harness/.claude` (until Phase 2b, when it becomes *generated(tag)*). So a legacy consumer
  syncing `.claude` from a tag gets exactly what they got before. **No consumer action
  required.** (`test-multi-domain-sync.sh` locally overrides `ALLOWED_DOMAINS` with the old
  list, so it is unaffected by the additive change — verified.)
- **Interaction with ABS-95 (tag-freshness).** Post-2b the invariant is
  `committed .claude/@tag  ==  generate(harness/.claude)@tag`. ABS-95's tag-freshness fix
  ensures a synced consumer is compared against a *released tag's* tree; because the tag's
  committed `.claude/` equals its generated form, ABS-95 stays correct whether a consumer
  syncs the legacy `.claude` domain or (future) the `harness/.claude` source. This ticket
  keeps both in lockstep by copy-back; ABS-97/98 wire the generation + reference cleanup.

`harness/.claude` is added as an allowed domain and documented as the canonical upstream
source going forward. Consumers may opt into it later; today they need not.

---

## 5. `sync_scope` default in `setup-template.sh`

Kept as `.claude/` (unchanged). A freshly-bootstrapped consuming project has a live
`.claude/` and expects to sync that domain — flipping the emitted default to
`harness/.claude/` now would (a) change consuming-project bootstrap output (violating the
byte-identity AC) and (b) require the consumer to carry a `harness/` dir they do not have.
The namespace is an **upstream-source** concept; the consumer-facing default stays `.claude/`.
This is the correct minimal, compat-preserving choice for ABS-96. Any future flip is a
deliberate ABS-97/2b decision, not this ticket's.

**Net effect on consuming-project bootstrap output: ZERO** (proven by `diff -r`, §6).

---

## 6. Move mechanics + spawn seam

### Move mechanics
For each SHIPPED item: `git mv .claude/<item> harness/.claude/<item>` (history follows the
move), then `cp -R harness/.claude/<item> .claude/<item>` to restore the byte-identical live
copy. `.gitignore` for `.claude/` is untouched — `.claude/` stays tracked, and the restored
copies are re-added. LOCAL-RUNTIME items (`team-config.json`, `settings.local.json`,
`worktrees/`, `.harness-*`, `.sync-exclude*`) are NOT moved.

### Spawn seam (`orchestrator-spawn-claude.sh`)
Default becomes **namespace-preferred with `.claude/agents` fallback**:
`ORCH_AGENTS_DIR` unset → try `$ORCH_HARNESS_HOME/harness/.claude/agents`; if that dir does
not exist, fall back to `$ORCH_HARNESS_HOME/.claude/agents`. This keeps the stable v2.16.0
checkout (no `harness/` dir) working via fallback, and lets a future stable tag that ships
`harness/` resolve from the namespace. Minimal correct form; no new CLI flags.

---

## 7. Verification summary (see ticket report)

- 10 named suites green pre-change (baseline) and green post-change, unmodified.
- Bootstrap byte-identity proven with `diff -r` (empty result) pre/post move.
- `git status` accounted for; every moved/copied path listed in the report.
- bash 3.2 / BSD-safe; no `timeout`, no `grep -P`.

## 8. Deferred to ABS-97 / ABS-98 (explicit)

- Test path-reference migration (point suites/fixtures at `harness/.claude` where they
  should read the source rather than the live copy).
- Doc path-reference cleanup (READMEs / SOPs / changelog prose that name `.claude/…` as the
  *source* location).
- Phase-2b generation of live `.claude/` from `harness/.claude` (+ drift guard) and the
  eventual `sync_scope` default flip.
