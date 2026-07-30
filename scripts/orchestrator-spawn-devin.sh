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
#   ORCH_SPAWN_CWD        runner-provisioned per-ticket worktree; cd here before spawn
#   ORCH_TARGET_REPO      self-hosting work TARGET (ABS-92); cwd fallback below
#                         ORCH_SPAWN_CWD
#   ORCH_OVERRIDES_DIR    agent-def overlay dir (ABS-258/ADR-A-0022); an overlay
#                         <role>.append.md is APPENDED to the role body
#   ORCH_TOOLS            per-role toolset override (§5.5). A write-free override
#                         forces read-only permissions (ABS-57 separation of duties)
#   ORCH_MODEL            per-role model, mapped to Devin's model aliases
#   ORCH_DEVIN_BIN        devin binary (default: devin)
#   ORCH_DEVIN_MODEL      explicit Devin model, wins over ORCH_MODEL
#   ORCH_DEVIN_PERMISSION_MODE  auto | accept-edits | smart | dangerous
#
# NOTE on enforcement: `--permission-mode auto` is the ONLY mechanism verified to
# actually block writes in `-p` mode (the tool call is rejected as "requires
# confirmation"). `--agent-config` `allowed-tools` / `permissions.deny` were
# measured NOT to block the write tool, so read-only seats rely on the
# permission mode, never on an agent-config allowlist.
# =============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH_HARNESS_HOME="${ORCH_HARNESS_HOME:-$REPO_ROOT}"

ROLE="${1:-${ORCH_ROLE:-}}"
TICKET="${2:-${ORCH_TICKET:-}}"
PACKET_FILE="${3:-${ORCH_PACKET_FILE:-}}"

die() { echo "spawn-devin: ERROR $*" >&2; exit 1; }

[ -n "$ROLE" ] || die "no role (arg 1 / ORCH_ROLE)"
[ -n "$TICKET" ] || die "no ticket (arg 2 / ORCH_TICKET)"

# ABS-174: underscore-prefixed defs are shared fragments (e.g. _common-rules.md),
# never spawnable roles. Reject them so a stray role label cannot resolve one.
case "$ROLE" in
    _*) die "role '$ROLE' is a shared fragment, not a spawnable role (ABS-174)" ;;
esac

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

# Composition order (parity with the Claude seam): commons -> role def -> overlay.
# ABS-174 commons live EXACTLY ONCE in _common-rules.md instead of in every def;
# ABS-258 overlays let a project refine a def without forking it (later text
# refines earlier text). Both fail open: absent file contributes nothing.
COMMON_RULES="$AGENTS_DIR/_common-rules.md"
[ -f "$COMMON_RULES" ] || COMMON_RULES=""

# Overlay dir resolution mirrors the Claude seam: explicit override, else the
# per-ticket worktree, else the self-hosting target, else this repo.
if [ -n "${ORCH_OVERRIDES_DIR:-}" ]; then
    OVERLAY_DIR="$ORCH_OVERRIDES_DIR"
elif [ -n "${ORCH_SPAWN_CWD:-}" ] && [ -d "${ORCH_SPAWN_CWD:-}" ]; then
    OVERLAY_DIR="$ORCH_SPAWN_CWD/.agentic/overrides/agents"
elif [ -n "${ORCH_TARGET_REPO:-}" ] && [ -d "${ORCH_TARGET_REPO:-}" ]; then
    OVERLAY_DIR="$ORCH_TARGET_REPO/.agentic/overrides/agents"
else
    OVERLAY_DIR="$REPO_ROOT/.agentic/overrides/agents"
fi
ROLE_OVERLAY="$OVERLAY_DIR/$ROLE.append.md"
[ -f "$ROLE_OVERLAY" ] || ROLE_OVERLAY=""

python3 - "$ROLE" "$ROLE_DEF" "$PACKET_TEMP" "$SKILL_DIR" "$PROMPT_FILE" \
         "$AGENTS_DIR" "$COMMON_RULES" "$ROLE_OVERLAY" <<'PY'
import sys

(role, role_def_path, packet_path, skill_dir, prompt_path,
 agents_dir, common_rules_path, overlay_path) = sys.argv[1:9]


def body_of(path):
    """Return the markdown body with any YAML frontmatter stripped."""
    if not path:
        return ''
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    if not text.startswith('---'):
        return text
    parts = text.split('---')
    return '---'.join(parts[2:]) if len(parts) >= 3 else text


def rewrite(text):
    """Point stable-harness references at the live skills / agents trees."""
    for prefix in ('harness/claude/skills/', 'harness/.claude/skills/',
                   'harness/devin/skills/', 'harness/.devin/skills/'):
        text = text.replace(prefix, skill_dir + '/')
    for prefix in ('harness/claude/agents/', 'harness/.claude/agents/',
                   'harness/devin/agents/', 'harness/.devin/agents/'):
        text = text.replace(prefix, agents_dir + '/')
    return text


