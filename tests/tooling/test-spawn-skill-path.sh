#!/usr/bin/env bash
# =============================================================================
# ABS-535 — seat skill references resolve to the LIVE .claude/skills, never to
#           the inert harness/claude/skills source
# =============================================================================
# Origin (v3-pilot #3, 2026-07-22): every tech-writer spawn ended SESSION-
# POISONED. Its agent-def body cites skill files as
# `harness/claude/skills/<name>` — the EDITABLE SOURCE namespace, inert per the
# ABS-94 governor-pin model (the live harness is the generated .claude/). In
# self-hosting the seat resolved those citations against ORCH_HARNESS_HOME,
# read <stable>/harness/claude/skills/*, got a permission denial, and the
# ORCH_SESSION_POISON_GUARD (correctly) refused to store the session — so
# every follow-up spawn of the station started cold.
#
# The fix lives in the spawn seam (scripts/orchestrator-spawn-claude.sh):
#   1. concrete `harness/claude/skills/<name>` references in the composed
#      prompt (commons + role body + overlay) are rewritten to
#      $ORCH_SKILLS_DIR/<name> (default <harness>/.claude/skills/<name>);
#   2. glob/namespace mentions (`harness/claude/skills/*` in the mirror-parity
#      rule — about EDITING the source, not loading a skill) stay untouched;
#   3. reads under the live skills dir are allowlisted READ-ONLY via
#      --allowedTools "Read(//…/**)" (never --add-dir) so the rewritten
#      reference is loadable under --permission-mode dontAsk — but ONLY when
#      the skills dir lies OUTSIDE the effective seat cwd (self-hosting); in a
#      plain consumer repo (harness == cwd) reads inside the workspace are
#      already permitted and the argv stays byte-identical to the legacy spawn;
#   4. no live skills dir -> no rewrite, no extra rule (fail-open).
#
# The seam is exercised FOR REAL (not reimplemented): a stub `claude` binary is
# handed to it via ORCH_CLAUDE_BIN and records the --agents JSON plus the full
# argv. No real Claude spawn. Same pattern as tests/test-agent-def-overlay.sh.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/test-spawn-skill-path.sh
# =============================================================================
set -u

# ABS-285: scrub ambient ORCH_* so the result is a function of the commit, not
# of the seat that ran the suite. This test sets everything it needs below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SEAM="$REPO_ROOT/scripts/orchestrator-spawn-claude.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/spawn-skill-path-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3 (expected to find: $2)"; FAIL=$((FAIL + 1))
    fi
}
assert_not_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo -e "  ${RED}FAIL${NC} $3 (unexpectedly found: $2)"; FAIL=$((FAIL + 1))
    else
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    fi
}

# -----------------------------------------------------------------------------
# Fixtures: a HARNESS (governing checkout — ships defs AND the generated live
# .claude/skills) and a PROJECT (the seat's cwd). Separate dirs on purpose:
# that is the ABS-92 self-hosting split in which the defect fired.
# -----------------------------------------------------------------------------
HARNESS="$TEST_DIR/harness"
PROJECT="$TEST_DIR/project"
AGENTS_DIR="$HARNESS/harness/claude/agents"
LIVE_SKILLS="$HARNESS/.claude/skills"
mkdir -p "$AGENTS_DIR" "$PROJECT" \
         "$LIVE_SKILLS/docs-station" "$LIVE_SKILLS/stop-slop"
printf 'recipes\n' > "$LIVE_SKILLS/docs-station/SKILL.md"
printf 'gate\n'    > "$LIVE_SKILLS/stop-slop/SKILL.md"

# Commons body carries a concrete skill reference AND the mirror-parity glob
# mention — the first must be rewritten, the second must survive verbatim.
cat > "$AGENTS_DIR/_common-rules.md" <<'EOF'
---
title: common rules
---
COMMONS: apply the `stop-slop` checklist (`harness/claude/skills/stop-slop`).
If your change edits ANY `harness/claude/agents/*.md` or `harness/claude/skills/*`
file, regenerate the provider mirror in the SAME commit.
EOF

# The poisoned station itself: tech-writer citing the docs-station SKILL.md
# exactly like the shipped def does (no Skill tool — Read-only loading).
cat > "$AGENTS_DIR/tech-writer.md" <<'EOF'
---
name: tech-writer
description: docs station
tools: [Read, Write, Edit, Bash]
---
Recipes live in `harness/claude/skills/docs-station/SKILL.md`.
Apply `stop-slop` (`harness/claude/skills/stop-slop`) before handoff.
EOF

# A Skill-tool seat, to prove the Skill rule and the Read rule COMBINE.
cat > "$AGENTS_DIR/qas.md" <<'EOF'
---
name: qas
description: skill-tool seat
tools: [Read, Bash, Skill]
---
Use `testing-patterns` (`harness/claude/skills/testing-patterns`).
EOF

