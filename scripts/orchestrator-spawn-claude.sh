#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Default ORCH_SPAWN_CMD binding — Claude Code headless spawn (spec §3)
# =============================================================================
# The shipped default spawn seam for scripts/orchestrator.sh. Implements the
# provider contract (spec ABS-36 §3.1):
#
#   "$ORCH_SPAWN_CMD" <role> <ticket-id> <packet-file>
#     stdin:  the context packet (§4)          (also written to <packet-file>)
#     env:    ORCH_ROLE, ORCH_TICKET, ORCH_PACKET_FILE
#     stdout: the agent's final structured result incl. the handoff record (§6)
#     exit 0: success   exit !0: spawn failure (runner retries once then escalates)
#
# It materializes the repo's .claude/agents/<role>.md frontmatter+body into the
# --agents JSON shape ({name:{description, prompt, tools}}) and invokes the
# Claude Code CLI with ONLY the flags the spec verified against the CLI docs.
# No flag is invented here.
#
# Tests DO NOT use this script — they set ORCH_SPAWN_CMD to a stub. This is the
# production binding; it requires a real `claude` on PATH and is never run in CI.
#
# Environment:
#   ORCH_ROLE / $1        role name (matches .claude/agents/<role>.md)
#   ORCH_TICKET / $2      ticket id (informational)
#   ORCH_PACKET_FILE / $3 packet path (packet also arrives on stdin)
#   ORCH_MODEL            per-role model (default: from role frontmatter or CLI default)
#   ORCH_MAX_TURNS        hard turn ceiling (default: 25, ABS-150)
#   ORCH_AGENTS_DIR       agent-def dir (default: $ORCH_HARNESS_HOME/harness/claude/agents
#                         when that namespace dir exists, else the pre-v2.23.0
#                         $ORCH_HARNESS_HOME/harness/.claude/agents, else the
#                         legacy $ORCH_HARNESS_HOME/.claude/agents — ABS-96 fallback)
#   ORCH_HARNESS_HOME     stable/harness root (ABS-92, default: this script's repo)
#   ORCH_TARGET_REPO      self-hosting work TARGET (ABS-92): when set, cwd = this
#                         repo before exec so the spawn works in the dev repo
#   ORCH_SPAWN_CWD        runner-provisioned per-ticket worktree (ABS-111 C9):
#                         when set (absolute, existing dir) cwd = this dir before
#                         exec, taking PRECEDENCE over ORCH_TARGET_REPO. Purpose:
#                         the runner gives each ticket its own git worktree so the
#                         agent physically cannot touch the main checkout. Unset ->
#                         unchanged (ORCH_TARGET_REPO / no-cd behavior stands).
#   ORCH_OVERRIDES_DIR    agent-def overlay dir (ABS-258/ADR-A-0022, default:
#                         <target>/.agentic/overrides/agents, where <target> is
#                         ORCH_SPAWN_CWD -> ORCH_TARGET_REPO -> this script's repo).
#                         An overlay <role>.append.md is APPENDED to the role body
#                         at spawn time so a project can customize a def without
#                         forking it. Absent -> byte-identical to no-overlay.
#   ORCH_RESUME_SESSION_ID resume an existing session instead of a fresh one
#                         (ABS-111 A2): when set, invoke `claude -p --resume <id>`
#                         and OMIT --agents/--agent (the resumed session already
#                         carries its agent definition; verified against
#                         `claude -p --help` — --resume needs only the session id,
#                         --max-turns/--permission-mode/--output-format still apply,
#                         and the packet arrives on stdin as a new prompt). Use for
#                         rework / re-review / handoff-repair resume (ADR-A-0002
#                         reading: fresh-per-task means fresh until Acceptance, so a
#                         bounce-back reuses the same session). Unset -> fresh spawn.
#   ORCH_CLAUDE_BIN       claude binary (default: claude)
#   ORCH_SKILLS_DIR       LIVE skills dir the seat prompt's skill references are
#                         rewritten to (ABS-535, default: $ORCH_HARNESS_HOME/.claude/skills
#                         when that dir exists, else no rewrite). Agent-def bodies
#                         cite skill files as `harness/claude/skills/<name>` — the
#                         EDITABLE SOURCE namespace, which per the governor-pin
#                         model (ABS-94) is INERT: the live harness is the
#                         generated .claude/. In self-hosting a seat resolving
#                         those citations against $ORCH_HARNESS_HOME reads
#                         <stable>/harness/claude/skills/*, gets a permission
#                         denial, and the denial poisons the session (not stored
#                         -> every follow-up spawn of the station starts cold).
#                         The seam therefore rewrites `harness/claude/skills/<name>`
#                         (a concrete skill reference — the bare namespace and
#                         glob forms like `harness/claude/skills/*` in the
#                         mirror-parity rule are left alone) to $ORCH_SKILLS_DIR/<name>
#                         in the composed prompt, and allowlists READS under
#                         $ORCH_SKILLS_DIR so the rewritten reference is loadable
#                         under --permission-mode dontAsk (read-only: no --add-dir,
#                         a seat must never be able to WRITE the governing skills).
#   ORCH_AGENTS_ARG_MAX   argv-size gate for the --agents JSON (default: 24000,
#                         ABS-251). Windows' CreateProcess caps a command line at
#                         ~32 KB, so passing a large agent def inline crashes the
#                         spawn outright (consumer repro: system-architect, 37.6 KB).
#                         Above the gate the seam OMITS the inline --agents and
#                         instead MATERIALIZES the same composed+rewritten def
#                         (ABS-535 skill-path rewrite + ABS-174 commons) as a
#                         markdown def under a throwaway --plugin-dir, selected by
#                         a unique `--agent <role>__seat`. The big def travels in a
#                         FILE so argv stays tiny (Windows-safe) while the seat
#                         material is fully rewritten (PILOT-23). Set to a huge
#                         value to disable the gate.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ABS-92: agent defs are read from the HARNESS (stable), the work TARGET is a
# separate dev repo. Both default to this script's own repo, so with neither seam
# set the resolution is byte-for-byte identical to before (isolation is agent-defs
# only in Phase 1 — PATH_DECISION 1).
ORCH_HARNESS_HOME="${ORCH_HARNESS_HOME:-$REPO_ROOT}"