# commons -> role def -> overlay, blank-line separated, empty parts dropped.
sections = [body_of(p).strip() for p in (common_rules_path, role_def_path, overlay_path)]
role_prompt = rewrite('\n\n'.join(s for s in sections if s))

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

# ABS-111 C9 / ABS-92: choose the cwd before exec. ORCH_SPAWN_CWD (a runner-
# provisioned per-ticket worktree) takes PRECEDENCE over ORCH_TARGET_REPO so the
# seat works inside its isolated worktree and cannot touch the main checkout.
if [ -n "${ORCH_SPAWN_CWD:-}" ]; then
    cd "$ORCH_SPAWN_CWD" || die "cannot cd to ORCH_SPAWN_CWD: $ORCH_SPAWN_CWD"
elif [ -n "${ORCH_TARGET_REPO:-}" ]; then
    cd "$ORCH_TARGET_REPO" || die "cannot cd to ORCH_TARGET_REPO: $ORCH_TARGET_REPO"
fi

DEVIN_BIN="${ORCH_DEVIN_BIN:-devin}"

# Permission mode = the seat's write privilege. `auto` auto-approves read-only
# tools and REJECTS anything needing confirmation in -p mode, so it is the
# mechanical read-only gate; `accept-edits` additionally auto-approves edits.
#
# ABS-57 separation of duties: a write-free ORCH_TOOLS override (the runner hands
# the In Review spawn a read-only toolset while reusing the write-capable
# system-architect role) MUST NOT be able to edit the code under review. A
# write-free override therefore forces `auto` regardless of role. QAS / QAS-Design
# / Security Engineer are read-only by charter and default to `auto` too.
case "${ORCH_TOOLS:-}" in
    "")             TOOLS_ALLOW_WRITE=unset ;;
    *Write*|*Edit*) TOOLS_ALLOW_WRITE=yes ;;
    *)              TOOLS_ALLOW_WRITE=no ;;
esac

if [ "$TOOLS_ALLOW_WRITE" = "no" ]; then
    DEFAULT_PERM="auto"
else
    case "$ROLE" in
        qas|qas-design|security-engineer) DEFAULT_PERM="auto" ;;
        *)                                DEFAULT_PERM="accept-edits" ;;
    esac
fi
PERM_MODE="${ORCH_DEVIN_PERMISSION_MODE:-$DEFAULT_PERM}"

# Resolve the Devin model. ORCH_DEVIN_MODEL wins, else ORCH_MODEL (which the
# orchestrator sets from the role frontmatter). Devin natively understands the
# `opus` / `sonnet` / `codex` aliases and resolves each to its CURRENT family, so
# they are passed through untouched — mapping them to a pinned version number
# would silently downgrade the seat (e.g. `opus` -> Opus 5 becoming Opus 4.6).
# An unknown model makes Devin exit 1 with the valid list, so a typo is loud.
RESOLVED_MODEL="${ORCH_DEVIN_MODEL:-${ORCH_MODEL:-}}"

set -- -p --prompt-file "$PROMPT_FILE" --permission-mode "$PERM_MODE" --respect-workspace-trust false
[ -n "$RESOLVED_MODEL" ] && set -- "$@" --model "$RESOLVED_MODEL"

# ABS-111 / ABS-157: Devin has no --max-turns, so if the runner exported a
# wall-clock timeout, wrap the CLI in timeout(1)/gtimeout(1). The orchestrator
# already runs a parallel watchdog; this is a last-resort SIGTERM/SIGKILL so
# a runaway devin process cannot outlive its budget on a direct spawn.
WALL_SEC="${ORCH_AGENT_TIMEOUT:-${ORCH_AGENT_MAX_LIFETIME:-}}"
TIMEOUT_BIN=""
if [ -n "$WALL_SEC" ] && [ "$WALL_SEC" -gt 0 ] 2>/dev/null; then
    if command -v timeout >/dev/null 2>&1; then
        TIMEOUT_BIN="timeout"
    elif command -v gtimeout >/dev/null 2>&1; then
        TIMEOUT_BIN="gtimeout"
    fi
fi

# --- SQLite database-lock resilience ----------------------------------------
# Devin CLI stores sessions in a SQLite database (~/.local/share/devin/cli/
# sessions.db) with WAL mode and a 1-second busy_timeout. When the orchestrator
# spawns sessions in rapid succession, the previous session's WAL checkpoint
# or connection cleanup can exceed the 1-second busy_timeout, causing:
#   Error: database is locked
# This section:
#   1. Cleans up stale session lock files from crashed sessions
#   2. Waits for any in-flight Devin process to release the DB
#   3. Retries the spawn with exponential backoff on "database is locked" errors
DEVIN_DB="${HOME}/.local/share/devin/cli/sessions.db"
DEVIN_LOCK_DIR="${HOME}/.local/share/devin/cli/session_locks"
DB_LOCK_MAX_RETRIES="${ORCH_DEVIN_DB_LOCK_RETRIES:-3}"
DB_LOCK_BASE_DELAY="${ORCH_DEVIN_DB_LOCK_BASE_DELAY:-2}"   # seconds
DB_LOCK_MAX_DELAY="${ORCH_DEVIN_DB_LOCK_MAX_DELAY:-15}"    # seconds cap

