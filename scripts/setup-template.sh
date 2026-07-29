#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# GitHub Template Setup Wizard (Bootstrap v2)
# ============================================================================
# This script customizes the template repository for your project. It:
#   1. Collects project identity values (interactive prompts, a --values file,
#      or environment variables).
#   2. Replaces {{PLACEHOLDER}} tokens across the repo.
#   3. Writes secrets (DB_PASSWORD) to .env, never to tracked files.
#   4. Generates/updates .harness-manifest.yml.
#   5. Selects an agentic-execution profile and records it in .active-profile.
#   6. Emits a tooling-readiness gap report (bootstrap-gap-report.md).
#
# The wizard is IDEMPOTENT: run it twice and the second run detects
# already-replaced placeholders and skips destructive steps.
#
# Usage:
#   bash scripts/setup-template.sh                 # interactive
#   bash scripts/setup-template.sh --values FILE   # KEY=VALUE file (non-interactive)
#   bash scripts/setup-template.sh --yes           # skip the confirm prompt
#   bash scripts/setup-template.sh --profile NAME  # pick profiles/<NAME>
#   bash scripts/setup-template.sh --allow-gaps    # do not fail on NOT-ready gaps
#   bash scripts/setup-template.sh --finalize      # also delete wizard + TEMPLATE_SETUP.md
#
# Environment variables matching the prompt keys (e.g. PROJECT_NAME=foo) are
# honored as a value source, below a --values file but above interactive input.
#
# Compatible with GNU sed (Linux) and BSD sed (macOS), bash 3.2+.
# ============================================================================

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# --- CLI flags ---
VALUES_FILE=""
ASSUME_YES=false
PROFILE_FLAG=""
ALLOW_GAPS=false
FINALIZE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --values)
      VALUES_FILE="${2:-}"
      shift 2
      ;;
    --values=*)
      VALUES_FILE="${1#*=}"
      shift
      ;;
    --yes|-y)
      ASSUME_YES=true
      shift
      ;;
    --profile)
      PROFILE_FLAG="${2:-}"
      shift 2
      ;;
    --profile=*)
      PROFILE_FLAG="${1#*=}"
      shift
      ;;
    --allow-gaps)
      ALLOW_GAPS=true
      shift
      ;;
    --finalize)
      FINALIZE=true
      shift
      ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -40
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# Non-interactive when stdin is not a TTY OR a --values file was supplied.
NON_INTERACTIVE=false
if [[ -n "$VALUES_FILE" ]] || [ ! -t 0 ]; then
  NON_INTERACTIVE=true
fi

# --- Cross-platform sed helper ---
# BSD sed (macOS) requires -i '' while GNU sed uses -i alone.
# Detect the dialect ONCE at startup (ABS-179): the old helper ran
# `sed --version | grep GNU` on every call, which -- inside the per-file,
# per-placeholder replacement loop -- meant hundreds of thousands of extra
# process spawns. Resolve it to a single flag here instead.
if sed --version 2>/dev/null | grep -q 'GNU'; then
  SED_IS_GNU=true
else
  SED_IS_GNU=false
fi
_sed_inplace() {
  if [[ "$SED_IS_GNU" == true ]]; then
    sed -i "$@"
  else
    sed -i '' "$@"
  fi
}

# --- Escape a literal string for safe use inside a sed "s|OLD|NEW|g" expression ---
_sed_escape() {
  printf '%s' "$1" | sed -e 's/[\&|]/\\&/g'
}

# --- Shared repo-sweep excludes/includes (ABS-179) --------------------------
# ONE directory-exclude list applied to ALL repo sweeps (candidate scan,
# idempotency check, REMAINING report) so the wizard never traverses giant
# dependency/build/VCS trees in a real target project. Traversing node_modules
# alone turned a seconds-long run into hours (live-confirmed 2026-07-09).
SWEEP_EXCLUDE_DIRS=(.git node_modules dist build .next vendor worktrees tmp)

# File types that carry {{PLACEHOLDER}} tokens (matches the substitution set
# below -- same extensions the old per-placeholder `find` loop used).
SWEEP_INCLUDE_GLOBS=(
  "*.md" "*.json" "*.yml" "*.yaml" "*.sh" "*.py" "*.txt" "*.toml"
  "*.bib" "*.cff" "*.mjs" "*.ts"
  "NOTICE" "LICENSE" "CODEOWNERS" ".env.template" ".gitignore"
)

# Pre-build the grep --include / --exclude-dir argument array once.
GREP_SWEEP_ARGS=()
for _g in "${SWEEP_INCLUDE_GLOBS[@]}"; do GREP_SWEEP_ARGS+=(--include="$_g"); done
for _d in "${SWEEP_EXCLUDE_DIRS[@]}"; do GREP_SWEEP_ARGS+=(--exclude-dir="$_d"); done

echo "============================================"
echo "  AI Agent Harness - Template Setup Wizard"
echo "============================================"
echo ""
echo "This will replace all template placeholders with your project values."
echo "Press Ctrl+C to cancel at any time."
echo ""

# --- Dependency preflight ---
# These tools are used by the sync/manifest machinery (not this wizard's core),
# but checking here gives users one early, consolidated warning. Missing tools
# do NOT abort the wizard.
DEP_WARNINGS=()

if ! command -v python3 &>/dev/null; then
  DEP_WARNINGS+=("python3 not found - install from https://www.python.org/downloads/ (needed for manifest/YAML parsing)")
