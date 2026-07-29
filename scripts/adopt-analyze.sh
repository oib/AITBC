#!/bin/bash
#
# =============================================================================
# Existing-Project Adoption Analyzer (blueprint §8)
# =============================================================================
# Read-only inventory of a target repository ahead of boilerplate adoption:
# detected stack, existing CI, tracker references, harness conflicts, a
# capability-mapping suggestion (blueprint §19), and a migration-plan
# skeleton. This is analysis only — it never executes a migration and it
# NEVER writes inside the target path.
#
# Usage:
#   scripts/adopt-analyze.sh <target-repo-path> [--out <file>]
#
# Output: a markdown report (default: ./adoption-report.md in the CWD, or
# the path given via --out). Nothing is written under <target-repo-path>.
#
# Bash 3.2 / BSD-safe: no associative arrays, no `mapfile`, no GNU-only
# grep/sed/find flags. No jq/python dependency.
# =============================================================================

set -eu

# --- Output helpers ---------------------------------------------------------

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

die() {
    print_error "$*"
    exit 1
}

usage() {
    cat <<'EOF'
adopt-analyze.sh — read-only adoption inventory (blueprint §8)

Usage: scripts/adopt-analyze.sh <target-repo-path> [--out <file>]

  <target-repo-path>   Existing repository to analyze. Read-only: this
                        script never writes inside the target path.
  --out <file>          Report destination (default: ./adoption-report.md,
                        i.e. the current working directory — NOT the
                        target repo).

Emits a markdown report covering:
  - Detected stack (package.json, pyproject/requirements, go.mod, Gemfile,
    pom/gradle, Dockerfile, docker-compose)
  - Existing CI (.github/workflows, bitbucket-pipelines.yml, .gitlab-ci.yml)
  - Tracker references (Jira/Linear/GitHub-issues URLs in README/docs)
  - Harness conflicts (pre-existing .claude/, .agents/, .gemini/, .cursor/,
    AGENTS.md, CLAUDE.md, existing hooks)
  - Capability mapping suggestion (blueprint §19)
  - Migration plan skeleton (staged PRs) — requires human approval before
    execution (ADR-A-0004)

This tool performs analysis only. It never modifies the target repository
and never executes any part of the migration plan it proposes.
EOF
}

# --- Args ---------------------------------------------------------------

TARGET=""
OUT_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --out)
            [ $# -ge 2 ] || die "--out requires a value"
            OUT_FILE="$2"
            shift 2
            ;;
        *)
            if [ -z "$TARGET" ]; then
                TARGET="$1"
                shift
            else
                die "Unexpected argument: $1"
            fi
            ;;
    esac
done

[ -n "$TARGET" ] || { usage; die "target-repo-path is required"; }
[ -d "$TARGET" ] || die "Target path is not a directory: $TARGET"

# Resolve to an absolute path (read-only realpath equivalent, BSD-safe)
TARGET="$(cd "$TARGET" && pwd)"

OUT_FILE="${OUT_FILE:-$(pwd)/adoption-report.md}"

# Resolve OUT_FILE to an absolute path (its parent dir may not exist yet, so
# resolve the directory portion and re-append the filename — BSD-safe).
case "$OUT_FILE" in
    /*) ;; # already absolute
    *)
        OUT_DIR="$(dirname "$OUT_FILE")"
        OUT_BASE="$(basename "$OUT_FILE")"
        mkdir -p "$OUT_DIR"
        OUT_DIR="$(cd "$OUT_DIR" && pwd)"
        OUT_FILE="$OUT_DIR/$OUT_BASE"
        ;;
esac

# Guard: the report must never be written inside the target tree.
case "$OUT_FILE" in
    "$TARGET"|"$TARGET"/*)
        die "Refusing to write the report inside the target repo ($TARGET). Use --out to pick a location outside the target, e.g. --out /tmp/adoption-report.md"
        ;;
esac

print_info "Analyzing (read-only): $TARGET"
print_info "Report will be written to: $OUT_FILE"

# --- Small helpers --------------------------------------------------------

# file_exists_rel <relative-path> — test for a file/dir under $TARGET only.
target_has() {
    [ -e "$TARGET/$1" ]
}

# first_line_matching <file> <pattern> — first grep match, or empty.
first_line_matching() {
    [ -f "$1" ] || return 0
    grep -m 1 -E "$2" "$1" 2>/dev/null || true
}

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/adopt-analyze.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT

REPORT="$TMP_DIR/adoption-report.md"
: > "$REPORT"

emit() {
    printf '%s\n' "$1" >> "$REPORT"
}

# =============================================================================
# Header
# =============================================================================

emit "# Adoption Analysis Report"
emit ""
emit "- **Target**: \`$TARGET\`"
emit "- **Generated**: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
emit "- **Mode**: read-only inventory (blueprint §8) — no files were written or modified inside the target repository."
emit ""
emit "---"
emit ""

# =============================================================================
# Section: Detected Stack
# =============================================================================

emit "## Detected Stack"
emit ""

STACK_FOUND=0

if target_has "package.json"; then
    STACK_FOUND=1
    NODE_NAME=""
    NODE_VERSION=""
    NODE_NAME=$(first_line_matching "$TARGET/package.json" '"name"[[:space:]]*:' | sed -E 's/.*"name"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')
    NODE_VERSION=$(first_line_matching "$TARGET/package.json" '"version"[[:space:]]*:' | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')
    emit "- **Node.js** — \`package.json\` found (name: \`${NODE_NAME:-unknown}\`, version: \`${NODE_VERSION:-unknown}\`)"
    if target_has "package-lock.json"; then
        emit "  - Lockfile: \`package-lock.json\` (npm)"
    elif target_has "yarn.lock"; then
        emit "  - Lockfile: \`yarn.lock\` (yarn)"
    elif target_has "pnpm-lock.yaml"; then
        emit "  - Lockfile: \`pnpm-lock.yaml\` (pnpm)"
    fi
fi

if target_has "pyproject.toml"; then
    STACK_FOUND=1
    PY_NAME=$(first_line_matching "$TARGET/pyproject.toml" '^name[[:space:]]*=' | sed -E 's/^name[[:space:]]*=[[:space:]]*"?([^"]*)"?.*/\1/')
    emit "- **Python** — \`pyproject.toml\` found (name: \`${PY_NAME:-unknown}\`)"