# Clean up stale session lock files from crashed sessions.
# These accumulate when Devin CLI crashes (e.g. timeout kill) and never cleans up.
if [ -d "$DEVIN_LOCK_DIR" ]; then
    find "$DEVIN_LOCK_DIR" -name "*.lock" -mmin +5 -delete 2>/dev/null || true
fi

# Wait for any in-flight Devin process to release the DB connection.
# A short delay lets the previous session's SQLite WAL checkpoint complete.
_devin_pids=$(pgrep -f "devin.*-p.*--prompt-file" 2>/dev/null || true)
if [ -n "$_devin_pids" ]; then
    # Another Devin print-mode session is running — wait briefly for it to finish.
    _wait_sec=0
    while [ -n "$_devin_pids" ] && [ "$_wait_sec" -lt "$DB_LOCK_MAX_DELAY" ]; do
        sleep 1
        _wait_sec=$((_wait_sec + 1))
        _devin_pids=$(pgrep -f "devin.*-p.*--prompt-file" 2>/dev/null || true)
    done
    # Brief settle delay for WAL checkpoint after the process exits.
    sleep 1
fi

# Retry wrapper: re-invoke devin with exponential backoff on "database is locked".
# The orchestrator's own retry (do_spawn_action) is coarser (1 retry, no backoff);
# this inner retry handles the specific SQLite contention case with finer granularity.
# stderr is captured to a temp file so we can inspect it for the lock error without
# corrupting the stdout handoff record that the orchestrator parses.
_db_lock_errfile="$(mktemp "$TMPDIR/devin-db-lock.XXXXXX")"
trap 'rm -f "$PACKET_TEMP" "$PROMPT_FILE" "$_db_lock_errfile"' EXIT
_db_lock_attempt=0
while true; do
    # Disable set -e for the devin invocation so we can capture the exit code
    # and retry on "database is locked" errors.
    if [ -n "$TIMEOUT_BIN" ]; then
        # -s TERM: ask politely; -k 60: SIGKILL if still alive 60s after TERM.
        set +e
        "$TIMEOUT_BIN" -s TERM -k 60 "$WALL_SEC" "$DEVIN_BIN" "$@" 2>"$_db_lock_errfile"
        _rc=$?
        set -e
    else
        set +e
        "$DEVIN_BIN" "$@" 2>"$_db_lock_errfile"
        _rc=$?
        set -e
    fi

    # Check if the failure was due to "database is locked"
    if [ "$_rc" -ne 0 ] && [ "$_db_lock_attempt" -lt "$DB_LOCK_MAX_RETRIES" ]; then
        if grep -q "database is locked" "$_db_lock_errfile" 2>/dev/null; then
            _delay=$(( DB_LOCK_BASE_DELAY * (2 ** _db_lock_attempt) ))
            [ "$_delay" -gt "$DB_LOCK_MAX_DELAY" ] && _delay="$DB_LOCK_MAX_DELAY"
            echo "spawn-devin: database is locked (attempt $((_db_lock_attempt + 1))/$((_db_lock_attempt + 1 + DB_LOCK_MAX_RETRIES))); retrying in ${_delay}s..." >&2
            cat "$_db_lock_errfile" >&2
            sleep "$_delay"
            _db_lock_attempt=$((_db_lock_attempt + 1))
            # Clean up any stale locks before retrying
            if [ -d "$DEVIN_LOCK_DIR" ]; then
                find "$DEVIN_LOCK_DIR" -name "*.lock" -mmin +1 -delete 2>/dev/null || true
            fi
            # Wait for any other in-flight Devin process before retrying
            _devin_pids=$(pgrep -f "devin.*-p.*--prompt-file" 2>/dev/null || true)
            if [ -n "$_devin_pids" ]; then
                _wait_sec=0
                while [ -n "$_devin_pids" ] && [ "$_wait_sec" -lt "$DB_LOCK_MAX_DELAY" ]; do
                    sleep 1
                    _wait_sec=$((_wait_sec + 1))
                    _devin_pids=$(pgrep -f "devin.*-p.*--prompt-file" 2>/dev/null || true)
                done
                sleep 1
            fi
            : > "$_db_lock_errfile"
            continue
        fi
    fi

    # Flush captured stderr to our stderr before exiting
    cat "$_db_lock_errfile" >&2 2>/dev/null || true
    exit "$_rc"
done