else
  if ! python3 -c "import yaml" &>/dev/null; then
    DEP_WARNINGS+=("PyYAML not importable - install with: python3 -m pip install pyyaml (needed for manifest/YAML parsing)")
  fi
fi

if ! command -v node &>/dev/null; then
  DEP_WARNINGS+=("node not found - install via nvm (https://github.com/nvm-sh/nvm) or https://nodejs.org/ (needed for sync tooling)")
fi

echo "Bash version: ${BASH_VERSION:-unknown}"

if [[ ${#DEP_WARNINGS[@]} -gt 0 ]]; then
  echo ""
  echo "WARNING: Some optional dependencies for the sync/manifest tooling are missing:"
  for w in "${DEP_WARNINGS[@]}"; do
    echo "  - $w"
  done
  echo "The wizard itself will continue, but scripts/sync-claude-harness.sh may not work until these are installed."
  echo ""
fi

# ============================================================================
# Value collection (ABS-47): --values file > env var > interactive prompt.
# ============================================================================
# Parse an optional KEY=VALUE file. Lines starting with # and blank lines are
# ignored. Values may be quoted; surrounding single/double quotes are stripped.

declare -a VF_KEYS=()
declare -a VF_VALS=()

if [[ -n "$VALUES_FILE" ]]; then
  if [[ ! -f "$VALUES_FILE" ]]; then
    echo "ERROR: values file not found: $VALUES_FILE" >&2
    exit 2
  fi
  while IFS= read -r _line || [ -n "$_line" ]; do
    # strip comments (whole-line) and blanks
    case "$_line" in
      ''|\#*) continue ;;
    esac
    # must contain '='
    case "$_line" in
      *=*) : ;;
      *) continue ;;
    esac
    _k="${_line%%=*}"
    _v="${_line#*=}"
    # trim surrounding whitespace on key
    _k="$(printf '%s' "$_k" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    # strip a single pair of surrounding quotes on value
    case "$_v" in
      \"*\") _v="${_v#\"}"; _v="${_v%\"}" ;;
      \'*\') _v="${_v#\'}"; _v="${_v%\'}" ;;
    esac
    VF_KEYS+=("$_k")
    VF_VALS+=("$_v")
  done < "$VALUES_FILE"
fi

# Look up a key in the parsed values file. Echoes value, returns 0 if found.
_vf_lookup() {
  local want="$1" i=0 n=${#VF_KEYS[@]}
  while [ "$i" -lt "$n" ]; do
    if [ "${VF_KEYS[$i]}" = "$want" ]; then
      printf '%s' "${VF_VALS[$i]}"
      return 0
    fi
    i=$((i + 1))
  done
  return 1
}

# Missing required keys accumulator (non-interactive hard-fail).
MISSING_KEYS=()

# Resolve a single value from the layered sources.
#   $1 = KEY   $2 = prompt text   $3 = default (may be empty)   $4 = required(true/false)
# Assigns the resolved value to the variable named by KEY.
resolve_value() {
  local key="$1" prompt="$2" def="$3" required="$4"
  local val="" found=false

  # 1. --values file
  if [[ -n "$VALUES_FILE" ]] && val="$(_vf_lookup "$key")"; then
    found=true
  fi

  # 2. environment variable of the same name (only if non-empty and not already found)
  if [[ "$found" == false ]]; then
    eval "local envval=\"\${$key:-}\""
    if [[ -n "$envval" ]]; then
      val="$envval"
      found=true
    fi
  fi

  # 3. interactive prompt (only when we still have nothing and a TTY is available)
  if [[ "$found" == false && "$NON_INTERACTIVE" == false ]]; then
    if [[ -n "$def" ]]; then
      read -rp "$prompt [$def]: " val
    else
      read -rp "$prompt: " val
    fi
    found=true
  fi

  # 4. default fallback
  if [[ -z "${val:-}" && -n "$def" ]]; then
    val="$def"
  fi

  # required check
  if [[ -z "${val:-}" && "$required" == true ]]; then
    if [[ "$NON_INTERACTIVE" == true ]]; then
      MISSING_KEYS+=("$key")
    fi
  fi

  # assign to the named variable
  eval "$key=\"\$val\""
}

echo "--- Project Identity ---"
resolve_value PROJECT_NAME  "Project name (e.g., my-saas-app)"        "" true
resolve_value PROJECT_REPO  "Project repo name (e.g., my-saas-app)"   "" true
resolve_value PROJECT_SHORT "Project short name / acronym (e.g., ACME)" "" true
resolve_value PROJECT_DOMAIN "Project domain (e.g., acme.com)"        "" false

echo ""
echo "--- Organization ---"
resolve_value GITHUB_ORG    "GitHub org or username (e.g., acme-corp)" "" true
resolve_value COMPANY_NAME  "Company/org display name (e.g., Acme Corp)" "" false

echo ""
echo "--- Author ---"
resolve_value AUTHOR_NAME       "Author full name (e.g., Jane Smith)"    "" false
resolve_value AUTHOR_FIRST_NAME "Author first name (e.g., Jane)"         "" false
resolve_value AUTHOR_LAST_NAME  "Author last name (e.g., Smith)"         "" false
resolve_value AUTHOR_HANDLE     "Author GitHub handle (e.g., janesmith)" "" false
resolve_value AUTHOR_EMAIL      "Author email (e.g., jane@acme.com)"     "" false
resolve_value AUTHOR_WEBSITE    "Author website URL (e.g., https://janesmith.dev)" "" false
resolve_value SECURITY_EMAIL    "Security contact email (e.g., security@acme.com)" "" false

echo ""
echo "--- Workflow ---"
resolve_value ARCHITECT_GITHUB_HANDLE "Architect GitHub handle (e.g., lead-dev)" "" false
resolve_value TICKET_PREFIX     "Linear ticket prefix (e.g., ACM)"       "" true
resolve_value LINEAR_WORKSPACE  "Linear workspace slug (e.g., acme)"     "" false
resolve_value MAIN_BRANCH       "Main branch name"                       "main" false

echo ""
echo "--- MCP Server Names ---"
resolve_value MCP_LINEAR_SERVER     "Linear MCP server name"     "linear-mcp" false
resolve_value MCP_CONFLUENCE_SERVER "Confluence MCP server name" "confluence-mcp" false
resolve_value MCP_JIRA_SERVER       "Jira MCP server name"       "jira-mcp" false

echo ""
echo "--- Infrastructure ---"
resolve_value DB_USER            "Database user (e.g., app_user)"         "" false
resolve_value DB_PASSWORD        "Database password (e.g., app_password)" "" false
resolve_value DB_NAME            "Database name (e.g., app_dev)"          "" false
resolve_value DB_CONTAINER       "Database container name (e.g., app-postgres)" "" false
resolve_value DEV_CONTAINER      "Dev container name (e.g., app-dev)"     "" false
resolve_value STAGING_CONTAINER  "Staging container name (e.g., app-staging)" "" false
resolve_value CONTAINER_REGISTRY "Container registry (e.g., ghcr.io/acme-corp)" "" false

# --- Non-interactive hard-fail on missing required keys (ABS-47) ---
if [[ ${#MISSING_KEYS[@]} -gt 0 ]]; then
  echo "" >&2
  echo "ERROR: non-interactive run is missing required values for:" >&2
  for k in "${MISSING_KEYS[@]}"; do
    echo "  $k" >&2
  done
  echo "" >&2
  echo "Provide them via --values <file>, environment variables, or run interactively." >&2
  exit 3
fi

# --- TICKET_PREFIX schema validation (.harness-manifest.schema.json: ^[A-Z][A-Z0-9]{1,9}$) ---
# Upper-case it first (a lowercase/mixed-case prefix like "acm" is a common
# typo, not an intentional choice), then validate against the schema pattern.
# A non-conforming value can't be silently coerced further, so a
# non-interactive run hard-fails with the offending value listed.
if [[ -n "$TICKET_PREFIX" ]]; then
  TICKET_PREFIX="$(printf '%s' "$TICKET_PREFIX" | tr '[:lower:]' '[:upper:]')"
  case "$TICKET_PREFIX" in
    [A-Z][A-Z0-9] | [A-Z][A-Z0-9][A-Z0-9] | [A-Z][A-Z0-9][A-Z0-9][A-Z0-9] | \
    [A-Z][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9] | [A-Z][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9] | \
    [A-Z][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9] | \
    [A-Z][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9] | \
    [A-Z][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9] | \
    [A-Z][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9][A-Z0-9])
      : # conforms to ^[A-Z][A-Z0-9]{1,9}$ (2-10 chars total)
      ;;
    *)
      if [[ "$NON_INTERACTIVE" == true ]]; then
        echo "" >&2
        echo "ERROR: TICKET_PREFIX '$TICKET_PREFIX' does not conform to the required" >&2
        echo "pattern ^[A-Z][A-Z0-9]{1,9}\$ (2-10 chars, starts with a letter," >&2
        echo "letters/digits only)." >&2
        exit 3
      else
        echo "" >&2
        echo "WARNING: TICKET_PREFIX '$TICKET_PREFIX' does not conform to the required" >&2
        echo "pattern ^[A-Z][A-Z0-9]{1,9}\$ (2-10 chars, starts with a letter," >&2
        echo "letters/digits only). The generated manifest will fail schema validation." >&2
      fi
      ;;
  esac
fi

# Derived values
TICKET_PREFIX_LOWER=$(echo "$TICKET_PREFIX" | tr '[:upper:]' '[:lower:]')
if [[ -n "$AUTHOR_FIRST_NAME" && -n "$AUTHOR_LAST_NAME" ]]; then
  AUTHOR_INITIALS="${AUTHOR_FIRST_NAME:0:1}. ${AUTHOR_LAST_NAME:0:1}."
else
  AUTHOR_INITIALS=""
fi
GITHUB_REPO_URL="https://github.com/${GITHUB_ORG}/${PROJECT_REPO}"

# Determine the harness version (single source of truth), in priority order:
#   1. Newest entry in HARNESS_CHANGELOG.yml whose summary is NOT marked
#      "Unreleased" (i.e., the latest actually-released version).
#   2. .boilerplate-version file content (mirrors the last release tag).
#   3. Hardcoded fallback constant.
# The source used is printed so it's clear which path produced the value.
# Versions are normalized to the "vX.Y.Z" form regardless of source format.
HARNESS_VERSION="v2.10.0"
HARNESS_VERSION_SOURCE="hardcoded fallback"

HARNESS_VERSION_TMP=""
if [[ -f "$REPO_ROOT/HARNESS_CHANGELOG.yml" ]] && command -v python3 &>/dev/null; then
  HARNESS_VERSION_TMP=$(python3 -c "
import yaml
try:
    with open('$REPO_ROOT/HARNESS_CHANGELOG.yml') as f:
        data = yaml.safe_load(f)
    for rel in data.get('releases', []):
        summary = rel.get('summary', '')
        if 'Unreleased' not in summary:
            print(rel.get('version', ''))
            break
except Exception:
    pass
" 2>/dev/null)
fi

if [[ -n "$HARNESS_VERSION_TMP" ]]; then
  HARNESS_VERSION="$HARNESS_VERSION_TMP"
  HARNESS_VERSION_SOURCE="HARNESS_CHANGELOG.yml (latest released entry)"
elif [[ -f "$REPO_ROOT/.boilerplate-version" ]]; then
  HARNESS_VERSION_TMP="$(grep -v '^#' "$REPO_ROOT/.boilerplate-version" | grep -v '^[[:space:]]*$' | head -1 | tr -d '[:space:]')"
  if [[ -n "$HARNESS_VERSION_TMP" ]]; then
    HARNESS_VERSION="$HARNESS_VERSION_TMP"
    HARNESS_VERSION_SOURCE=".boilerplate-version file"
  fi
fi

# Normalize to "vX.Y.Z" form regardless of which source produced the value.
HARNESS_VERSION="${HARNESS_VERSION#v}"
HARNESS_VERSION="v${HARNESS_VERSION}"

echo "Harness version resolved via: ${HARNESS_VERSION_SOURCE} -> ${HARNESS_VERSION}"

# ============================================================================
# Profile selection (ABS-48)
# ============================================================================
PROFILES_DIR="$REPO_ROOT/profiles"
PROFILE_NAME=""

# Gather available profile names (directories containing profile.yaml).
declare -a AVAILABLE_PROFILES=()
if [[ -d "$PROFILES_DIR" ]]; then
  for d in "$PROFILES_DIR"/*/; do
    [[ -f "${d}profile.yaml" ]] || continue
    AVAILABLE_PROFILES+=("$(basename "$d")")
  done
fi

if [[ -n "$PROFILE_FLAG" ]]; then
  PROFILE_NAME="$PROFILE_FLAG"
elif [[ -n "${PROFILE:-}" ]]; then
  PROFILE_NAME="$PROFILE"
elif [[ "$NON_INTERACTIVE" == false && ${#AVAILABLE_PROFILES[@]} -gt 0 ]]; then
  echo ""
  echo "--- Profile selection ---"
  echo "Available profiles (bind neutral capabilities to concrete providers):"
  for p in "${AVAILABLE_PROFILES[@]}"; do
    echo "  - $p"
  done
  read -rp "Profile [neutral]: " PROFILE_NAME
fi
PROFILE_NAME="${PROFILE_NAME:-neutral}"

# Validate the selected profile exists.
if [[ ! -f "$PROFILES_DIR/$PROFILE_NAME/profile.yaml" ]]; then
  echo "ERROR: profile '$PROFILE_NAME' not found (expected $PROFILES_DIR/$PROFILE_NAME/profile.yaml)." >&2
  if [[ ${#AVAILABLE_PROFILES[@]} -gt 0 ]]; then
    echo "Available: ${AVAILABLE_PROFILES[*]}" >&2
  fi
  exit 4
fi

echo ""
echo "--- Review your values ---"
echo "  Project name:       $PROJECT_NAME"
echo "  Project repo:       $PROJECT_REPO"
echo "  Project short:      $PROJECT_SHORT"
echo "  Project domain:     $PROJECT_DOMAIN"
echo "  GitHub org:         $GITHUB_ORG"
echo "  Company:            $COMPANY_NAME"
echo "  Author:             $AUTHOR_NAME ($AUTHOR_HANDLE) <$AUTHOR_EMAIL>"
echo "  Author website:     $AUTHOR_WEBSITE"
echo "  Author initials:    $AUTHOR_INITIALS"
echo "  Security email:     $SECURITY_EMAIL"
echo "  Ticket prefix:      $TICKET_PREFIX ($TICKET_PREFIX_LOWER)"
echo "  Linear workspace:   $LINEAR_WORKSPACE"
echo "  Main branch:        $MAIN_BRANCH"
echo "  MCP Linear server:  $MCP_LINEAR_SERVER"
echo "  MCP Confluence:     $MCP_CONFLUENCE_SERVER"
echo "  MCP Jira server:    $MCP_JIRA_SERVER"
echo "  Harness version:    $HARNESS_VERSION"
echo "  Database:           $DB_USER / $DB_NAME ($DB_CONTAINER)"
echo "  Dev container:      $DEV_CONTAINER"
echo "  Staging container:  $STAGING_CONTAINER"
echo "  Registry:           $CONTAINER_REGISTRY"
echo "  Repo URL:           $GITHUB_REPO_URL"
echo "  Profile:            $PROFILE_NAME"
echo ""

if [[ "$ASSUME_YES" == false ]]; then
  if [[ "$NON_INTERACTIVE" == true ]]; then
    echo "Non-interactive mode: pass --yes to skip this confirmation." >&2
    exit 5
  fi
  read -rp "Proceed? (y/N): " CONFIRM
  if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

echo ""
echo "Applying replacements..."

# --- Candidate scan (ABS-179): ONE traversal shared by all three sweeps ------
# A single grep collects every file that contains any "{{" token, honoring the
# shared directory excludes and the wizard's own-source exclusion. The
# idempotency check, the replacement loop, and the REMAINING report all reuse
# this list -- no sweep re-traverses the repo. The old code traversed the whole
# tree once per placeholder (30x) plus a full idempotency + REMAINING scan,
# reading all of node_modules each time (~450k spawns / hours).
CANDIDATE_FILES=()
while IFS= read -r _cf; do
  [[ -n "$_cf" ]] && CANDIDATE_FILES+=("$_cf")
done < <(grep -rl '{{' "$REPO_ROOT" \
    "${GREP_SWEEP_ARGS[@]}" \
    --exclude="setup-template.sh" \
    2>/dev/null || true)

# --- Idempotency check (ABS-50): are any known placeholders still present? ---
# Reuses the candidate list. The wizard's own source literally contains
# "{{PROJECT_NAME}}" (in the replacement arrays) and stays excluded above, or
# the check would never go false on a re-run.
PLACEHOLDERS_PRESENT=false
if [[ ${#CANDIDATE_FILES[@]} -gt 0 ]] \
    && grep -q '{{PROJECT_NAME}}' "${CANDIDATE_FILES[@]}" 2>/dev/null; then
  PLACEHOLDERS_PRESENT=true
fi

# --- Define replacements (order matters: longer/more-specific strings first) ---
# DB_PASSWORD is intentionally NOT here -- secrets never go into tracked files.
declare -a REPLACEMENT_KEYS=(
  "{{GITHUB_REPO_URL}}"
  "{{CONTAINER_REGISTRY}}"
  "{{STAGING_CONTAINER}}"
  "{{TICKET_PREFIX_LOWER}}"
  "{{DEV_CONTAINER}}"
  "{{DB_CONTAINER}}"
  "{{PROJECT_DOMAIN}}"
  "{{PROJECT_SHORT}}"
  "{{PROJECT_REPO}}"
  "{{PROJECT_NAME}}"
  "{{COMPANY_NAME}}"
  "{{AUTHOR_WEBSITE}}"
  "{{AUTHOR_FIRST_NAME}}"
  "{{AUTHOR_LAST_NAME}}"
  "{{AUTHOR_INITIALS}}"
  "{{AUTHOR_HANDLE}}"
  "{{AUTHOR_EMAIL}}"
  "{{AUTHOR_NAME}}"
  "{{SECURITY_EMAIL}}"
  "{{TICKET_PREFIX}}"
  "{{LINEAR_WORKSPACE}}"
  "{{MAIN_BRANCH}}"
  "{{ARCHITECT_GITHUB_HANDLE}}"
  "{{GITHUB_ORG}}"
  "{{DB_USER}}"
  "{{DB_NAME}}"
  "{{MCP_LINEAR_SERVER}}"
  "{{MCP_CONFLUENCE_SERVER}}"
  "{{MCP_JIRA_SERVER}}"
  "{{HARNESS_VERSION}}"
)

declare -a REPLACEMENT_VALS=(
  "${GITHUB_REPO_URL}"
  "${CONTAINER_REGISTRY}"
  "${STAGING_CONTAINER}"
  "${TICKET_PREFIX_LOWER}"
  "${DEV_CONTAINER}"
  "${DB_CONTAINER}"
  "${PROJECT_DOMAIN}"
  "${PROJECT_SHORT}"
  "${PROJECT_REPO}"
  "${PROJECT_NAME}"
  "${COMPANY_NAME}"
  "${AUTHOR_WEBSITE}"
  "${AUTHOR_FIRST_NAME}"
  "${AUTHOR_LAST_NAME}"
  "${AUTHOR_INITIALS}"
  "${AUTHOR_HANDLE}"
  "${AUTHOR_EMAIL}"
  "${AUTHOR_NAME}"
  "${SECURITY_EMAIL}"
  "${TICKET_PREFIX}"
  "${LINEAR_WORKSPACE}"
  "${MAIN_BRANCH}"
  "${ARCHITECT_GITHUB_HANDLE}"
  "${GITHUB_ORG}"
  "${DB_USER}"
  "${DB_NAME}"
  "${MCP_LINEAR_SERVER}"
  "${MCP_CONFLUENCE_SERVER}"
  "${MCP_JIRA_SERVER}"
  "${HARNESS_VERSION}"
)

if [[ "$PLACEHOLDERS_PRESENT" == false ]]; then
  echo "  Nothing to replace -- no {{PROJECT_NAME}} tokens remain (already bootstrapped)."
else
  # Build ONE sed -e chain with every non-empty replacement, in the declared
  # order (longer/more-specific keys first). Applying the whole chain in a
  # single sed invocation per file is byte-identical to running each
  # substitution as its own file-wide pass -- sed is line-oriented with no
  # cross-line state here -- but collapses 30 passes into one.
  SED_EXPRS=()
  _replacement_count=${#REPLACEMENT_KEYS[@]}
  _i=0
  while [ "$_i" -lt "$_replacement_count" ]; do
    OLD="${REPLACEMENT_KEYS[$_i]}"
    NEW="${REPLACEMENT_VALS[$_i]}"
    _i=$((_i + 1))

    # Skip if old == new or replacement value is empty (leave placeholder for
    # manual fill rather than blanking it).
    [[ "$OLD" == "$NEW" ]] && continue
    [[ -z "$NEW" ]] && continue

    echo "  Replacing '$OLD' → '$NEW'"

    OLD_ESC="$(_sed_escape "$OLD")"
    NEW_ESC="$(_sed_escape "$NEW")"
    SED_EXPRS+=(-e "s|${OLD_ESC}|${NEW_ESC}|g")
  done

  # ONE sed invocation per candidate file (all placeholders in the -e chain).
  # CANDIDATE_FILES already excludes the wizard's own source and the shared
  # excluded directories, so no per-file find/path filtering is needed here.
  if [[ ${#SED_EXPRS[@]} -gt 0 && ${#CANDIDATE_FILES[@]} -gt 0 ]]; then
    for file in "${CANDIDATE_FILES[@]}"; do
      _sed_inplace "${SED_EXPRS[@]}" "$file"
    done
  fi
fi

# --- Secrets: write DB_PASSWORD to .env, never to tracked files ---

echo ""
echo "Writing secrets to .env (never substituted into tracked files)..."

ENV_FILE="$REPO_ROOT/.env"
ENV_TEMPLATE_FILE="$REPO_ROOT/.env.template"

if [[ -n "$DB_PASSWORD" ]]; then
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$ENV_TEMPLATE_FILE" ]]; then
      cp "$ENV_TEMPLATE_FILE" "$ENV_FILE"
    else
      touch "$ENV_FILE"
    fi
  fi

  if grep -q '^DB_PASSWORD=' "$ENV_FILE" 2>/dev/null; then
    DB_PASSWORD_ESC="$(_sed_escape "$DB_PASSWORD")"
    _sed_inplace "s|^DB_PASSWORD=.*|DB_PASSWORD=\"${DB_PASSWORD_ESC}\"|" "$ENV_FILE"
  else
    {
      echo ""
      echo "# Database password (added by setup-template.sh; not committed to git)"
      echo "DB_PASSWORD=\"${DB_PASSWORD}\""
    } >> "$ENV_FILE"
  fi
  echo "  DB_PASSWORD written to .env (not to any tracked file)."
else
  echo "  No DB_PASSWORD provided; skipping .env secret write."
fi

echo ""
echo "Replacements complete."

# --- Remaining placeholders notice ---

# Reuses the candidate list (ABS-179) -- no fresh full-tree scan. Candidate
# paths are unchanged by the in-place substitution above, so re-reading them
# reports exactly the {{...}} tokens that survived (e.g. unfilled tech-stack
# placeholders). Excluded directories were never candidates, so they cannot
# leak into this report.
REMAINING=""
if [[ ${#CANDIDATE_FILES[@]} -gt 0 ]]; then
  REMAINING=$(grep -oh '{{[A-Z_]*}}' "${CANDIDATE_FILES[@]}" \
    2>/dev/null | sort -u | grep -v '^$' || true)
fi

if [[ -n "$REMAINING" ]]; then
  echo "NOTE: The following placeholders remain (customize manually in CLAUDE.md"
  echo "and other config files for your specific technology stack):"
  echo ""
  echo "$REMAINING"
  echo ""
  echo "These are typically filled in as you configure your project's tech stack."
fi

# ============================================================================
# Manifest generation (ABS-48)
# ============================================================================
# Decision: emit a minimal, schema-valid manifest via heredoc using the
# identity values we already collected. `sync-claude-harness.sh manifest init`
# is NOT reused here because it reads identity from team-config.json (which may
# not yet be populated at bootstrap) and hard-requires node. The heredoc path
# is dependency-free and works in every environment. Required schema fields
# (manifest_version + identity{PROJECT_NAME,PROJECT_REPO,PROJECT_SHORT,
# GITHUB_ORG,TICKET_PREFIX,MAIN_BRANCH}) are all provided.

MANIFEST_FILE="$REPO_ROOT/.harness-manifest.yml"

echo ""
echo "Generating .harness-manifest.yml..."

# YAML-escape a value for a double-quoted scalar (escape backslash and quote).
_yaml_escape() {
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

# Emit an identity key: value line, but only when the value is non-empty.
# Optional identity fields (e.g. AUTHOR_EMAIL, SECURITY_EMAIL) use
# `format: email`/`format: uri` in the schema under a strict FormatChecker;
# an empty string satisfies `type: string` but fails format validation, so
# omitting the key entirely (rather than writing "") keeps a bootstrap run
# with unset optional values schema-valid.
_emit_identity_field() {
  local key="$1" val="$2"
  [[ -z "$val" ]] && return 0
  echo "  ${key}: \"$(_yaml_escape "$val")\""
}

{
  echo "# ============================================================================="
  echo "# Harness Manifest - generated by scripts/setup-template.sh (bootstrap)"
  echo "# ============================================================================="
  echo "# Declares how this fork customizes the upstream SAFe Agentic Workflow harness."
  echo "# See docs/HARNESS_MANIFEST_SCHEMA.md and .harness-manifest.schema.json."
  echo "# Regenerate richer sync metadata with:"
  echo "#   ./scripts/sync-claude-harness.sh manifest init"
  echo "# ============================================================================="
  echo ""
  echo "manifest_version: \"1.1\""
  echo ""
  echo "identity:"
  # Required by .harness-manifest.schema.json -- always emitted (resolve_value
  # already hard-fails non-interactive runs when these are missing).
  echo "  PROJECT_NAME: \"$(_yaml_escape "$PROJECT_NAME")\""
  echo "  PROJECT_REPO: \"$(_yaml_escape "$PROJECT_REPO")\""
  echo "  PROJECT_SHORT: \"$(_yaml_escape "$PROJECT_SHORT")\""
  echo "  GITHUB_ORG: \"$(_yaml_escape "$GITHUB_ORG")\""
  echo "  TICKET_PREFIX: \"$(_yaml_escape "$TICKET_PREFIX")\""
  echo "  MAIN_BRANCH: \"$(_yaml_escape "$MAIN_BRANCH")\""
  # Optional -- omitted entirely when empty (see _emit_identity_field above).
  _emit_identity_field "PROJECT_DOMAIN" "$PROJECT_DOMAIN"
  _emit_identity_field "COMPANY_NAME" "$COMPANY_NAME"
  _emit_identity_field "AUTHOR_NAME" "$AUTHOR_NAME"
  _emit_identity_field "AUTHOR_FIRST_NAME" "$AUTHOR_FIRST_NAME"
  _emit_identity_field "AUTHOR_LAST_NAME" "$AUTHOR_LAST_NAME"
  _emit_identity_field "AUTHOR_HANDLE" "$AUTHOR_HANDLE"
  _emit_identity_field "AUTHOR_EMAIL" "$AUTHOR_EMAIL"
  _emit_identity_field "AUTHOR_WEBSITE" "$AUTHOR_WEBSITE"
  _emit_identity_field "SECURITY_EMAIL" "$SECURITY_EMAIL"
  _emit_identity_field "ARCHITECT_GITHUB_HANDLE" "$ARCHITECT_GITHUB_HANDLE"
  _emit_identity_field "LINEAR_WORKSPACE" "$LINEAR_WORKSPACE"
  _emit_identity_field "MCP_LINEAR_SERVER" "$MCP_LINEAR_SERVER"
  _emit_identity_field "MCP_CONFLUENCE_SERVER" "$MCP_CONFLUENCE_SERVER"
  _emit_identity_field "MCP_JIRA_SERVER" "$MCP_JIRA_SERVER"
  _emit_identity_field "DB_USER" "$DB_USER"
  _emit_identity_field "DB_NAME" "$DB_NAME"
  echo ""
  echo "# Rename mappings: upstream path -> local path (repo-root-relative in v1.1)."
  echo "renames: {}"
  echo ""
  echo "# Protected files: never overwritten during sync."
  echo "protected: []"
  echo ""
  echo "# Replaced files: fork maintains independently."
  echo "replaced: []"
  echo ""
  echo "# Sync behavior preferences."
  echo "sync:"
  # ABS-96: the SHIPPED harness now lives in the upstream "harness/claude"
  # namespace (source of truth), but a freshly-bootstrapped consuming project
  # has a live ".claude/" and no "harness/" dir — so the consumer-facing
  # sync_scope default stays ".claude/" (unchanged). This keeps consuming-project
  # bootstrap output byte-identical; the namespace is an upstream-source concept.
  echo "  sync_scope:"
  echo "    - \".claude/\""
  echo "  auto_substitute: true"
  echo "  backup: true"
  echo "  conflict_strategy: \"prompt\""
} > "$MANIFEST_FILE"

echo "  Wrote $MANIFEST_FILE (schema v1.1)."
echo "  For richer sync metadata (renames/protected/replaced) run:"
echo "    ./scripts/sync-claude-harness.sh manifest init"

# --- Write the active profile marker (ABS-48) ---
ACTIVE_PROFILE_FILE="$REPO_ROOT/.active-profile"
printf '%s\n' "$PROFILE_NAME" > "$ACTIVE_PROFILE_FILE"
echo "  Active profile '$PROFILE_NAME' recorded in .active-profile."

# ============================================================================
# Gap report (ABS-49)
# ============================================================================
# Reads the selected profile's profile.yaml with grep/sed (no new deps, same
# style as scripts/hooks/evolver-lifecycle.sh). For each capability:
#   required: true  -> provider must be != none  (mock = ready-with-note)
#   required: false -> reported informationally
# Overall verdict + blocking list written to bootstrap-gap-report.md.

PROFILE_YAML="$PROFILES_DIR/$PROFILE_NAME/profile.yaml"
GAP_REPORT="$REPO_ROOT/bootstrap-gap-report.md"

echo ""
echo "Building tooling-readiness gap report..."

# Extract a capability's provider value, strictly scoped to that capability's
# own block: from its "  <name>:" header up to (but excluding) the next
# same-indent ("  <key>:") capability key or any top-level (0-indent) key.
# This prevents bleeding into the NEXT capability's "provider:" line when the
# current capability doesn't declare one -- a missing required provider must
# be reported as MISSING, never masked by a neighboring block's value.
_cap_provider() {
  local cap="$1"
  awk -v cap="  ${cap}:" '
    $0 == cap { infield=1; print; next }
    infield && (/^  [a-zA-Z0-9_-]+:/ || /^[a-zA-Z]/) { exit }
    infield { print }
  ' "$PROFILE_YAML" 2>/dev/null \
    | grep 'provider:' | head -1 \
    | sed 's/.*provider:[[:space:]]*//' | sed 's/[[:space:]]*#.*//' \
    | tr -d ' ' || echo ""
}

# Required capabilities (mandatory tooling layer, blueprint §19).
REQUIRED_CAPS="task-tracking docs git notifications"
# Conditionally-mandatory capabilities (informational).
CONDITIONAL_CAPS="database deploy design-system secrets evolution knowledge"

BLOCKING=()
READY=true

{
  echo "# Bootstrap Gap Report"
  echo ""
  echo "- Profile: \`$PROFILE_NAME\`"
  echo "- Generated by: \`scripts/setup-template.sh\`"
  echo ""
  echo "## Mandatory capabilities (required for agentic execution)"
  echo ""
  echo "| Capability | Provider | Status |"
  echo "|------------|----------|--------|"
} > "$GAP_REPORT"

for cap in $REQUIRED_CAPS; do
  prov="$(_cap_provider "$cap")"
  status=""
  case "$prov" in
    ""|none)
      status="MISSING"
      BLOCKING+=("$cap (provider: ${prov:-unset})")
      READY=false
      ;;
    mock)
      status="mocked (ready-with-note)"
      ;;
    *)
      status="ready"
      ;;
  esac
  echo "| $cap | ${prov:-unset} | $status |" >> "$GAP_REPORT"
done

{
  echo ""
  echo "## Conditionally-mandatory capabilities (informational)"
  echo ""
  echo "| Capability | Provider | Status |"
  echo "|------------|----------|--------|"
} >> "$GAP_REPORT"

for cap in $CONDITIONAL_CAPS; do
  prov="$(_cap_provider "$cap")"
  status=""
  case "$prov" in
    ""|none) status="not configured" ;;
    mock)    status="mocked" ;;
    *)       status="configured" ;;
  esac
  echo "| $cap | ${prov:-unset} | $status |" >> "$GAP_REPORT"