ROLE="${1:-${ORCH_ROLE:-}}"
TICKET="${2:-${ORCH_TICKET:-}}"
PACKET_FILE="${3:-${ORCH_PACKET_FILE:-}}"

# ABS-96: agent defs are sourced from the SHIPPED-harness namespace
# ($ORCH_HARNESS_HOME/harness/claude/agents; pre-v2.23.0 stable checkouts still
# ship harness/.claude/agents) when it exists, else the legacy
# live path ($ORCH_HARNESS_HOME/.claude/agents). An explicit ORCH_AGENTS_DIR
# always wins. The stable checkout at the current release tag (v2.16.0) has no
# harness/ dir, so the fallback keeps that (and every consuming project) working
# byte-for-byte until a future stable tag ships the namespace.
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

# ABS-535: LIVE skills dir for the skill-reference rewrite (see header). The
# governing checkout's live harness is its generated .claude/ (ABS-94), so the
# live skill source is $ORCH_HARNESS_HOME/.claude/skills — never
# harness/claude/skills, which is the inert editable SOURCE. Absent (pre-ABS-94
# layouts) -> empty -> no rewrite, no extra allow rule: byte-identical spawn.
if [ -n "${ORCH_SKILLS_DIR:-}" ]; then
    SKILLS_DIR="$ORCH_SKILLS_DIR"
elif [ -d "$ORCH_HARNESS_HOME/.claude/skills" ]; then
    SKILLS_DIR="$ORCH_HARNESS_HOME/.claude/skills"
else
    SKILLS_DIR=""
fi

CLAUDE_BIN="${ORCH_CLAUDE_BIN:-claude}"
MAX_TURNS="${ORCH_MAX_TURNS:-25}"  # ABS-150: raised from 12

die() { echo "spawn-claude: ERROR $*" >&2; exit 1; }

[ -n "$ROLE" ] || die "role is required (\$1 or ORCH_ROLE)"

# ABS-174: underscore-prefixed defs are shared/partial fragments (e.g.
# _common-rules.md), never spawnable roles. Reject them explicitly so a stray
# role label can never resolve one as an agent.
case "$ROLE" in
    _*) die "role '$ROLE' is not spawnable (underscore-prefixed defs are shared fragments)" ;;
