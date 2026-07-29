# ABS-117 Design Spec — Session-Resume Config-Generation Stamp + Stale-Session Invalidation

**Ticket**: ABS-117 (epic ABS-114) · **Status**: accepted (architect review 2026-07-07: approve-with-changes; F1 agent-defs added to the hash, F2 per-sweep recompute adopted, F3–F5 test/format fixes — all incorporated) · **Date**: 2026-07-07

## 0. Defect being fixed

ABS-111's session resume keeps the ORIGINAL permission/settings context of the session across
runner config generations: the run-1 dev session of ABS-108 (pre-worktree, pre-allowlist fixes)
stayed tracker-denied on every resume while FRESH spawns worked fine. Resumed Claude sessions
re-read nothing — allowlist fixes never reach them.

## 1. Config generation

`CONFIG_GENERATION` = `cksum` over the concatenation of everything a resume FREEZES but a fresh
spawn re-reads (the boundary, per architect F1: `--model`/`--max-turns`/`--permission-mode` are
passed per spawn even on resume and are deliberately NOT hashed):
1. `$ORCH_STATE_ROOT/.claude/settings.local.json` (when present — the live permission surface a
   spawn actually runs under; absent file contributes nothing, which itself changes the hash),
2. `scripts/orchestrator.sh` (runner version proxy — any runner change is a new generation),
3. `scripts/orchestrator-spawn-claude.sh` (the spawn seam: flags/model/env handed to sessions),
4. all `*.md` files (sorted) in the RESOLVED agent-defs dir — `--resume` omits `--agents`, so the
   role prompt + `tools:` frontmatter is the LARGEST context a resume freezes (architect F1); the
   resolution mirrors the seam's ABS-96 order (`ORCH_AGENTS_DIR` > `$ORCH_HARNESS_HOME/harness/`
   `.claude/agents` > `$ORCH_HARNESS_HOME/.claude/agents`). Any agent-def edit over-invalidates
   ALL stored sessions — ADR-A-0002-safe by construction (fresh is always allowed).

Recomputed ONCE PER SWEEP (the ticket's constraint, adopted per architect F2): fresh spawns of a
RUNNING runner re-read `settings.local.json` on every `claude` invocation, so after a mid-run
operator edit fresh and resumed sessions diverge immediately — a start-time-only stamp would keep
resuming stale sessions until the next restart. Per-sweep costs nothing when nothing changed
(same inputs → same cksum → zero extra invalidation). `ORCH_CONFIG_GENERATION` env overrides the
computed value (tests; operator force-invalidate by setting a throwaway value). Zero-dependency:
`cksum`/`find`/`sort` are POSIX.

Rejected: per-ticket re-hash (waste, the constraint's own point); git-describe as version source
(not available in exported/consumer repos).

## 2. Stamp + invalidation

Session store format (`$ORCH_STATE_DIR/sessions/<ticket>.<role>.<status>`) grows a second line:
line 1 = session id (unchanged), line 2 = the generation stamp at store time. Written wherever
the sid is captured (attempt_spawn, including failure paths).

Before every FILE-based resume (the A2 lookup in spawn_dispatch): read both lines; when the
stored generation differs from `CONFIG_GENERATION` — or is missing entirely (legacy single-line
file from a pre-ABS-117 runner: unknown context, exactly the defect case) — the session file is
deleted, a machine-readable `SESSION-INVALIDATED` line goes to run.log (ticket, role, status,
`stored=<gen> current=<gen>`), and the spawn proceeds FRESH. The in-memory handoff-repair resume
(A2c, same run, same generation by construction) is untouched.

Conformance: ADR-A-0002 — fresh is always allowed; the resume-until-acceptance amendment is an
optimization, and invalidation just falls back to the base rule.

## 3. Test plan (tests/test-orchestrator.sh, ABS-111/A2 section)

- regression: same generation → A2a resume behavior unchanged (existing A2a now runs with stamps)
- mismatch: store under `ORCH_CONFIG_GENERATION=genA`, bounce under `genB` → NO RESUME intent,
  fresh spawn happens, `SESSION-INVALIDATED` in run.log, new session file carries `genB`
- legacy single-line session file (hand-written fixture) → invalidated, fresh spawn
- stamp is written: session file's line 2 equals the active generation after a spawn