done

{
  echo ""
  echo "## Verdict"
  echo ""
} >> "$GAP_REPORT"

if [[ "$READY" == true ]]; then
  echo "**ready for agentic execution**" >> "$GAP_REPORT"
  echo "  Gap report: ready for agentic execution."
else
  {
    echo "**NOT ready for agentic execution**"
    echo ""
    echo "Blocking gaps (required capability without a provider):"
    echo ""
    for b in "${BLOCKING[@]}"; do
      echo "- $b"
    done
  } >> "$GAP_REPORT"
  echo "  Gap report: NOT ready for agentic execution."
  echo "  Blocking: ${BLOCKING[*]}"
fi
echo "  Wrote $GAP_REPORT."

# Non-interactive mode fails on NOT-ready unless --allow-gaps.
if [[ "$READY" == false && "$NON_INTERACTIVE" == true && "$ALLOW_GAPS" == false ]]; then
  echo "" >&2
  echo "ERROR: profile '$PROFILE_NAME' is NOT ready for agentic execution." >&2
  echo "See $GAP_REPORT. Re-run with --allow-gaps to proceed anyway." >&2
  exit 6
fi

# ============================================================================
# Optional finalize (ABS-50): delete template-only artifacts.
# ============================================================================
# The wizard NO LONGER self-deletes by default -- that broke idempotency and
# re-runs. Deletion now only happens behind --finalize.
if [[ "$FINALIZE" == true ]]; then
  echo ""
  echo "Finalizing: removing template-only files..."
  rm -f "$REPO_ROOT/TEMPLATE_SETUP.md"
  rm -f "$REPO_ROOT/scripts/setup-template.sh"
  echo "  Removed TEMPLATE_SETUP.md and scripts/setup-template.sh."
