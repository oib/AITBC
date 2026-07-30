#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Devin CLI spawn adapter for scripts/orchestrator.sh
# =============================================================================
# Implements the §3.1 provider seam contract:
#   "$0" <role> <ticket-id> <packet-file>
#     stdin:  the context packet
#     env:    ORCH_ROLE, ORCH_TICKET, ORCH_PACKET_FILE
#     stdout: the agent's final result, including the handoff record
#     exit 0: success   exit !0: spawn failure
#
# Use this adapter by setting:
#     ORCH_SPAWN_CMD=scripts/orchestrator-spawn-devin.sh
# or per-role:
#     ORCH_SPAWN_CMD_qas=scripts/orchestrator-spawn-devin.sh
#
# The agent definition is read from the same source as the Claude adapter
# (.claude/agents/<role>.md) and the prompt body is injected before the packet.
# Devin CLI is invoked in non-interactive print mode with the composed prompt.
#
# Environment:
#   ORCH_HARNESS_HOME     harness root (default: this script's repo)
#   ORCH_AGENTS_DIR       agent-def dir override
#   ORCH_SKILLS_DIR       live skills dir the prompt references (default .claude/skills)
#   ORCH_SPAWN_CWD        cd here before spawning
#   ORCH_DEVIN_BIN        devin binary (default: devin)
#   ORCH_DEVIN_MODEL      Devin model override
#   ORCH_DEVIN_PERMISSION_MODE  auto | accept-edits | smart (default: accept-edits)
# =============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH_HARNESS_HOME="${ORCH_HARNESS_HOME:-$REPO_ROOT}"

ROLE="${1:-${ORCH_ROLE:-}}"
TICKET="${2:-${ORCH_TICKET:-}}"
PACKET_FILE="${3:-${ORCH_PACKET_FILE:-}}"

die() { echo "spawn-devin: ERROR $*" >&2; exit 1; }

[ -n "$ROLE" ] || die "no role (arg 1 / ORCH_ROLE)"
[ -n "$TICKET" ] || die "no ticket (arg 2 / ORCH_TICKET)"

if [ -n "${ORCH_AGENTS_DIR:-}" ]; then
    AGENTS_DIR="$ORCH_AGENTS_DIR"
elif [ -d "$ORCH_HARNESS_HOME/.claude/agents" ]; then
    AGENTS_DIR="$ORCH_HARNESS_HOME/.claude/agents"
elif [ -d "$ORCH_HARNESS_HOME/harness/claude/agents" ]; then
    AGENTS_DIR="$ORCH_HARNESS_HOME/harness/claude/agents"
elif [ -d "$ORCH_HARNESS_HOME/harness/.claude/agents" ]; then
    AGENTS_DIR="$ORCH_HARNESS_HOME/harness/.claude/agents"
else
    AGENTS_DIR="$ORCH_HARNESS_HOME/.claude/agents"
fi

ROLE_DEF="$AGENTS_DIR/$ROLE.md"
[ -f "$ROLE_DEF" ] || die "no agent definition for role '$ROLE' at $ROLE_DEF"

SKILL_DIR="${ORCH_SKILLS_DIR:-$ORCH_HARNESS_HOME/.claude/skills}"
[ -d "$SKILL_DIR" ] || die "live skills directory missing: $SKILL_DIR"

TMPDIR="${TMPDIR:-/tmp}"
PACKET_TEMP="$(mktemp "$TMPDIR/devin-packet-$TICKET.XXXXXX")"
PROMPT_FILE="$(mktemp "$TMPDIR/devin-prompt-$TICKET.XXXXXX.md")"
trap 'rm -f "$PACKET_TEMP" "$PROMPT_FILE"' EXIT

# Packet: stdin wins (seam contract), file fallback.
if ! cat > "$PACKET_TEMP" 2>/dev/null; then
    [ -n "$PACKET_FILE" ] && PACKET_FILE=""
fi
if [ ! -s "$PACKET_TEMP" ] && [ -n "$PACKET_FILE" ]; then
    cat "$PACKET_FILE" > "$PACKET_TEMP"
fi

python3 - "$ROLE" "$ROLE_DEF" "$PACKET_TEMP" "$SKILL_DIR" "$PROMPT_FILE" <<'PY'
import sys

role, role_def_path, packet_path, skill_dir, prompt_path = sys.argv[1:6]

with open(role_def_path, 'r', encoding='utf-8') as f:
    body = f.read()

# Extract body after the second '---' frontmatter marker.
parts = body.split('---')
role_prompt = '---'.join(parts[2:]) if len(parts) >= 3 else body

# Rewrite stable-harness skill references to the live skill tree.
role_prompt = role_prompt.replace('harness/claude/skills/', skill_dir + '/')
role_prompt = role_prompt.replace('harness/.claude/skills/', skill_dir + '/')
role_prompt = role_prompt.replace('harness/claude/agents/', role_def_path.rsplit('/', 1)[0] + '/')
role_prompt = role_prompt.replace('harness/.claude/agents/', role_def_path.rsplit('/', 1)[0] + '/')

with open(packet_path, 'r', encoding='utf-8') as f:
    packet = f.read()

with open(prompt_path, 'w', encoding='utf-8') as f:
    f.write(f"""---

# Agent seat: {role}

{role_prompt}

=== CONTEXT PACKET ===

{packet}

---

End your reply with the '## Handoff' record exactly as the packet instructs.
""")
PY

# Change to the runner-provisioned worktree if given.
[ -n "${ORCH_SPAWN_CWD:-}" ] && [ -d "$ORCH_SPAWN_CWD" ] && cd "$ORCH_SPAWN_CWD"

DEVIN_BIN="${ORCH_DEVIN_BIN:-devin}"

# Role-aware permission mode. QAS and Security Engineer are intentionally
# read-only in Devin (separation-of-duties, same as the Claude seam's tool
# restriction); implementers and writers can edit. ORCH_DEVIN_PERMISSION_MODE
# overrides this default.
case "${ROLE}" in
    qas|qas-design|security-engineer)
        DEFAULT_PERM="auto"
        ;;
    *)
        DEFAULT_PERM="accept-edits"
        ;;
esac
PERM_MODE="${ORCH_DEVIN_PERMISSION_MODE:-$DEFAULT_PERM}"

# Resolve the Devin model. ORCH_DEVIN_MODEL wins, then a translation of
# ORCH_MODEL (which the orchestrator sets from the agent def's frontmatter).
# Leave the flag off entirely if no model is known so Devin uses its default.
RESOLVED_MODEL="${ORCH_DEVIN_MODEL:-}"
if [ -z "$RESOLVED_MODEL" ]; then
    _claude_model="${ORCH_MODEL:-}"
    case "$_claude_model" in
        "" ) ;;
        opus|claude-opus*|claude-opus-4* ) RESOLVED_MODEL="claude-opus-4.6" ;;
        sonnet|claude-sonnet*|claude-sonnet-4* ) RESOLVED_MODEL="claude-sonnet-4" ;;
        codex ) RESOLVED_MODEL="codex" ;;
        * ) RESOLVED_MODEL="$_claude_model" ;;
    esac
fi

set -- -p --prompt-file "$PROMPT_FILE" --permission-mode "$PERM_MODE" --respect-workspace-trust false
[ -n "$RESOLVED_MODEL" ] && set -- "$@" --model "$RESOLVED_MODEL"

exec "$DEVIN_BIN" "$@"