esac

ROLE_DEF="$AGENTS_DIR/$ROLE.md"
[ -f "$ROLE_DEF" ] || die "agent definition not found: $ROLE_DEF"

# ABS-258 / ADR-A-0022: project-owned agent-def OVERLAY. A project customizes a
# shipped def by ADDING .agentic/overrides/agents/<role>.append.md instead of
# EDITING (forking) the def. The overlay body is appended after the role body at
# spawn time and the on-disk def is never touched, so it keeps upstream bytes and
# the migration driver classifies it REPLACE, never CONFLICT — which is what makes
# the recurring "replace body, re-append project section" ritual disappear.
# Resolved against the work TARGET (the project), NOT ORCH_HARNESS_HOME (where the
# defs come from) — the ABS-92 self-hosting split; in a plain consumer project the
# two are the same repo, so this is invisible.
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

# ABS-224: seat-context marker. The pre-commit local-main guard
# (.git/hooks/pre-commit) reads ORCH_SEAT to distinguish a seat commit (guarded
# on the protected main branch) from a human commit (never guarded). Exported so
# it reaches the claude process and every Bash-tool subprocess a seat runs. Also
# forward the kill switch so a seat's git honours ORCH_PROTECT_LOCAL_MAIN=0.
export ORCH_SEAT="$ROLE"
[ -n "${ORCH_TICKET:-}" ] && export ORCH_TICKET
export ORCH_PROTECT_LOCAL_MAIN="${ORCH_PROTECT_LOCAL_MAIN:-1}"
# ABS-243: forward the foreign-process kill-guard switch (default ON) so the
# PreToolUse Bash guard (.claude/hooks/pre-bash-kill-guard.sh) is active in every
# Bash-tool subprocess a seat runs; ORCH_KILL_GUARD=0 restores legacy behavior.
# The guard keys off the ORCH_SEAT marker exported above (human shells, which
# carry no marker, are never guarded).
export ORCH_KILL_GUARD="${ORCH_KILL_GUARD:-1}"
# ABS-272: forward the shared-stash guard switch (default ON) so the PreToolUse
# Bash guard (.claude/hooks/pre-bash-stash-guard.sh) is active in every Bash-tool
# subprocess a seat runs. refs/stash is ONE stack shared by ALL worktrees, so a
# seat's stash/pop eats a concurrently running sibling seat's uncommitted work.
# ORCH_STASH_GUARD=0 restores legacy behavior. Keys off the ORCH_SEAT marker
# exported above (human shells, which carry no marker, are never guarded).
export ORCH_STASH_GUARD="${ORCH_STASH_GUARD:-1}"