elif target_has "requirements.txt"; then
    STACK_FOUND=1
    REQ_COUNT=$(grep -cve '^[[:space:]]*$' -e '^[[:space:]]*#' "$TARGET/requirements.txt" 2>/dev/null || echo "0")
    emit "- **Python** — \`requirements.txt\` found (${REQ_COUNT} declared requirement lines)"
fi

if target_has "go.mod"; then
    STACK_FOUND=1
    GO_MODULE=$(first_line_matching "$TARGET/go.mod" '^module[[:space:]]+')
    GO_VERSION_LINE=$(first_line_matching "$TARGET/go.mod" '^go[[:space:]]+[0-9]')
    emit "- **Go** — \`go.mod\` found (${GO_MODULE:-module unknown}${GO_VERSION_LINE:+, $GO_VERSION_LINE})"
fi

if target_has "Gemfile"; then
    STACK_FOUND=1
    RUBY_VERSION_LINE=$(first_line_matching "$TARGET/Gemfile" '^ruby[[:space:]]')
    emit "- **Ruby** — \`Gemfile\` found${RUBY_VERSION_LINE:+ ($RUBY_VERSION_LINE)}"
fi

if target_has "pom.xml"; then
    STACK_FOUND=1
    emit "- **Java (Maven)** — \`pom.xml\` found"
fi

if target_has "build.gradle" || target_has "build.gradle.kts"; then
    STACK_FOUND=1
    emit "- **Java/Kotlin (Gradle)** — build.gradle found"
fi

if target_has "Dockerfile"; then
    STACK_FOUND=1
    BASE_IMAGE=$(first_line_matching "$TARGET/Dockerfile" '^FROM[[:space:]]+')
    emit "- **Docker** — \`Dockerfile\` found${BASE_IMAGE:+ ($BASE_IMAGE)}"
fi

if target_has "docker-compose.yml" || target_has "docker-compose.yaml"; then
    STACK_FOUND=1
    emit "- **Docker Compose** — compose file found"
fi

if [ "$STACK_FOUND" -eq 0 ]; then
    emit "- No recognized stack manifest found (package.json, pyproject.toml/requirements.txt, go.mod, Gemfile, pom.xml/build.gradle, Dockerfile, docker-compose)."
fi

emit ""
emit "---"
emit ""

# =============================================================================
# Section: Existing CI
# =============================================================================

emit "## Existing CI"
emit ""

CI_FOUND=0

if [ -d "$TARGET/.github/workflows" ]; then
    CI_FOUND=1
    emit "- **GitHub Actions** — \`.github/workflows/\`:"
    find "$TARGET/.github/workflows" -maxdepth 1 -type f \( -name "*.yml" -o -name "*.yaml" \) 2>/dev/null | while read -r wf; do
        emit "  - \`.github/workflows/$(basename "$wf")\`"
    done
fi

if target_has "bitbucket-pipelines.yml"; then
    CI_FOUND=1
    emit "- **Bitbucket Pipelines** — \`bitbucket-pipelines.yml\`"
fi

if target_has ".gitlab-ci.yml"; then
    CI_FOUND=1
    emit "- **GitLab CI** — \`.gitlab-ci.yml\`"
fi