# Stub `claude`: records --agents JSON and the full argv, then returns a
# well-formed result. Never talks to a real model.
RECORDER="$TEST_DIR/fake-claude.sh"
AGENTSLOG="$TEST_DIR/agents.json"
ARGVLOG="$TEST_DIR/argv.log"
DEFLOG="$TEST_DIR/fallback-def.md"   # PILOT-23: the plugin-materialized def, if any
cat > "$RECORDER" <<RECBIN
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$ARGVLOG"
while [ \$# -gt 0 ]; do
    case "\$1" in
        --agents) printf '%s' "\$2" > "$AGENTSLOG"; shift 2 ;;
        # PILOT-23: on the argv-size fallback the seam hands the def via a
        # throwaway --plugin-dir; capture the materialized def for inspection.
        --plugin-dir) cat "\$2"/agents/*.md > "$DEFLOG" 2>/dev/null; shift 2 ;;
        *) shift ;;
    esac
done
echo '{"result": "ok", "session_id": "rec"}'
RECBIN
chmod +x "$RECORDER"

# Drive the real seam once for <role>; sets JSON + ARGV + DEF globals.
JSON=""; ARGV=""; DEF=""
spawn() {  # spawn <role> [extra env assignments via ORCH_* already exported]
    rm -f "$AGENTSLOG" "$ARGVLOG" "$DEFLOG"
    ORCH_HARNESS_HOME="$HARNESS" \
    ORCH_SPAWN_CWD="$PROJECT" \
    ORCH_CLAUDE_BIN="$RECORDER" \
    "${@:2}" \
        bash "$SEAM" "$1" ABS-535 /dev/null </dev/null >/dev/null 2>&1
    JSON="$(cat "$AGENTSLOG" 2>/dev/null || true)"
    ARGV="$(cat "$ARGVLOG" 2>/dev/null || true)"
    DEF="$(cat "$DEFLOG" 2>/dev/null || true)"
}

echo -e "${CYAN}=== ABS-535: skill references resolve to the live .claude/skills ===${NC}\n"

# =============================================================================
echo -e "${CYAN}AC1 — concrete skill references rewritten to <harness>/.claude/skills${NC}"
# =============================================================================
spawn tech-writer
assert_contains "$JSON" "$LIVE_SKILLS/docs-station/SKILL.md" \
    "docs-station reference points at the LIVE skills dir"
assert_contains "$JSON" "$LIVE_SKILLS/stop-slop" \
    "stop-slop reference points at the LIVE skills dir"
assert_not_contains "$JSON" "harness/claude/skills/docs-station" \
    "no harness/claude/skills path remains for docs-station"
assert_not_contains "$JSON" "harness/claude/skills/stop-slop" \
    "no harness/claude/skills path remains for stop-slop (role body)"

# =============================================================================
echo -e "\n${CYAN}AC1b — commons bucket rewritten too; glob/source mentions preserved${NC}"
# =============================================================================
assert_contains "$JSON" "COMMONS: apply the \`stop-slop\` checklist (\`$LIVE_SKILLS/stop-slop\`)" \
    "commons-body skill reference rewritten"
assert_contains "$JSON" "harness/claude/skills/*" \
    "mirror-parity glob mention (harness/claude/skills/*) survives verbatim"
assert_contains "$JSON" "harness/claude/agents/*.md" \
    "agents source mention untouched (rewrite is skills-load-scoped)"

# =============================================================================
echo -e "\n${CYAN}AC2 — reads under the live skills dir are allowlisted READ-ONLY${NC}"
# =============================================================================
assert_contains "$ARGV" "--allowedTools" \
    "seam passes --allowedTools"
assert_contains "$ARGV" "Read(/$LIVE_SKILLS/**)" \
    "Read(//…/.claude/skills/**) rule emitted (absolute-path permission rule)"
assert_not_contains "$ARGV" "--add-dir" \
    "no --add-dir (would grant WRITE access to the governing skills)"
assert_not_contains "$ARGV" "$HARNESS/harness/claude/skills" \
    "argv never names the inert harness/claude/skills source"

# =============================================================================
echo -e "\n${CYAN}AC2b — Skill-tool seat: Skill rule and Read rule combine${NC}"
# =============================================================================
spawn qas
assert_contains "$ARGV" "Skill" \
    "Skill invocation rule still emitted for a Skill-tool seat (ABS-123)"
assert_contains "$ARGV" "Read(/$LIVE_SKILLS/**)" \
    "Read rule emitted alongside the Skill rule"
assert_contains "$JSON" "$LIVE_SKILLS/testing-patterns" \
    "Skill-tool seat's reference rewritten too"

# =============================================================================
echo -e "\n${CYAN}AC3 — ORCH_SKILLS_DIR override wins${NC}"
# =============================================================================
ALT_SKILLS="$TEST_DIR/alt-skills"
mkdir -p "$ALT_SKILLS"
spawn tech-writer env ORCH_SKILLS_DIR="$ALT_SKILLS"
assert_contains "$JSON" "$ALT_SKILLS/docs-station/SKILL.md" \
    "explicit ORCH_SKILLS_DIR is the rewrite target"
assert_contains "$ARGV" "Read(/$ALT_SKILLS/**)" \
    "Read rule follows the override"

# =============================================================================
echo -e "\n${CYAN}AC3b — consumer mode (harness == cwd): rewrite yes, Read rule no${NC}"
# =============================================================================
# In a plain consumer project the harness IS the workspace, so the live skills
# dir sits inside the seat cwd — readable already. The reference is still
# rewritten to the live path, but no Read rule is emitted: the argv stays
# byte-identical to the legacy spawn (this is what keeps the ABS-123 "Skill-less
# toolset -> no --allowedTools" invariant in tests/test-orchestrator.sh green).
spawn tech-writer env ORCH_SPAWN_CWD="$HARNESS"
assert_contains "$JSON" "$LIVE_SKILLS/docs-station/SKILL.md" \
    "consumer mode: reference still rewritten to the live path"
assert_not_contains "$ARGV" "Read(" \
    "consumer mode: no Read rule (skills dir is inside the workspace)"

# =============================================================================
echo -e "\n${CYAN}AC4 — fail-open: no live skills dir -> byte-identical legacy spawn${NC}"
# =============================================================================
BARE="$TEST_DIR/bare-harness"
mkdir -p "$BARE/harness/claude/agents"
cp "$AGENTS_DIR/_common-rules.md" "$AGENTS_DIR/tech-writer.md" "$BARE/harness/claude/agents/"
rm -f "$AGENTSLOG" "$ARGVLOG"
ORCH_HARNESS_HOME="$BARE" \
ORCH_SPAWN_CWD="$PROJECT" \
ORCH_CLAUDE_BIN="$RECORDER" \
    bash "$SEAM" tech-writer ABS-535 /dev/null </dev/null >/dev/null 2>&1
JSON="$(cat "$AGENTSLOG" 2>/dev/null || true)"
ARGV="$(cat "$ARGVLOG" 2>/dev/null || true)"
assert_contains "$JSON" "harness/claude/skills/docs-station/SKILL.md" \
    "without a live .claude/skills the reference is left as-is"
assert_not_contains "$ARGV" "Read(" \
    "no Read rule emitted without a live skills dir"

# =============================================================================
echo -e "\n${CYAN}AC5 (PILOT-23) — argv-size fallback rewrites too (no unrewritten seat material)${NC}"
# =============================================================================
# Origin (v3-pilot #4, 2026-07-24): the ABS-535 rewrite sat ONLY on the inline
# --agents JSON path. A role def larger than ORCH_AGENTS_ARG_MAX (24000B default;
# be-developer/po-agent/tech-writer all exceed it) trips the ABS-251 argv-size
# gate and falls back to loading the on-disk def — which the OLD fallback pulled
# UN-rewritten, so large seats stayed SESSION-POISONED despite the ABS-535 fix
# (first evidence: PILOT-14 tech-writer). The fix materializes the SAME
# composed+rewritten def via a throwaway --plugin-dir. Force the fallback with a
# 1-byte gate and prove no harness/claude/skills LOAD path survives in the seat
# material, that the rewrite + commons + Read-allowlist all still apply, and that
# a unique selector is used so a same-named project agent cannot shadow it.
spawn tech-writer env ORCH_AGENTS_ARG_MAX=1
assert_not_contains "$ARGV" "--agents" \
    "fallback forced: inline --agents omitted (argv stays under the Windows limit)"
assert_contains "$ARGV" "--plugin-dir" \
    "fallback hands the def via a throwaway --plugin-dir (def travels in a file, not argv)"
assert_contains "$ARGV" "tech-writer__seat" \
    "fallback selects a UNIQUE agent name (a same-named project agent cannot shadow it)"
assert_contains "$DEF" "name: tech-writer__seat" \
    "fallback def frontmatter carries the unique selector name"
assert_contains "$DEF" "$LIVE_SKILLS/docs-station/SKILL.md" \
    "fallback def: docs-station reference rewritten to the LIVE skills dir"
assert_contains "$DEF" "$LIVE_SKILLS/stop-slop" \
    "fallback def: stop-slop reference rewritten to the LIVE skills dir"
assert_not_contains "$DEF" "harness/claude/skills/docs-station" \
    "fallback def: no harness/claude/skills LOAD path remains for docs-station"
assert_not_contains "$DEF" "harness/claude/skills/stop-slop" \
    "fallback def: no harness/claude/skills LOAD path remains for stop-slop"
assert_contains "$DEF" "COMMONS: apply" \
    "fallback def: commons prepended too (ABS-174 parity, unlike the pre-PILOT-23 fallback)"
assert_contains "$DEF" "harness/claude/skills/*" \
    "fallback def: mirror-parity glob mention survives verbatim (EDIT-scoped, not a load)"
assert_contains "$ARGV" "Read(/$LIVE_SKILLS/**)" \
    "fallback: Read-allowlist for the live skills dir still emitted"
assert_not_contains "$ARGV" "--add-dir" \
    "fallback: no --add-dir (no WRITE grant to the governing skills)"

# =============================================================================
echo ""
echo -e "${CYAN}=== Results: $PASS/$TOTAL passed ===${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}$FAIL test(s) failed${NC}"
    exit 1
fi
echo -e "${GREEN}All tests passed${NC}"
exit 0