# --- Materialize .claude/agents/<role>.md -> --agents JSON --------------------
# The agent def is YAML frontmatter (name/description/tools/model) + a markdown
# body (the role prompt). The docs' --agents shape uses the same field names as
# subagent frontmatter plus a `prompt` field carrying the body. We emit:
#   {"<name>": {"description": "...", "prompt": "<body>", "tools": [...]}}
# JSON is assembled with awk (zero-dependency, bash 3.2 / BSD safe) with proper
# string escaping for the body.
build_agents_json() {
    # ABS-535-follow (PILOT-23): this composer emits EITHER the --agents JSON
    # (emit="json", default) OR a materialized on-disk agent def as markdown
    # (emit="def", used by the argv-size fallback below so the fallback path gets
    # the SAME rewrite_skills filter + commons prepend as the inline path). $2 is
    # the frontmatter `name:` for the def (a UNIQUE selector so a same-named
    # project agent in the seat cwd cannot shadow it).
    local emit="${1:-json}"
    local def_name="${2:-}"
    # Per-role tools override (§5.5): honor an explicit ORCH_TOOLS list, else the
    # role's own `tools:` frontmatter. Mirrors the ORCH_MODEL override below — it
    # lets the runner hand a review/validate gate a narrower (read-only) toolset
    # than the reused role carries for its other duties, so a reviewer can only
    # approve or bounce, never edit the code under review. Accepts a YAML flow
    # list or a bare comma-separated list ("[Read, Bash]" or "Read, Bash").
    #
    # ABS-174: prepend the shared common-rules body (frontmatter stripped) ahead
    # of the role body, so cross-seat rules live EXACTLY ONCE in _common-rules.md
    # instead of in every def. ABS-258: append the project overlay body AFTER the
    # role body (later text refines earlier text). Composition order is therefore
    # commons -> role def -> overlay, and awk keys off the ROLE DEF's file index
    # (ridx) for which file supplies name/description/tools — NOT "the last file",
    # since the overlay now sits after it and must contribute body text ONLY.
    # FAIL-OPEN both ways: absent commons -> cbody empty; absent overlay -> obody
    # empty; with neither, the emitted JSON is byte-identical to the pre-ABS-174
    # single-file behavior.
    local common_rules="$AGENTS_DIR/_common-rules.md"
    local -a files=()
    [ -f "$common_rules" ] && files+=("$common_rules")
    files+=("$ROLE_DEF")
    local ridx=${#files[@]}   # role def index (1-based): the ONLY frontmatter source
    if [ -f "$ROLE_OVERLAY" ]; then
        files+=("$ROLE_OVERLAY")
        echo "spawn-claude: NOTICE agent-def overlay applied: $ROLE_OVERLAY" >&2
        # D2: append-only, BODY-only. An overlay's frontmatter is stripped and
        # ignored — it cannot widen `tools` (the seat's privilege grant), change
        # the model, or rename the seat. Say so loudly rather than let the author
        # believe a `tools:` line in their overlay took effect.
        local first_line=""
        IFS= read -r first_line < "$ROLE_OVERLAY" || true
        if [ "$first_line" = "---" ]; then
            echo "spawn-claude: NOTICE overlay $ROLE_OVERLAY carries frontmatter — stripped and ignored (body-only; it cannot set tools/model/name — use ORCH_TOOLS/ORCH_MODEL)" >&2
        fi
    fi
    awk -v tools_override="${ORCH_TOOLS:-}" -v ridx="$ridx" -v skills_dir="$SKILLS_DIR" \
        -v emit="$emit" -v def_name="$def_name" '
        # ABS-535: rewrite CONCRETE skill references — `harness/claude/skills/<name>`
        # where <name> starts with a skill-name character — to the LIVE skills dir
        # (<harness>/.claude/skills/<name>). harness/claude/ is the inert editable
        # SOURCE (ABS-94 governor-pin); resolving a skill read there yields a
        # permission denial that poisons the seat session. Glob/namespace mentions
        # (e.g. the mirror-parity rule citing `harness/claude/skills/*`, whose next
        # char is `*`) are about EDITING the source and are deliberately left
        # untouched. index/substr instead of gsub so the replacement path is never
        # interpreted for `&`/backslash. skills_dir empty -> identity (fail-open).
        function rewrite_skills(s,   pfx, out, i, c) {
            if (skills_dir == "") return s
            pfx = "harness/claude/skills/"
            out = ""
            while ((i = index(s, pfx)) > 0) {
                c = substr(s, i + length(pfx), 1)
                if (c ~ /[A-Za-z0-9._-]/) out = out substr(s, 1, i - 1) skills_dir "/"
                else                      out = out substr(s, 1, i - 1) pfx
                s = substr(s, i + length(pfx))
            }
            return out s
        }
        function jesc(s,   r) {
            r = s
            gsub(/\\/, "\\\\", r)
            gsub(/"/, "\\\"", r)
            gsub(/\t/, "\\t", r)
            gsub(/\r/, "", r)
            return r
        }
        BEGIN { fidx=0; fm=0; name=""; desc=""; tools=""; body=""; cbody=""; obody="";
                cbody_raw=""; body_raw=""; obody_raw=""; tf="" }
        # Per-file frontmatter state: reset at the first line of every input file
        # (FNR==1), so commons / role def / overlay are parsed independently.
        FNR == 1 { fidx++; fm = 0 }
        FNR == 1 && $0 == "---" { fm = 1; next }
        fm == 1 && $0 == "---" { fm = 2; next }
        fm == 1 {
            # ONLY the role def (fidx == ridx) supplies name/description/tools.
            # The commons file and the overlay contribute body text only — an
            # overlay `tools:` line is therefore stripped here, never merged
            # (ADR-A-0022 D2: an overlay cannot widen the seat privilege grant).
            if (fidx == ridx) {
                if ($0 ~ /^name:[[:space:]]*/)        { s=$0; sub(/^name:[[:space:]]*/,"",s); name=s; next }
                if ($0 ~ /^description:[[:space:]]*/) { s=$0; sub(/^description:[[:space:]]*/,"",s); desc=s; next }
                if ($0 ~ /^tools:[[:space:]]*/)       { s=$0; sub(/^tools:[[:space:]]*/,"",s); tools=s; next }
            }
            next
        }
        # Body lines: everything not inside a frontmatter block. fm==2 is "after
        # frontmatter"; fm==0 is "file had none at all" — the common shape for an
        # overlay, which must NOT be silently dropped for lacking frontmatter.
        fm != 1 {
            # Escape each body line for JSON, then join with the literal two-char
            # sequence backslash-n so the emitted string is valid JSON (no raw
            # control characters). Before the role def -> cbody (commons), the
            # role def -> body, after it -> obody (overlay). ABS-535: skill
            # references are rewritten to the LIVE skills dir first, in every
            # bucket (commons and overlay cite skills too).
            line = rewrite_skills($0)
            # json bucket = JSON-escaped, \n-joined; def bucket = raw + real
            # newline (the markdown fallback def loaded by the CLI verbatim).
            if      (fidx <  ridx) { cbody = cbody jesc(line) "\\n"; cbody_raw = cbody_raw line "\n" }
            else if (fidx == ridx) { body  = body  jesc(line) "\\n"; body_raw  = body_raw  line "\n" }
            else                   { obody = obody jesc(line) "\\n"; obody_raw = obody_raw line "\n" }
        }
        END {
            if (name == "") name = "ROLE_NAME_PLACEHOLDER"
            # tools frontmatter is a YAML flow list "[Read, Write, ...]" — turn
            # it into a JSON array. Bare/empty tools -> omit (inherit defaults).
            tj = ""
            t = (tools_override != "") ? tools_override : tools
            gsub(/^\[/, "", t); gsub(/\]$/, "", t)
            n = split(t, arr, ",")
            first = 1
            for (i = 1; i <= n; i++) {
                v = arr[i]
                gsub(/^[ \t]+/, "", v); gsub(/[ \t]+$/, "", v)
                if (v == "" || v == "*") continue
                if (first) { tj = "\"" jesc(v) "\""; tf = v;            first = 0 }
                else       { tj = tj ", \"" jesc(v) "\""; tf = tf ", " v }
            }
            # emit="def": a materialized markdown agent def (frontmatter + raw,
            # rewritten body incl. commons) for the argv-size fallback. Selector
            # name = def_name (unique) so a same-named project agent in the seat
            # cwd cannot shadow it (CLI resolves the project agent over a plugin
            # agent of the same name). tools = the same resolved list the JSON
            # would carry (override-or-frontmatter), so the fallback seat grant
            # matches the inline path.
            if (emit == "def") {
                dn = (def_name != "") ? def_name : name
                printf "---\n"
                printf "name: %s\n", dn
                if (desc != "") printf "description: %s\n", desc
                if (tf   != "") printf "tools: [%s]\n", tf
                printf "---\n"
                rprompt = cbody_raw
                if (body_raw  != "") rprompt = (rprompt != "") ? rprompt "\n" body_raw  : body_raw
                if (obody_raw != "") rprompt = (rprompt != "") ? rprompt "\n" obody_raw : obody_raw
                printf "%s", rprompt
                exit
            }
            # prompt = commons body + role body + overlay body, each pair separated
            # by a blank line, empty buckets contributing nothing. Fail-open: with
            # no commons AND no overlay, prompt == role body, byte-identical to the
            # pre-ABS-174 single-file emission.
            prompt = cbody
            if (body  != "") prompt = (prompt != "") ? prompt "\\n" body  : body
            if (obody != "") prompt = (prompt != "") ? prompt "\\n" obody : obody
            # name/desc still need escaping; bodies were escaped line-by-line above.
            printf "{\"%s\": {\"description\": \"%s\", \"prompt\": \"%s\"",
                jesc(name), jesc(desc), prompt
            if (tj != "") printf ", \"tools\": [%s]", tj
            printf "}}\n"
        }
    ' "${files[@]}"
}

AGENTS_JSON="$(build_agents_json)"

# --- Per-role model (§3.2): honor an explicit ORCH_MODEL, else the role's own
# `model:` frontmatter, else let the CLI default stand (omit --model). ---------
MODEL="${ORCH_MODEL:-}"
if [ -z "$MODEL" ]; then
    MODEL="$(awk -F': ' '
        /^---$/ { fm++; next }
        fm == 1 && $1 == "model" { print $2; exit }
        fm >= 2 { exit }
    ' "$ROLE_DEF")"
fi

# --- Sonnet alias pin: the bare `sonnet` alias resolves to Sonnet 5 in the
# Claude CLI, which currently has a token-usage regression (frequently exceeds
# Fable 5). Until that is fixed, pin every Sonnet-family request to Sonnet 4.6
# explicitly. Single chokepoint: covers the role `model:` frontmatter AND the
# ORCH_MODEL / ORCH_MODEL_<ROLE> / ticket-label paths, since all resolve into
# $MODEL above. An explicit `claude-sonnet-4-6` (or any non-Sonnet model) is
# passed through untouched. Remove this block once Sonnet 5 usage is acceptable.
case "$MODEL" in
    sonnet|sonnet-5|sonnet5|claude-sonnet-5|claude-sonnet-5-*)
        echo "spawn-claude: NOTICE pinning model '$MODEL' -> claude-sonnet-4-6 (Sonnet 5 token regression)" >&2
        MODEL="claude-sonnet-4-6"
        ;;
