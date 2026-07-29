---
id: ADR-A-0022
title: Agent-def overlays — append-only project customization composed at the spawn seam
status: proposed           # accepted when a human merges this ADR's PR (adrs/README.md)
scope: agentic
date: "2026-07-13"
---

## Context

Consumer projects need to add project-specific rules to a shipped agent def (e.g. a QAS section
naming the project's test commands). Today the only expressible form is **editing the def file**,
so the customization becomes byte-divergence in a boilerplate-owned file.

The field report (Florian, consumer project, 2026-07-12/13) shows the cost precisely: his migration
agent performs the **same ritual on every migration** — replace the upstream `qas.md` body, then
re-append the 28-line project section verbatim (three consecutive migration reports, diff-verified).
The customization is *additive*, but the ownership model only knows whole files, so a permanently
forked def and a recurring CONFLICT are the only outcomes. ADR-A-0008's Amendment (2026-07-12)
offers `project_owned_exceptions:` as the escape hatch, but that trades the conflict for a def that
**stops receiving upstream improvements entirely** — the wrong trade for an additive change.

The mechanism to fix this already exists and is unused for this purpose: the spawn seam's
`build_agents_json()` (`scripts/orchestrator-spawn-claude.sh`) **already composes an agent prompt
from more than one file** — ABS-174 feeds it `_common-rules.md` + the role def, keyed by file index,
and emits one `prompt` string. Composition at spawn time is therefore a solved, shipped pattern.

## Decision

Adopt **`.agentic/overrides/agents/<role>.append.md`** as the project-owned overlay for a shipped
agent def, composed **at the spawn seam**, append-only, body-only.

**D1 — Materialization point: the spawn seam (runtime composition), never a write-time file edit.**
`build_agents_json()` gains a third body bucket: the emitted prompt becomes
`commons body + role body + overlay body`. The on-disk def is **not** modified. This is the load-
bearing choice: because the def keeps upstream bytes, the migration driver's hash-compare
(`scripts/migrate-project.sh`, ADR-A-0008 §Q2) classifies it **REPLACE, never CONFLICT** — the base
file updates cleanly and the overlay, living under an already-declared
`project_owned_exceptions:` path (`.agentic/overrides/`, `.agentic/upgrade/ownership.yaml:62`), is
never touched. The recurring ritual disappears by construction.
*Rejected — appending into the materialized file at write time* (`sync-claude-harness.sh` /
`migrate-project.sh`): the on-disk file would then diverge from the upstream baseline hash on every
migration, i.e. it would produce **exactly the permanent CONFLICT this ticket exists to remove**.
Making that work needs recomposed-hash baselines in the driver — new machinery for no gain
(ADR-A-0010 minimal-change).

**D2 — Semantics: append-only, body-only. No frontmatter override, and specifically no `tools`
merge.** The overlay contributes prose that is appended *after* the role body (later text refines
earlier text). Only the role def supplies `name` / `description` / `tools` / `model`; a frontmatter
block in an overlay is **stripped and ignored**, with a `NOTICE` to stderr so the author is not
silently surprised. The existing awk parser already yields this for free (frontmatter fields are
read only from the role-def file index). `tools` is deliberately **not** additive: the toolset is the
seat's privilege grant, and a project-owned file that migration never inspects must not be able to
widen a security boundary. The runner-level levers for that need already exist (`ORCH_TOOLS`,
`ORCH_MODEL`) and stay the only way to change a seat's grant.

**D3 — Resolution: against the work TARGET, not the harness home.** The overlay is a *project*
customization while defs are read from the *harness* (`ORCH_HARNESS_HOME`, the ABS-92 self-hosting
split). It resolves from `ORCH_SPAWN_CWD` → `ORCH_TARGET_REPO` → the seam's repo root, overridable
via `ORCH_OVERRIDES_DIR`. `<role>` is the def basename (`qas` → `qas.append.md`). Behavior is
**fail-open**: no overlay file → the emitted `--agents` JSON is byte-identical to today. In a plain
consumer project harness and target are the same repo, so this is invisible; under self-hosting it
is the difference between reading the project's overlay and the boilerplate's (empty) one.

**D4 — Scope of the change: the spawn seam only.** `sync-claude-harness.sh` (3475 lines, legacy) and
`migrate-project.sh` need **no change** — D1 makes their existing behavior correct. The overlay is a
new project-owned file under a path the ownership map already excepts; the base def is already
handled by the REPLACE path.

**D5 — Known limit: orchestrator seats only.** Interactive Task-tool subagent use loads
`.claude/agents/*.md` directly and does **not** pass through the spawn seam, so it does not see the
overlay. This is the same trade-off ABS-174 already accepted for `_common-rules.md`, and the same
mitigation applies: a def keeps a short distillate of anything that must survive interactive use.
Only the shipped roles are overlayable; the `_common-rules.md` fragment is not (v1 scope).

**D6 — The non-null case: size has a BUDGET, and overage changes the LOAD PATH, not just the
transfer form (PILOT-55 / ABS-566).** D3's fail-open ("no overlay → byte-identical to today")
describes the *null* case only. The non-null case is that the composed prompt
(`_common-rules.md` + role def + overlay) has a **declared size budget** — 24000 B per seat
(`docs/sop/AGENT_CONFIGURATION_SOP.md` → "Prompt Size Budget"), enforced by
`scripts/agent-prompt-size.sh --check`. A seat over budget is a **defect**, not an operating mode.
This matters because the composed payload is the largest controllable cost item in a run (22–60 %
of paid input; `work/improvement-proposals/2026-07-25-token-efficiency-prefix-amplification.md`).

Crucially, overage does not merely change *how the same bytes are handed to the CLI* — it changes
**which load path runs**. The spawn seam gates on `ORCH_AGENTS_ARG_MAX`: above the gate it drops the
inline `--agents` JSON and materializes the composed def via a throwaway `--plugin-dir` (`--agent
<role>__seat`), a **different, historically fragile path** (the pre-PILOT-23 form of it produced the
Pilot-4 `SESSION-POISONED` series and correlates with 12 of 21 Pilot-5 `error_max_turns` aborts).
The gate defends the **Windows** CreateProcess limit (~32 KB for the whole command line); on POSIX
`getconf ARG_MAX` is ≥ 256 KB, so the gate is now **platform-dependent** (PILOT-55): Windows keeps
24000 B, POSIX defaults to `getconf ARG_MAX` minus headroom, restoring the inline path as the POSIX
NORMALFALL and the fallback as the exception it was designed to be. Budget (cost) and gate
(operational load-path) are two views of the same payload: keep the composed prompt within budget
and neither the token bill nor the fragile fallback path is triggered on any platform.

## Consequences

- The strongest structural de-fork lever available: an additive def customization stops being a
  fork. The base def keeps receiving upstream improvements *and* the project section survives
  migration untouched — the two outcomes that were previously mutually exclusive.
- Cost is one body bucket in an awk program that already does multi-file composition, plus a path
  lookup. No new directory (the map already excepts `.agentic/overrides/`), no driver change, no
  dependency — consistent with ADR-A-0009 (zero-dep bash) and ADR-A-0010.
- `project_owned_exceptions:` remains the right hatch for a *wholesale* forked def; the overlay is
  the right tool for an *additive* one. The SOP must teach the distinction (ABS-258 AC3), otherwise
  projects will keep reaching for the exception list and keep losing upstream updates.
- The overlay is unreviewed-by-upstream text injected into a seat prompt. That is intended (it is
  the project's own prompt surface) and bounded: it cannot widen tools, change the model, or rename
  the seat.
- Test surface (ABS-258 AC2): a base-def change plus an overlay yields a prompt containing **both**
  bodies and a clean (non-CONFLICT) migration classification for the def; no overlay yields a
  byte-identical prompt to the pre-change seam; an overlay carrying `tools:` frontmatter does **not**
  widen the emitted toolset.

## Related decisions

- **ADR-A-0008** (boilerplate ownership map) — defines the `overrides/` surface and the
  `project_owned_exceptions:` hatch this ADR refines; its 2026-07-12 Amendment supplies the
  CONFLICT/REPLACE drift semantics D1 depends on.
- **ADR-A-0010** (minimal-change default) — grounds the rejection of write-time recomposition.
- **ADR-A-0016** (`.claude` apply path) — the live `.claude/` is a generated artifact, never a
  hand-edited source; the overlay respects that by never writing into it.
- **ABS-174** (`_common-rules.md`) — the multi-file spawn-seam composition precedent this reuses,
  including its interactive-use limit (D5).

## References

- Ticket ABS-258 (epic ABS-245, consumer de-fork); ADR-A-0008 Amendment 2026-07-12 (ABS-228).
- `scripts/orchestrator-spawn-claude.sh` → `build_agents_json()`; `.agentic/upgrade/ownership.yaml`.
