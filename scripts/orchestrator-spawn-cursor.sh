#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Cursor spawn adapter — EVALUATION STATUS (ABS-122 spike, NOT a default)
# =============================================================================
# Implements the §3.1 provider seam contract on Cursor's headless agent CLI
# (`cursor agent -p --output-format json`):
#   "$0" <role> <ticket-id> <packet-file>
#     stdin:  the context packet
#     stdout: the agent's final structured result incl. the handoff record
#     exit code: 0 on success
# Wire a seat onto it via ORCH_SPAWN_CMD_<ROLE> (ABS-122) — Claude remains the
# default provider (operator decision: Cursor is a quota overflow valve).
#
# VERIFIED against cursor agent 2025.x CLI --help (see the ABS-122 evaluation
# report): headless print mode, JSON output, --model, --resume [chatId],
# --workspace, sandbox flags all exist.
# UNVERIFIED (blocked on authentication — `cursor agent login` is a human-only
# credential step, ADR-A-0004): the JSON result field names (chat id + result
# text extraction below are BEST-EFFORT patterns) and the actual resume
# semantics. Do NOT flip a seat to this adapter before a human has run the
# live verification in the evaluation report.
#
# Differences vs the Claude adapter, by design:
#   - No --agents equivalent: the role definition's PROMPT BODY is prepended
#     to the packet as the instruction preamble; `tools:` frontmatter has no
#     enforcement surface here — worktree isolation (C9) carries the safety
#     (see report §d for the residual-risk assessment).
#   - No settings.local.json semantics: sandbox mode is Cursor's own
#     (ORCH_CURSOR_FORCE=1 opts into --force; default keeps the sandbox).
#   - Model names are Cursor's (e.g. sonnet-4-thinking); ORCH_MODEL is passed
#     through verbatim — the Claude-side sonnet pin does NOT apply here.
# =============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH_HARNESS_HOME="${ORCH_HARNESS_HOME:-$REPO_ROOT}"

ROLE="${1:-${ORCH_ROLE:-}}"
TICKET="${2:-${ORCH_TICKET:-}}"
PACKET_FILE="${3:-${ORCH_PACKET_FILE:-}}"

if [ -n "${ORCH_AGENTS_DIR:-}" ]; then
    AGENTS_DIR="$ORCH_AGENTS_DIR"
elif [ -d "$ORCH_HARNESS_HOME/harness/claude/agents" ]; then
    AGENTS_DIR="$ORCH_HARNESS_HOME/harness/claude/agents"
elif [ -d "$ORCH_HARNESS_HOME/harness/.claude/agents" ]; then
    # Pre-v2.23.0 stable checkouts still use the dotted namespace.
    AGENTS_DIR="$ORCH_HARNESS_HOME/harness/.claude/agents"
else
    AGENTS_DIR="$ORCH_HARNESS_HOME/.claude/agents"
fi
CURSOR_BIN="${ORCH_CURSOR_BIN:-cursor}"

die() { echo "spawn-cursor: ERROR $*" >&2; exit 1; }

[ -n "$ROLE" ] || die "no role (arg 1 / ORCH_ROLE)"
[ -n "$TICKET" ] || die "no ticket (arg 2 / ORCH_TICKET)"

ROLE_DEF="$AGENTS_DIR/$ROLE.md"
[ -f "$ROLE_DEF" ] || die "no agent definition for role '$ROLE' at $ROLE_DEF"

# Packet: stdin wins (seam contract), file fallback.
PACKET="$(cat 2>/dev/null || true)"
[ -n "$PACKET" ] || { [ -n "$PACKET_FILE" ] && PACKET="$(cat "$PACKET_FILE" 2>/dev/null || true)"; }

# Role prompt = the def body after the frontmatter (no --agents equivalent).
ROLE_PROMPT="$(awk 'BEGIN{fm=0} /^---$/{fm++; next} fm>=2{print}' "$ROLE_DEF")"

PROMPT="You are the '$ROLE' seat of this repo's orchestrated agent team.
$ROLE_PROMPT

=== CONTEXT PACKET ===
$PACKET

End your reply with the '## Handoff' record exactly as the packet instructs."

set -- agent -p "$PROMPT" --output-format json --trust
[ -n "${ORCH_MODEL:-}" ] && set -- "$@" --model "$ORCH_MODEL"
[ -n "${ORCH_SPAWN_CWD:-}" ] && set -- "$@" --workspace "$ORCH_SPAWN_CWD"
# Resume equivalent (--resume <chatId>) — semantics UNVERIFIED, see header.
[ -n "${ORCH_RESUME_SESSION_ID:-}" ] && set -- "$@" --resume "$ORCH_RESUME_SESSION_ID"
[ "${ORCH_CURSOR_FORCE:-0}" = "1" ] && set -- "$@" --force

exec "$CURSOR_BIN" "$@"