esac

# --- Invoke Claude Code headless (spec §3.2) — ONLY spec-listed flags ---------
# Packet arrives on stdin (also written to $PACKET_FILE by the runner).
# NOTE: --bare is deliberately NOT passed — it skips keychain reads, so on
# macOS (credentials in Keychain) every spawn fails with "Not logged in"
# (found in the first live run, 2026-07-04). Opt back in via ORCH_CLAUDE_BARE=1
# only where credentials are file/env-based.
set -- -p
[ "${ORCH_CLAUDE_BARE:-0}" = "1" ] && set -- "$@" --bare
# ABS-111 A2: resume seam. With ORCH_RESUME_SESSION_ID set we resume the existing
# session via `--resume <id>` and OMIT --agents/--agent — the session already
# holds its agent definition, so re-passing them is redundant (verified against
# `claude -p --help`: --resume takes only the session id; --max-turns,
# --permission-mode, --output-format remain valid alongside it). The packet still
# arrives on stdin as the new prompt. Unset -> the exact fresh-spawn flags below.
# ABS-251 argv-size gate: Windows' CreateProcess caps the whole command line at
# ~32 KB, so a large agent def passed inline via --agents kills the spawn before
# the CLI even starts (consumer repro: system-architect def, 37.6 KB). Above the
# gate we OMIT the inline --agents and hand the CLI the SAME composed+rewritten
# def via a throwaway --plugin-dir (PILOT-23): the def content lives in a FILE, so
# argv stays under the Windows limit, and — unlike the pre-PILOT-23 `--agent
# <role>` fallback that loaded the UN-rewritten on-disk def and skipped both the
# ABS-535 skill-path rewrite and the ABS-174 commons prepend — the fallback seat
# now gets byte-for-byte the same rewritten material as the inline path. Below the
# gate (macOS/Linux with today's defs) the flag sequence is byte-identical to before.
# PILOT-55 / ABS-566: the gate is PLATFORM-DEPENDENT. The constraint it defends is
# the WINDOWS CreateProcess limit (~32 KB for the whole command line); on POSIX
# `getconf ARG_MAX` is the whole argv+envp limit and is >= 256 KB (macOS 262144,
# Linux ~1–2 MB). Forcing the 24000 B fallback on POSIX was grundlos: it made the
# --agent fallback the NORMALFALL for most roles (13 of 17 measured by
# scripts/agent-prompt-size.sh) and correlates with the
# Pilot-4 SESSION-POISONED and Pilot-5 error_max_turns series. So on POSIX the
# inline --agents path is the norm again (default = getconf ARG_MAX minus a 32 KB
# headroom for env + the other flags, floored at the Windows-safe 24000). Windows
# keeps 24000. ORCH_AGENTS_ARG_MAX still overrides both — the unchanged operator lever.
if [ -n "${ORCH_AGENTS_ARG_MAX:-}" ]; then
    AGENTS_ARG_MAX="$ORCH_AGENTS_ARG_MAX"