if [ "$CI_FOUND" -eq 0 ]; then
    emit "- No existing CI configuration found (.github/workflows, bitbucket-pipelines.yml, .gitlab-ci.yml)."
fi

emit ""
emit "---"
emit ""

# =============================================================================
# Section: Tracker References
# =============================================================================

emit "## Tracker References"
emit ""
emit "First match per tracker type, searched across README and \`docs/\` (bounded — not exhaustive):"
emit ""

# Search for tracker references using NUL-delimited file list for safe handling of paths with spaces.
# README* at root + docs/**, read-only.

TRACKER_FOUND=0

JIRA_MATCH=""
LINEAR_MATCH=""
GH_ISSUES_MATCH=""

# Helper: search_tracker_pattern <pattern> — searches README + docs/ with NUL-delimited find+xargs.
search_tracker_pattern() {
    local pattern="$1"
    (
        find "$TARGET" -maxdepth 1 -iname "README*" -type f -print0 2>/dev/null | xargs -0 grep -m 1 -Eho "$pattern" 2>/dev/null || true
        if [ -d "$TARGET/docs" ]; then
            find "$TARGET/docs" -type f \( -name "*.md" -o -name "*.mdx" -o -name "*.txt" \) -print0 2>/dev/null | xargs -0 grep -m 1 -Eho "$pattern" 2>/dev/null || true
        fi
    ) | head -1
}

if [ -d "$TARGET" ]; then
    JIRA_MATCH=$(search_tracker_pattern 'https?://[A-Za-z0-9.-]+\.atlassian\.net/browse/[A-Za-z0-9_-]+')
    if [ -z "$JIRA_MATCH" ]; then
        JIRA_MATCH=$(search_tracker_pattern '\b[A-Z][A-Z0-9]+-[0-9]+\b')
    fi
    LINEAR_MATCH=$(search_tracker_pattern 'https?://linear\.app/[A-Za-z0-9_/-]+')
    GH_ISSUES_MATCH=$(search_tracker_pattern 'https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues[A-Za-z0-9/_-]*')
fi
if [ -n "$JIRA_MATCH" ]; then
    TRACKER_FOUND=1
    emit "- **Jira** — \`$JIRA_MATCH\`"
fi
if [ -n "$LINEAR_MATCH" ]; then
    TRACKER_FOUND=1
    emit "- **Linear** — \`$LINEAR_MATCH\`"
fi
if [ -n "$GH_ISSUES_MATCH" ]; then
    TRACKER_FOUND=1
    emit "- **GitHub Issues** — \`$GH_ISSUES_MATCH\`"
fi

if [ "$TRACKER_FOUND" -eq 0 ]; then
    emit "- No tracker references found in README/docs (Jira, Linear, GitHub Issues)."
fi

emit ""
emit "---"
emit ""

# =============================================================================
# Section: Harness Conflicts
# =============================================================================

emit "## Harness Conflicts"
emit ""
emit "Pre-existing files/directories that will conflict with boilerplate files of the same name:"
emit ""

CONFLICT_FOUND=0

check_conflict() {
    # check_conflict <relative-path> <boilerplate-file-description>
    if target_has "$1"; then
        CONFLICT_FOUND=1
        emit "- \`$1\` exists — will conflict with boilerplate file \`$1\` ($2)"
    fi
}

check_conflict ".claude" "Claude Code harness (agents, skills, commands, hooks)"
check_conflict ".agents" "shared agent skills directory"
check_conflict ".gemini" "Gemini CLI harness"
check_conflict ".cursor" "Cursor IDE harness (.mdc rules)"
check_conflict "AGENTS.md" "agent role reference"
check_conflict "CLAUDE.md" "AI assistant context file"
check_conflict ".codex" "Codex CLI harness (config.toml)"

if [ -d "$TARGET/.git/hooks" ]; then
    CUSTOM_HOOKS=$(find "$TARGET/.git/hooks" -maxdepth 1 -type f ! -name "*.sample" 2>/dev/null | wc -l | tr -d ' ')
    if [ "${CUSTOM_HOOKS:-0}" -gt 0 ]; then
        CONFLICT_FOUND=1
        emit "- \`.git/hooks/\` has $CUSTOM_HOOKS non-sample hook(s) installed — will conflict with boilerplate-managed hooks (\`.claude/hooks/\`)"
    fi
fi

if [ "$CONFLICT_FOUND" -eq 0 ]; then
    emit "- No pre-existing harness files detected. Clean adoption target."
fi

emit ""
emit "---"
emit ""

# =============================================================================
# Section: Capability Mapping Suggestion (blueprint §19)
# =============================================================================

emit "## Capability Mapping Suggestion (blueprint §19)"
emit ""
emit "| Capability | Detected candidate | Provider suggestion |"
emit "| ---------- | ------------------- | -------------------- |"

