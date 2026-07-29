#!/bin/bash
# =============================================================================
# docs-identifier-check.sh — ABS-337: fail on fabricated ORCH_* / scripts/*
#                            identifiers in docs-story prose.
# -----------------------------------------------------------------------------
# THE GAP THIS CLOSES (ABS-303): a docs-only story carrying skip-review +
# skip-test (both correctly applied — the diff is one markdown file) has every
# mechanical gate removed except PO acceptance. Nothing verifies the document's
# factual content. ABS-303 shipped a proposal citing two orchestrator label/fence
# knobs that do not exist — one inside a copy-pasteable bash snippet a human was
# meant to run. This checker restores a cheap, MECHANICAL factual gate for that
# class of defect. NOTE: this file must never spell out a fabricated ORCH_* token
# literally, or the `git grep scripts/` below would self-satisfy it and mask the
# very defect the gate exists to catch.
#
# It scans the changed DOCS files (under work/improvement-proposals/ and docs/)
# for two token classes and fails on any that does not exist in the repo:
#   * ORCH_[A-Z0-9_]+   env-var tokens  -> must be `git grep`-verifiable in scripts/
#   * scripts/<path>    repo paths      -> must exist on the filesystem
# Prose factual claims beyond these two mechanical classes are OUT OF SCOPE
# (English claims, version numbers, external URLs are not mechanically checkable).
#
# GATING: ORCH_DOCS_IDENTIFIER_CHECK (default 1 = ON since ABS-517; set to 0 as
# the kill-switch). Off => this script is a clean no-op (exit 0) regardless of
# its arguments.
#
# SCOPE REFINEMENTS (ABS-517): docs/agent-outputs/, docs/archive/ and
# docs/releases/ are NOT gated — they are run artifacts / frozen history whose
# identifiers were factual at write time (governance: work product, never
# instructions). A template/example doc whose PURPOSE is hypothetical paths can
# opt out with the literal marker `docs-identifier-check: skip-file` anywhere
# in the file. ORCH_* tokens are verified against scripts/, backend/,
# harness/claude/hooks/, OR tests/ — each defines real ORCH_* knobs (tests/
# holds implementer-facing test-only knobs like ORCH_TEST_ALLOW_BACKEND,
# PILOT-62).
#
# Usage: scripts/docs-identifier-check.sh <file>...
#   Each <file> is a changed file (repo-relative or absolute). Only files under
#   work/improvement-proposals/ or docs/ are scanned; any other path is ignored
#   (a non-docs diff is untouched by this checker).
# Exit: 0 = pass (or gate off); 1 = one or more fabricated identifiers found.
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Gate default OFF -> today's behaviour exactly (no gate). This is the ONLY knob.
if [ "${ORCH_DOCS_IDENTIFIER_CHECK:-1}" != "1" ]; then
    exit 0
fi

# audit <msg> — name the finding on stderr AND (when the runner set one) append a
# structured run-log line so a failure is greppable in the audit trail.
audit() {
    echo "docs-identifier-check: $*" >&2
    if [ -n "${ORCH_RUN_LOG:-}" ]; then
        printf '%s\tDOCS-IDENTIFIER-FAIL\t-\t-\t-\t%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$ORCH_RUN_LOG" 2>/dev/null || true
    fi
}

# is_docs_path <path> — true only for the two docs scopes this checker gates.
# Matches the scope segment whether the path is repo-relative (docs/x.md) or
# absolute (/abs/.../work/improvement-proposals/x.md).
is_docs_path() {
    case "$1" in
        docs/agent-outputs/*|docs/archive/*|docs/releases/*) return 1 ;;
        */docs/agent-outputs/*|*/docs/archive/*|*/docs/releases/*) return 1 ;;
        work/improvement-proposals/*|docs/*) return 0 ;;
        */work/improvement-proposals/*|*/docs/*) return 0 ;;
        *) return 1 ;;
    esac
}

fail=0
for f in "$@"; do
    # Normalise an absolute path to repo-relative for the docs-scope decision.
    rel="$f"
    case "$f" in "$REPO_ROOT"/*) rel="${f#"$REPO_ROOT"/}" ;; esac
    is_docs_path "$rel" || continue          # non-docs file: untouched
    [ -f "$f" ] || continue
    # Template/example docs opt out explicitly (marker is visible in the file).
    grep -q 'docs-identifier-check: skip-file' "$f" && continue

    # --- ORCH_* env tokens: must be git grep-verifiable in a real code dir ----
    # (Searching scripts/ + backend/ + the harness hook SOURCE + tests/ — not the
    # whole tree — so a doc citing its own new, not-yet-real knob cannot self-
    # satisfy the check; real knobs live in one of those code dirs, not in prose.
    # harness/claude/hooks is the editable source of .claude/hooks (ABS-94), so
    # knobs read only by a PreToolUse hook — e.g. ORCH_MERGE_GUARD_TARGET_CMD,
    # PILOT-11 — are real definitions, not doc fabrications. tests/ is included
    # because a shipped test entrypoint defines real, implementer-facing test-only
    # knobs — e.g. ORCH_TEST_ALLOW_BACKEND, the sandbox-guard escape hatch in
    # tests/sandbox-guard.sh — that an SOP legitimately documents, PILOT-62.)
    while IFS= read -r tok; do
        [ -n "$tok" ] || continue
        if ! git -C "$REPO_ROOT" grep -qw -- "$tok" scripts/ backend/ harness/claude/hooks/ tests/ 2>/dev/null; then
            audit "fabricated ORCH_ token '$tok' in $rel (not defined in scripts/, backend/, harness/claude/hooks/, or tests/)"
            fail=1
        fi
    done < <(grep -oE 'ORCH_[A-Z0-9_]+' "$f" | sort -u)

    # --- scripts/* paths: must exist on the filesystem ------------------------
    while IFS= read -r p; do
        [ -n "$p" ] || continue
        # Trim trailing prose punctuation the regex may absorb (. , ) ` : ).
        p_clean="$p"
        while :; do
            case "$p_clean" in
                *[.,\)\`:]) p_clean="${p_clean%?}" ;;
                *) break ;;
            esac
        done
        [ -n "$p_clean" ] || continue
        # A token ending in '-' or '/' is a glob prefix / directory mention
        # (e.g. "scripts/orchestrator-*.sh" prose), not a concrete path claim.
        case "$p_clean" in *-|*/) continue ;; esac
        if [ ! -e "$REPO_ROOT/$p_clean" ]; then
            audit "fabricated path '$p_clean' in $rel (does not exist in repo)"
            fail=1
        fi
    done < <(grep -oE '(^|[^A-Za-z0-9_/.-])scripts/[A-Za-z0-9._/-]+' "$f" | sed -E 's|^[^s]||' | sort -u)
done

exit "$fail"