else
    case "$(uname -s 2>/dev/null || echo unknown)" in
        MINGW*|MSYS*|CYGWIN*|Windows_NT)
            AGENTS_ARG_MAX=24000 ;;
        *)
            _sys_arg_max="$(getconf ARG_MAX 2>/dev/null || echo 262144)"
            case "$_sys_arg_max" in ''|*[!0-9]*) _sys_arg_max=262144 ;; esac
            AGENTS_ARG_MAX=$(( _sys_arg_max - 32768 ))
            [ "$AGENTS_ARG_MAX" -lt 24000 ] && AGENTS_ARG_MAX=24000 ;;
    esac
fi
if [ -n "${ORCH_RESUME_SESSION_ID:-}" ]; then
    set -- "$@" --resume "$ORCH_RESUME_SESSION_ID"
elif [ "${#AGENTS_JSON}" -gt "$AGENTS_ARG_MAX" ]; then
    echo "spawn-claude: NOTICE --agents JSON is ${#AGENTS_JSON}B > ORCH_AGENTS_ARG_MAX (${AGENTS_ARG_MAX}B) -> falling back to a plugin-materialized def for --agent $ROLE" >&2
    # ABS-535-follow (PILOT-23): the OLD fallback passed `--agent $ROLE`, which
    # made the CLI load the role's UN-rewritten on-disk def from the seat cwd
    # (<cwd>/.claude/agents/$ROLE.md) — so the ABS-535 skill-path rewrite (and the
    # ABS-174 commons prepend) were skipped and every large role-def (be-developer,
    # po-agent, tech-writer) still poisoned the session on skill-file denials.
    # FIX: materialize the SAME composed+rewritten def build_agents_json produces,
    # as a markdown def under a throwaway --plugin-dir, and select it by a UNIQUE
    # name (a same-named project agent in the cwd would otherwise shadow a plugin
    # agent). The big def content travels in a FILE, so argv stays tiny — the very
    # property the Windows CreateProcess gate needs — while the seat material is
    # fully rewritten. Fail-open unchanged: no live skills dir -> identity rewrite.
    FALLBACK_AGENT="${ROLE}__seat"
    PLUGIN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/orch-seat-plugin.XXXXXX")" || die "cannot create fallback plugin dir"
    mkdir -p "$PLUGIN_DIR/.claude-plugin" "$PLUGIN_DIR/agents"
    printf '{"name": "orch-seat", "version": "0.0.0", "description": "spawn-materialized seat def (ABS-535 fallback rewrite, PILOT-23)"}\n' \
        > "$PLUGIN_DIR/.claude-plugin/plugin.json"
    build_agents_json def "$FALLBACK_AGENT" > "$PLUGIN_DIR/agents/$ROLE.md"
    set -- "$@" --plugin-dir "$PLUGIN_DIR" --agent "$FALLBACK_AGENT"
    # Tool-narrowing parity (AC2): the materialized def now bakes the SAME resolved
    # (override-or-frontmatter) tools the inline JSON would carry, so a read-only
    # ORCH_TOOLS override already yields a write-free def. The explicit
    # --disallowedTools below is a belt-and-suspenders backstop kept for behavioral
    # parity with the pre-PILOT-23 fallback (and the ABS-251 AC2 contract): when the
    # override is write-free, deny the write tools so the seat stays read-only.
    case "${ORCH_TOOLS:-}" in
        "")             : ;;  # no override -> def tools ARE what the JSON would have carried
        *Write*|*Edit*) : ;;  # override grants writes -> nothing to narrow
        *)              set -- "$@" --disallowedTools "Write,Edit,NotebookEdit" ;;
    esac