fi

# --- Optional: reinitialize git ---

GIT_ALREADY_REINIT=false
# Heuristic: if the first commit message mentions the harness init, treat the
# repo as already reinitialized and skip the prompt (idempotency).
if [[ -d "$REPO_ROOT/.git" ]]; then
  if git -C "$REPO_ROOT" log --oneline 2>/dev/null \
       | grep -q "initialize .* from AI Agent Harness template"; then
    GIT_ALREADY_REINIT=true
  fi
fi

if [[ "$GIT_ALREADY_REINIT" == true ]]; then
  echo ""
  echo "Git history already reinitialized from template; skipping reinit prompt."
elif [[ "$NON_INTERACTIVE" == true ]]; then
  : # never touch git history non-interactively
else
  echo ""
  read -rp "Reinitialize git history? This removes all previous commits. (y/N): " REINIT
  if [[ "$REINIT" == "y" || "$REINIT" == "Y" ]]; then
    rm -rf "$REPO_ROOT/.git"
    cd "$REPO_ROOT"
    git init -b "$MAIN_BRANCH"
    git add -A
    git commit -m "feat: initialize ${PROJECT_NAME} from AI Agent Harness template"
    echo "Fresh git history created."
  fi
fi

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Review the changes: git diff (if you didn't reinit)"
echo "  2. Review bootstrap-gap-report.md and close any MISSING capabilities"
echo "  3. Update .env.template with your actual service keys"
echo "  4. Customize CLAUDE.md technology stack section (fill remaining {{...}} placeholders)"
echo "  5. Configure your task tracker (see docs/onboarding/)"
echo "  6. Push to your remote: git remote add origin ${GITHUB_REPO_URL}.git && git push -u origin ${MAIN_BRANCH}"
if [[ "$FINALIZE" == false ]]; then
  echo ""
  echo "When fully set up, run 'bash scripts/setup-template.sh --finalize' to remove"
  echo "the wizard and TEMPLATE_SETUP.md."
fi
echo ""