# Task tracking
if [ -n "$JIRA_MATCH" ]; then
    emit "| Task Tracking Adapter | Jira reference found in docs | jira candidate |"
elif [ -n "$LINEAR_MATCH" ]; then
    emit "| Task Tracking Adapter | Linear reference found in docs | linear candidate |"
elif [ -n "$GH_ISSUES_MATCH" ]; then
    emit "| Task Tracking Adapter | GitHub Issues reference found in docs | github-issues candidate |"
else
    emit "| Task Tracking Adapter | none detected | unresolved |"
fi

# Git/PR + CI/deploy
if [ -d "$TARGET/.github/workflows" ]; then
    emit "| Git Repository Adapter | \`.github/workflows/\` present | github candidate |"
    emit "| Quality Gate Runner / Deploy | \`.github/workflows/\` present | github-actions candidate |"
elif target_has "bitbucket-pipelines.yml"; then
    emit "| Git Repository Adapter | \`bitbucket-pipelines.yml\` present | bitbucket candidate |"
    emit "| Quality Gate Runner / Deploy | \`bitbucket-pipelines.yml\` present | bitbucket-pipelines candidate |"
elif target_has ".gitlab-ci.yml"; then
    emit "| Git Repository Adapter | \`.gitlab-ci.yml\` present | gitlab candidate |"
    emit "| Quality Gate Runner / Deploy | \`.gitlab-ci.yml\` present | gitlab-ci candidate |"
else
    emit "| Git Repository Adapter | none detected | unresolved |"
    emit "| Quality Gate Runner / Deploy | none detected | unresolved |"
fi

# Container/runtime
if target_has "Dockerfile" || target_has "docker-compose.yml" || target_has "docker-compose.yaml"; then
    emit "| Container Runtime | Dockerfile/docker-compose present | docker candidate |"
else
    emit "| Container Runtime | none detected | unresolved |"
fi

emit ""
emit "Every row is a **suggestion for human review** — nothing here is applied automatically."
emit ""
emit "---"
emit ""

# =============================================================================
# Section: Migration Plan Skeleton
# =============================================================================

emit "## Migration Plan Skeleton"
emit ""
emit "**Requires human approval before execution (ADR-A-0004).** This analyzer produces the"
emit "plan skeleton only; no migration step below has been executed."
emit ""

emit "### Stage 1 — Harness Files PR"
emit ""
if [ "$CONFLICT_FOUND" -eq 1 ]; then
    emit "- Conflict notes: pre-existing harness files/directories detected above must be reconciled"
    emit "  (merge, rename, or override) before this PR can land cleanly."
else
    emit "- Conflict notes: none — no pre-existing harness files detected."
fi
emit "- Adds: \`.claude/\`, \`.agents/\`, \`AGENTS.md\`, \`CLAUDE.md\` (and \`.gemini/\`, \`.cursor/\`, \`.codex/\` if adopted)."
emit ""

emit "### Stage 2 — CI PR"
emit ""
if [ "$CI_FOUND" -eq 1 ]; then
    emit "- Conflict notes: existing CI configuration detected above — new quality-gate steps must"
    emit "  be merged into it rather than replacing it outright."
else
    emit "- Conflict notes: none — no existing CI configuration detected; boilerplate CI can be added fresh."
fi
emit "- Wires the Quality Gate Runner (blueprint §19) into the detected/suggested CI provider."
emit ""

emit "### Stage 3 — Tracker Adapter PR"
emit ""
if [ "$TRACKER_FOUND" -eq 1 ]; then
    emit "- Conflict notes: existing tracker reference(s) detected above — adapter configuration should"
    emit "  point at the existing tracker/project rather than provisioning a new one."
else
    emit "- Conflict notes: none — no existing tracker reference detected; adapter target needs human input."
fi
emit "- Configures the Task Tracking Adapter (blueprint §18) capability mapping proposed above."
emit ""

emit "### Stage 4 — Docs PR"
emit ""
emit "- Conflict notes: reconcile any pre-existing \`README\`/\`docs/\` content that duplicates"
emit "  boilerplate onboarding docs."
emit "- Adds/links \`docs/guides/WORKSPACE-ADOPTION-GUIDE.md\`, \`docs/sop/BOILERPLATE_MIGRATION_SOP.md\`,"
emit "  and records the \`.boilerplate-version\` marker stamped at adoption."
emit ""

emit "**This plan requires human approval before execution (ADR-A-0004).** No stage above has"
emit "been applied to the target repository by this tool."
emit ""

# --- Finalize --------------------------------------------------------------

mkdir -p "$(dirname "$OUT_FILE")"
cp "$REPORT" "$OUT_FILE"

print_success "Report written: $OUT_FILE"
print_info "Target repository was not modified (read-only analysis)."