else
    set -- "$@" \
        --agents "$AGENTS_JSON" \
        --agent "$ROLE"
fi
set -- "$@" \
    --max-turns "$MAX_TURNS" \
    --permission-mode dontAsk \
    --output-format json
[ -n "$MODEL" ] && set -- "$@" --model "$MODEL"

# ABS-123: a seat whose resolved toolset includes the Skill tool also needs the
# permission rule that unlocks skill INVOCATION under --permission-mode dontAsk
# (audit finding: repo/user skills are otherwise silently permission-denied;
# CLI built-ins run either way). Granular Skill(<name>) rules are unverified —
# least privilege is enforced by the tools: allowlist plus the role prompt's
# per-seat skill mapping, not by this rule.
SEAT_TOOLS="${ORCH_TOOLS:-$(awk -F': ' '/^tools:/{print $2; exit}' "$ROLE_DEF" 2>/dev/null)}"
ALLOWED_RULES=()
case "$SEAT_TOOLS" in
    *Skill*) ALLOWED_RULES+=("Skill") ;;
esac
# ABS-535: the rewritten skill references point at the governing checkout's
# LIVE skills dir, which sits OUTSIDE the seat cwd in self-hosting — without an
# allow rule the very Read the rewrite enables is permission-denied under
# --permission-mode dontAsk, and the denial poisons the session (not stored ->
# every follow-up spawn of the station starts cold). READ-ONLY on purpose:
# a Read(...) rule, never --add-dir — a seat must not be able to WRITE the
# governing skills. `//` prefix = absolute filesystem path in permission rules.
# Emitted ONLY when the skills dir lies outside the effective seat cwd: in a
# plain consumer repo (harness == target == cwd) reads inside the workspace are
# already permitted, so the argv stays byte-identical to the legacy spawn.
EFFECTIVE_CWD="${ORCH_SPAWN_CWD:-${ORCH_TARGET_REPO:-$PWD}}"
if [ -n "$SKILLS_DIR" ]; then
    case "$SKILLS_DIR/" in
        "$EFFECTIVE_CWD"/*) : ;;  # inside the workspace -> readable already
        *) ALLOWED_RULES+=("Read(/${SKILLS_DIR}/**)") ;;
    esac
fi
[ "${#ALLOWED_RULES[@]}" -gt 0 ] && set -- "$@" --allowedTools "${ALLOWED_RULES[@]}"

# ABS-111 C9 / ABS-92: choose the cwd before exec. ORCH_SPAWN_CWD (a runner-
# provisioned per-ticket git worktree) takes PRECEDENCE over ORCH_TARGET_REPO so
# the agent works inside its isolated worktree and cannot touch the main checkout;
# both are validated as existing dirs. When neither is set the cwd is unchanged
# (agent defs were already materialized from the harness above).
if [ -n "${ORCH_SPAWN_CWD:-}" ]; then
    cd "$ORCH_SPAWN_CWD" || die "cannot cd to ORCH_SPAWN_CWD: $ORCH_SPAWN_CWD"
elif [ -n "${ORCH_TARGET_REPO:-}" ]; then
    cd "$ORCH_TARGET_REPO" || die "cannot cd to ORCH_TARGET_REPO: $ORCH_TARGET_REPO"
fi

# PILOT-76: pin the seat's TMPDIR INSIDE its own worktree so every `mktemp` the
# seat — and the test harness it spawns at a gate (staged-suite/run-all/
# test-orchestrator) — makes lands under the already-allowlisted cwd. Under
# --permission-mode dontAsk a seat may Read/Write only within its cwd tree; the
# default $TMPDIR (/var/folders on macOS, /tmp on Linux) sits OUTSIDE it, so a
# gate seat could RUN the suite but was DENIED reading its own test artefacts →
# no pass/fail verdict → 2×NOMOVE → respawn-limit → Needs PO Decision (the RTE
# Epic-Integration station's PILOT-39 failure; also the enabler for the trivial
# PILOT-58 "nothing to integrate" case that still could not produce a verdict).
# `tmp/` is gitignored, so this never risks a stray commit, and it is cleaned
# with the worktree. Best-effort: if the dir cannot be created, leave TMPDIR
# untouched (fall back to prior behaviour) rather than fail the spawn.
if [ -n "${ORCH_SEAT:-}" ]; then
    _seat_tmpdir="$PWD/tmp"
    if mkdir -p "$_seat_tmpdir" 2>/dev/null; then
        export TMPDIR="$_seat_tmpdir"
    fi
    unset _seat_tmpdir
fi

exec "$CLAUDE_BIN" "$@"
