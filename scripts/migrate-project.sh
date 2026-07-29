#!/bin/bash
#
# =============================================================================
# migrate-project.sh -- Mechanical boilerplate-migration driver (ABS-227)
# =============================================================================
# Replaces the LLM-improvised migration procedure with a deterministic bash
# driver. Everything mechanical -- version detection, ownership classification,
# batch hashing, drift detection, replace/add, marker stamping, branch+commit,
# report generation (with pre-computed `diff -u` conflict hunks) -- runs HERE,
# not in an LLM context. The migration seat then only READS the report's
# conflict hunks and writes the human summary/recommendations.
#
# This driver SHIPS WITH the boilerplate and RUNS FROM the current boilerplate
# checkout against a target project (resolves the old-project/new-logic
# chicken-and-egg problem). See docs/sop/BOILERPLATE_MIGRATION_SOP.md and
# adrs/agentic/ADR-A-0008-boilerplate-ownership-and-upgrades.md.
#
# Usage:
#   scripts/migrate-project.sh <target-project-path> [OPTIONS]
#
#   <target-project-path>   Consuming project to migrate (required).
#   --source <path>         Boilerplate checkout to migrate FROM (default: the
#                           repo containing this script). The "to" side.
#   --format md|json        Machine-readable stdout summary format (default md).
#   --no-commit             Apply changes on the branch but do not commit
#                           (for inspection/testing).
#   --allow-untracked       Proceed even when untracked target files sit on the
#                           boilerplate-owned surface (they are then migrated as
#                           boilerplate: classified, possibly replaced, committed).
#   -h, --help              Show usage.
#
# Exit codes:
#   0  success (migration applied) OR already up to date
#   2  usage error
#   3  target has no .boilerplate-version marker           (adoption, not migration)
#   4  target version NEWER than source                    (stale checkout)
#   5  target has tracked modifications, or untracked files on the boilerplate-owned
#      surface (ABS-277). Unrelated untracked files never block; --allow-untracked
#      forces past owned-surface collisions.
#   6  ownership map missing                               (no LLM fallback, ABS-227 AC4)
#   7  a declared migration step failed
#   8  target path invalid / not a git repo
#   9  cannot establish drift baseline (missing v<from> tag in source)
#
# Bash 3.2 / BSD-safe: no associative arrays, no mapfile, no GNU-only flags,
# no jq/yq/python (ADR-A-0009 zero-dep bash).
# =============================================================================

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Output helpers (stderr; stdout is reserved for the machine summary) -----
if [ -t 2 ]; then
    GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
else
    GREEN=''; BLUE=''; YELLOW=''; RED=''; NC=''
fi
log()  { echo -e "${BLUE}[migrate]${NC} $*" >&2; }
ok()   { echo -e "${GREEN}[migrate]${NC} $*" >&2; }
warn() { echo -e "${YELLOW}[migrate]${NC} $*" >&2; }
abort() { echo -e "${RED}ERROR:${NC} $*" >&2; exit "${2:-2}"; }

usage() { sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'; }

# --- Portable SHA-256 helper -------------------------------------------------
hash_stdin() {
    if command -v shasum >/dev/null 2>&1; then shasum -a 256 | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print $1}'
    else abort "no sha256 tool (shasum/sha256sum) available" 2; fi
}
# Hash a file's raw bytes by path (used by the fork-budget de-fork check, ABS-259).
hash_file() { hash_stdin < "$1"; }

# --- Agentic-ADR acceptance frontmatter (ADR-A-0008 special case) -------------
# For `adrs/agentic/ADR-*.md` the CONTENT is boilerplate-owned but the acceptance
# frontmatter (status / accepted_by / accepted_date) is PROJECT-owned. Drift
# detection must ignore those fields, and a content replace must PRESERVE the
# target's acceptance frontmatter (ADR-A-0008; SOP §3). These helpers implement
# exactly that so an accepted ADR is classified REPLACE, not a spurious CONFLICT.
is_agentic_adr() { case "$1" in adrs/agentic/ADR-*.md) return 0 ;; *) return 1 ;; esac; }

# Strip the acceptance frontmatter fields from the leading `---` block (stdin->stdout).
strip_acceptance_fields() {
    awk '
        NR==1 && $0=="---" { infm=1; print; next }
        infm && $0=="---"  { infm=0; print; next }
        infm && /^(status|accepted_by|accepted_date):/ { next }
        { print }
    '
}
# Hash an agentic-ADR's content by path with acceptance frontmatter stripped
# (used by the fork-budget de-fork check for ADR exception paths, ABS-259).
hash_adr_content_file() { strip_acceptance_fields < "$1" | hash_stdin; }
# --- Setup-token normalization (ABS-249) -------------------------------------
# A consuming project's files are SETUP-INSTANTIATED: setup-template.sh replaced
# the TICKET_PREFIX / MAIN_BRANCH / HARNESS_VERSION / ... tokens with the
# project's values. The boilerplate source still carries the literal {{TOKEN}}s.
# Comparing the two raw would flag every tokened file as drift at EVERY migration
# (the consumer saw ADR-A-0005/0012/0014 re-conflict three releases running).
#
# So: before hashing, the UPSTREAM side (baseline + source) is run through the
# project's substitution map, and both sides are CR-normalized. The same map is
# applied on the WRITE path, so replaced/added files land instantiated instead of
# carrying literal tokens into the project (ABS-249).
#
# The map is evidence-based: identity + substitutions from the target's
# .harness-manifest.yml, plus the four derived tokens setup-template.sh computes.
# No manifest -> empty map -> pre-ABS-249 behavior (CR normalization only).
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# Parse a simple `key:` -> `  KEY: "value"` YAML map; prints KEY<TAB>VALUE.
parse_yaml_map() {
    awk -v key="$2" '
        $0 ~ "^" key ":" { inmap=1; next }
        inmap && /^[^[:space:]#]/ { inmap=0 }
        inmap && /^[[:space:]]+[A-Za-z_][A-Za-z0-9_]*:/ {
            line=$0; sub(/^[[:space:]]+/,"",line)
            k=line; sub(/:.*$/,"",k)
            v=line; sub(/^[^:]*:[[:space:]]*/,"",v)
            sub(/[[:space:]]+$/,"",v); sub(/^"/,"",v); sub(/"$/,"",v)
            # Skip still-uninstantiated values ("{{FOO}}") -- they carry no info.
            if (v != "" && v !~ /^\{\{.*\}\}$/) print k "\t" v
        }
    ' "$1"
}

# Escape a value for use as a sed replacement with `|` as the delimiter.
sed_escape_repl() { printf '%s' "$1" | sed -e 's/[\\|&]/\\&/g'; }

# Write a sed script instantiating every mapped {{TOKEN}}. $1=out, $2=HARNESS_VERSION.
# Order = precedence (sed's first match wins): explicit substitutions, then
# identity, then derived. The TICKET_PREFIX token cannot shadow the
# TICKET_PREFIX_LOWER one: the closing braces are part of the pattern, so no
# length sort is needed.
#
# CAUTION: no line in this file may contain a literal setup replacement key --
# setup sweeps migrate-project.sh, so any such key becomes a project value in
# the consumer's copy (see the %s construction below). Guarded by
# tests/test-migrate-project.sh (no-literal-token assertion).
build_token_sed() {
    local out="$1" hv="$2" k v
    : > "$out"
    printf '%s\n%s\n%s\n' "$SUBST_PAIRS" "$IDENTITY_PAIRS" "$DERIVED_PAIRS" \
    | while IFS="$(printf '\t')" read -r k v; do
        [ -n "$k" ] && [ -n "$v" ] || continue
        printf 's|{{%s}}|%s|g\n' "$k" "$(sed_escape_repl "$v")" >> "$out"
    done
    # NOTE: built via %s -- this file is itself swept by setup-template.sh, so a
    # literal replacement key here would be instantiated in the consumer's copy
    # (it would emit `s|v2.25.0|...|` and rewrite version strings it writes).
    printf 's|{{%s}}|%s|g\n' HARNESS_VERSION "$hv" >> "$out"
}

# Which files does setup instantiate? EXACTLY setup-template.sh's own sweep set
# (SWEEP_INCLUDE_GLOBS + its `--exclude=setup-template.sh`). The two lists must
# agree: a file setup does NOT substitute keeps its literal {{TOKEN}}s in the
# project, so normalizing it here would invent drift that isn't there.
# tests/test-migrate-project.sh guards this parity mechanically.
# setup-template.sh excludes ITSELF because its REPLACEMENT_KEYS array literally
# contains the PROJECT_NAME token & co -- substituting the wizard would destroy it.
is_substitutable() {
    case "${1##*/}" in
        setup-template.sh)                                  return 1 ;;
        NOTICE|LICENSE|CODEOWNERS|.env.template|.gitignore) return 0 ;;
    esac
    case "$1" in
        *.md|*.json|*.yml|*.yaml|*.sh|*.py|*.txt|*.toml|*.bib|*.cff|*.mjs|*.ts) return 0 ;;
        *) return 1 ;;
    esac
}

# Normalize an UPSTREAM stream (baseline/source): instantiate tokens + strip CR.
norm_upstream() { LC_ALL=C sed -f "$1" | tr -d '\r'; }
# Normalize a TARGET stream: already instantiated -> strip CR only.
norm_target() { tr -d '\r'; }

# True if $1 is a text file carrying {{TOKEN}}s (-I: binaries never match).
has_tokens() { LC_ALL=C grep -Iq '{{' "$1" 2>/dev/null; }

# True if the project's OWN token map still finds something to substitute in $1,
# i.e. the file carries tokens setup should already have instantiated (ABS-273).
# Deliberately narrower than has_tokens(): an UNMAPPED token is not residue.
has_mapped_residue() { ! LC_ALL=C sed -f "$SED_CUR" "$1" 2>/dev/null | cmp -s - "$1"; }

# Instantiate tokens in a written file, preserving its mode (cat > keeps the inode).
# $1 = repo-relative path, $2 = file to rewrite in place.
subst_in_place() {
    is_substitutable "$1" || return 0
    has_tokens "$2" || return 0
    LC_ALL=C sed -f "$SED_CUR" "$2" > "$TMP_DIR/subst" && cat "$TMP_DIR/subst" > "$2"
}

# Read one frontmatter field value from a file (empty if absent).
fm_field() {
    awk -v k="$2" '
        NR==1 && $0=="---" { infm=1; next }
        infm && $0=="---"  { exit }
        infm && index($0, k ":")==1 { v=$0; sub("^" k ":[[:space:]]*","",v); print v; exit }
    ' "$1"
}

# --- Semver compare: prints -1 / 0 / 1 for a<b / a==b / a>b ------------------
vnum() {
    # echo numeric weight of a semver (major*1e6 + minor*1e3 + patch)
    echo "$1" | awk -F. '{printf "%d\n", ($1+0)*1000000 + ($2+0)*1000 + ($3+0)}'
}

# ============================================================================
# Argument parsing
# ============================================================================
TARGET=""
SOURCE="$DEFAULT_SOURCE"
FORMAT="md"
DO_COMMIT="true"
ALLOW_UNTRACKED="false"

while [ $# -gt 0 ]; do
    case "$1" in
        --source) SOURCE="${2:-}"; shift 2 ;;
        --format) FORMAT="${2:-}"; shift 2 ;;
        --no-commit) DO_COMMIT="false"; shift ;;
        --allow-untracked) ALLOW_UNTRACKED="true"; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) abort "unknown option: $1" 2 ;;
        *) [ -z "$TARGET" ] && TARGET="$1" || abort "unexpected argument: $1" 2; shift ;;
    esac
done

[ -n "$TARGET" ] || { usage; exit 2; }
case "$FORMAT" in md|json) ;; *) abort "--format must be md or json" 2 ;; esac

TARGET="$(cd "$TARGET" 2>/dev/null && pwd || true)"
[ -n "$TARGET" ] && [ -d "$TARGET" ] || abort "target path invalid or not a directory" 8
[ -d "$TARGET/.git" ] || git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1 || abort "target is not a git repository: $TARGET" 8
SOURCE="$(cd "$SOURCE" && pwd)"

# ============================================================================
# Step 1: Version detection + aborts
# ============================================================================
[ -f "$SOURCE/.boilerplate-version" ] || abort "source checkout has no .boilerplate-version: $SOURCE" 2
TO="$(tr -d ' \n\r\t' < "$SOURCE/.boilerplate-version")"

if [ ! -f "$TARGET/.boilerplate-version" ]; then
    abort "$(printf '%s\n' \
        "$TARGET has no .boilerplate-version marker." \
        "Every boilerplate-derived project carries this marker from creation." \
        "This project appears not to have been created from the boilerplate." \
        "Aborting -- existing-project adoption requires a human-approved migration plan.")" 3
fi
FROM="$(tr -d ' \n\r\t' < "$TARGET/.boilerplate-version")"

log "migration $FROM -> $TO   (source: $SOURCE, target: $TARGET)"

if [ "$(vnum "$FROM")" = "$(vnum "$TO")" ]; then
    ok "already up to date at $FROM -- no branch, no diff."
    if [ "$FORMAT" = "json" ]; then
        echo "{\"status\":\"up-to-date\",\"from\":\"$FROM\",\"to\":\"$TO\"}"
    else
        echo "STATUS up-to-date from=$FROM to=$TO"
    fi
    exit 0
fi
if [ "$(vnum "$FROM")" -gt "$(vnum "$TO")" ]; then
    abort "target version $FROM is NEWER than source $TO -- you are running from a stale checkout. Update the boilerplate checkout and re-run." 4
fi

# --- Clean-tree gate, part 1: tracked modifications (ABS-277) ----------------
# TRACKED modifications always block: the migration commit must stay an isolated,
# reviewable diff, and an overwrite of a locally modified tracked file would bury
# the local change in the migration commit.
#
# UNTRACKED files are NOT checked here -- an untracked file only matters if it
# collides with the boilerplate-owned surface, which is not known until the
# ownership map is parsed. That check is part 2, after Step 3. Blocking on ANY
# untracked file (pre-ABS-277 behavior) made every unrelated build artefact
# (the consumer's extension/package-lock.json) an exit-5 stop sign.
TRACKED_DIRTY="$(git -C "$TARGET" -c core.quotePath=false status --porcelain --untracked-files=no)"
if [ -n "$TRACKED_DIRTY" ]; then
    abort "$(printf '%s\n%s\n%s\n' \
        "target has uncommitted changes to TRACKED files -- the migration diff must stay isolated:" \
        "$(printf '%s\n' "$TRACKED_DIRTY" | sed 's/^/    /')" \
        "Commit or stash them before migrating.")" 5
fi

# ============================================================================
# Step 1b: Build the project's setup-token map (ABS-249)
#   Two sed scripts, identical but for the HARNESS_VERSION token:
#     SED_BASE -> v$FROM : what setup/the last migration instantiated in the
#                          target, so the v<from> baseline hashes to the target.
#     SED_CUR  -> v$TO   : the version now being written/compared.
# ============================================================================
MANIFEST="$TARGET/.harness-manifest.yml"
IDENTITY_PAIRS=""; SUBST_PAIRS=""; DERIVED_PAIRS=""
if [ -f "$MANIFEST" ]; then
    IDENTITY_PAIRS="$(parse_yaml_map "$MANIFEST" identity || true)"
    SUBST_PAIRS="$(parse_yaml_map "$MANIFEST" substitutions || true)"
fi

# Derived tokens -- same derivations as scripts/setup-template.sh.
tok_get() {
    printf '%s\n%s\n' "$SUBST_PAIRS" "$IDENTITY_PAIRS" \
        | awk -F'\t' -v k="$1" '$1==k && $2!="" {print $2; exit}'
}
add_derived() { [ -n "$2" ] || return 0; DERIVED_PAIRS="${DERIVED_PAIRS}${1}"$'\t'"${2}"$'\n'; }

_tp="$(tok_get TICKET_PREFIX)"; _org="$(tok_get GITHUB_ORG)"; _repo="$(tok_get PROJECT_REPO)"
_fn="$(tok_get AUTHOR_FIRST_NAME)"; _ln="$(tok_get AUTHOR_LAST_NAME)"
add_derived TICKET_PREFIX_LOWER "$(printf '%s' "$_tp" | tr '[:upper:]' '[:lower:]')"
[ -n "$_org" ] && [ -n "$_repo" ] && add_derived GITHUB_REPO_URL "https://github.com/${_org}/${_repo}"
[ -n "$_fn" ]  && [ -n "$_ln" ]   && add_derived AUTHOR_INITIALS "$(printf '%s' "$_fn" | cut -c1). $(printf '%s' "$_ln" | cut -c1)."

SED_BASE="$TMP_DIR/tokens-from.sed"; SED_CUR="$TMP_DIR/tokens-to.sed"
SED_NOOP="$TMP_DIR/noop.sed"; : > "$SED_NOOP"
build_token_sed "$SED_BASE" "v${FROM}"
build_token_sed "$SED_CUR"  "v${TO}"
n_tokens="$(grep -c . "$SED_CUR" 2>/dev/null || echo 0)"
if [ -f "$MANIFEST" ]; then
    log "setup tokens: $n_tokens (from $(basename "$MANIFEST")) -- normalized before diff and on write"
else
    warn "no .harness-manifest.yml in target -- token normalization limited to the HARNESS_VERSION token + CR"
fi

# ============================================================================
# Step 2: Ownership map (STRICT -- no LLM fallback, ABS-227 AC4 / ADR-A-0008)
# ============================================================================
OWNERSHIP_MAP="$SOURCE/.agentic/upgrade/ownership.yaml"
if [ ! -f "$OWNERSHIP_MAP" ]; then
    abort "$(printf '%s\n' \
        "Ownership map not found: $OWNERSHIP_MAP" \
        "The migration driver classifies files STRICTLY from the ownership map;" \
        "there is no LLM tree-classification fallback (ADR-A-0008, ABS-227)." \
        "Handlungsanweisung: ensure the source boilerplate checkout ships" \
        ".agentic/upgrade/ownership.yaml (generated at setup/release). Re-run once present.")" 6
fi
log "ownership map: $OWNERSHIP_MAP"

# Parse the two lists from the ownership map (simple, regular YAML):
#   boilerplate_owned:            -> owned prefixes/paths
#   project_owned_exceptions:     -> paths never touched
parse_yaml_list() {
    # $1 = file, $2 = top-level key; prints one entry per line (unquoted)
    awk -v key="$2" '
        $0 ~ "^" key ":" { inlist=1; next }
        inlist && /^[^[:space:]]/ { inlist=0 }
        inlist && /^[[:space:]]*-[[:space:]]/ {
            s=$0; sub(/^[[:space:]]*-[[:space:]]*/,"",s)
            # Comment BEFORE quotes: `- "scripts/foo.sh"  # note` must not leave a
            # trailing quote on the path -- the pathspec would then match nothing
            # and the file would silently drop out of the managed surface (ABS-259).
            sub(/[[:space:]]+#.*$/,"",s); sub(/[[:space:]]+$/,"",s)
            sub(/^"/,"",s); sub(/"$/,"",s)
            if (s != "") print s
        }
    ' "$1"
}

# Parse project_owned_exceptions as records: path <TAB> kind <TAB> upstream_ref
# <TAB> since (ADR-A-0008 Amendment 2026-07-13). `kind` defaults to `fork` when
# absent, so a legacy bare-path entry stays a VALID exception (migration still
# never touches it) but reports as an unattributed fork. Absent fields are
# emitted as "-" so no field is ever empty -- tab is IFS-whitespace in `read`,
# which would collapse empty fields and shift the columns.
parse_exceptions_table() {
    awk '
        function clean(v) {
            sub(/[[:space:]]+#.*$/,"",v)
            sub(/^[[:space:]]+/,"",v); sub(/[[:space:]]+$/,"",v)
            sub(/^"/,"",v); sub(/"$/,"",v)
            return v
        }
        function flush() {
            if (p != "") printf "%s\t%s\t%s\t%s\n", p, (k=="" ? "fork" : k), (u=="" ? "-" : u), (s=="" ? "-" : s)
            p=""; k=""; u=""; s=""
        }
        $0 ~ "^project_owned_exceptions:" { inlist=1; next }
        !inlist { next }
        /^[^[:space:]]/ { flush(); inlist=0; next }
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*-[[:space:]]/ {
            flush()
            v=$0; sub(/^[[:space:]]*-[[:space:]]*/,"",v); sub(/^path:[[:space:]]*/,"",v)
            p=clean(v); next
        }
        /^[[:space:]]*kind:/         { v=$0; sub(/^[[:space:]]*kind:/,"",v);         k=clean(v); next }
        /^[[:space:]]*upstream_ref:/ { v=$0; sub(/^[[:space:]]*upstream_ref:/,"",v); u=clean(v); next }
        /^[[:space:]]*since:/        { v=$0; sub(/^[[:space:]]*since:/,"",v);        s=clean(v); next }
        END { flush() }
    ' "$1"
}

# Days between two ISO dates ($2 - $1), or "NA" if either is not YYYY-MM-DD.
# Pure awk (days-from-civil): `date -d` (GNU) and `date -j` (BSD) take different
# flags and this driver runs on consumer Linux CI *and* macOS dev machines.
days_between() {
    awk -v a="$1" -v b="$2" '
        function dfc(y, m, d,   era, yoe, doy, doe) {
            if (m <= 2) y--
            era = int((y >= 0 ? y : y - 399) / 400)
            yoe = y - era * 400
            doy = int((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1
            doe = yoe * 365 + int(yoe / 4) - int(yoe / 100) + doy
            return era * 146097 + doe - 719468
        }
        function parse(s,   f) {
            if (s !~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/) return "NA"
            split(s, f, "-")
            return dfc(f[1] + 0, f[2] + 0, f[3] + 0)
        }
        BEGIN {
            x = parse(a); y = parse(b)
            if (x == "NA" || y == "NA") { print "NA"; exit }
            print y - x
        }
    '
}

OWNED_PREFIXES="$(parse_yaml_list "$OWNERSHIP_MAP" "boilerplate_owned")"

# project_owned_exceptions = SOURCE ownership.yaml  ∪  TARGET ownership.local.yaml
# (ABS-264). ownership.local.yaml is PROJECT-owned: a consuming project declares
# its OWN forks/opt-outs there so the driver HONORS them and the fork budget
# GRADES them. Before ABS-264 the map was read only from $SOURCE, so a consumer's
# declaration was silently ignored (and both the fork and the edited map landed in
# permanent CONFLICT noise on every migration).
#
# SUBTRACT-ONLY invariant (AC2): only `project_owned_exceptions` is unioned from
# the local map -- `boilerplate_owned` stays SOURCE-authoritative. A local map can
# therefore only ADD an exception (subtract a file from the managed surface),
# never extend it: upstream never loses the ability to grow its managed surface,
# and a consumer cannot withhold upstream files it never declared. The
# over-broad-local-exception risk (`- scripts/` withholding every upstream fix) is
# exactly what the fork budget below renders visible/red.
LOCAL_OWNERSHIP_MAP="$TARGET/.agentic/upgrade/ownership.local.yaml"
if [ -f "$LOCAL_OWNERSHIP_MAP" ] && grep -q '^boilerplate_owned:' "$LOCAL_OWNERSHIP_MAP" 2>/dev/null; then
    warn "ownership.local.yaml declares boilerplate_owned: -- IGNORED. The local map is SUBTRACT-ONLY (ADR-A-0008 / ABS-264); boilerplate_owned stays source-authoritative."
fi

# Exception RECORDS (path <TAB> kind <TAB> upstream_ref <TAB> since) come from the
# SAME parser that grades them in the fork budget below, so the classifier and the
# report can never disagree about what an exception is (ABS-259). Read the union
# ONCE into EXCEPTIONS_TABLE and reuse it for both the classifier (field 1) and
# the fork-budget report -- a divergence there means the report grades an entry
# the classifier ignored, i.e. it reports on a file it actually overwrote.
EXCEPTIONS_TABLE="$(
    parse_exceptions_table "$OWNERSHIP_MAP"
    if [ -f "$LOCAL_OWNERSHIP_MAP" ]; then parse_exceptions_table "$LOCAL_OWNERSHIP_MAP"; fi
)"

# The target manifest's `protected:` list is folded into the exception set too
# (ADR-A-0008 Amendment 2026-07-14, Q4). A consumer already declares its
# untouchable harness files there for sync-claude-harness.sh; now that migration
# actually reaches the harness, it must honor the SAME declaration or it would
# overwrite files the consumer explicitly fenced off. Path normalization mirrors
# the harness loader exactly (docs/HARNESS_MANIFEST_SCHEMA.md): a v1.1 entry is
# already root-relative; a v1.0 entry has no domain prefix and gets `.claude/`.
# These are NOT graded by the fork budget -- they are the manifest's own surface,
# not ownership-map entries, so they stay out of EXCEPTIONS_TABLE.
manifest_protected() {
    [ -f "$MANIFEST" ] || return 0
    parse_yaml_list "$MANIFEST" protected | while IFS= read -r p; do
        [ -n "$p" ] || continue
        case "$p" in
            .claude/*|.gemini/*|.codex/*|.cursor/*|.agents/*|dark-factory/*) printf '%s\n' "$p" ;;
            *) printf '.claude/%s\n' "$p" ;;
        esac
    done
}

EXCEPTIONS="$( { printf '%s\n' "$EXCEPTIONS_TABLE" | cut -f1; manifest_protected; } | sed '/^$/d' | sort -u )"
[ -n "$OWNED_PREFIXES" ] || abort "ownership map has an empty boilerplate_owned list" 6

# --- Harness provider-domain gate (ADR-A-0008 Amendment 2026-07-14, Q2) ------
# The migration surface equals the INSTALL surface. `.claude` is the schema
# default scope; the other five provider domains migrate ONLY when the target
# manifest's `sync_scope` adopts them. Without this gate a Claude-only consumer
# would be handed 232 files it never asked for (.gemini 87, .agents 95,
# dark-factory 19, .cursor 18, .codex 13) as ADDs on its next upgrade.
# Same field sync-claude-harness.sh reads; it nests under `sync:`, so the reader
# is indent-tolerant and tolerates the schema's trailing slashes (".gemini/").
GATED_DOMAINS=".gemini .codex .cursor .agents dark-factory"
SYNC_SCOPE=""
if [ -f "$MANIFEST" ]; then
    SYNC_SCOPE="$(awk '
        /^[[:space:]]*sync_scope:/ { inlist=1; next }
        inlist && /^[[:space:]]*-[[:space:]]/ {
            s=$0; sub(/^[[:space:]]*-[[:space:]]*/,"",s)
            sub(/[[:space:]]+#.*$/,"",s); sub(/[[:space:]]+$/,"",s)
            gsub(/["\047]/,"",s); sub(/\/$/,"",s)
            if (s != "") print s
            next
        }
        inlist { inlist=0 }
    ' "$MANIFEST")"
fi
[ -n "$SYNC_SCOPE" ] || SYNC_SCOPE=".claude"   # schema default

in_sync_scope() {
    # false only for a GATED provider domain the target has not adopted;
    # `.claude/` and every non-harness path are always in scope.
    local p="$1" d s
    for d in $GATED_DOMAINS; do
        case "$p" in
            "$d"/*)
                for s in $SYNC_SCOPE; do [ "$s" = "$d" ] && return 0; done
                return 1 ;;
        esac
    done
    return 0
}

is_exception() {
    # true if path $1 is under any project-owned exception prefix
    local p="$1" ex
    for ex in $EXCEPTIONS; do
        case "$p" in "$ex"|"$ex"/*|"${ex%/}"/*) return 0 ;; esac
    done
    return 1
}

# ============================================================================
# Step 3: Enumerate the boilerplate-owned file set (index-scoped, exclusions
# applied by git ls-files -- never walks worktrees/node_modules/etc.)
# ============================================================================
OWNED_FILES="$(
    for pfx in $OWNED_PREFIXES; do
        git -C "$SOURCE" ls-files -- "$pfx" 2>/dev/null
    done | sort -u
)"
[ -n "$OWNED_FILES" ] || abort "no boilerplate-owned files enumerated from the map (is the source a git checkout with these paths tracked?)" 2

# --- Clean-tree gate, part 2: colliding untracked files (ABS-277) -------------
# The migration set is OWNED_FILES minus the project-owned exceptions -- exactly the
# paths the driver manages. The classifier keys on file EXISTENCE, not on git
# tracking, so an untracked target file ON one of those paths is picked up and
# migrated AS boilerplate: hashed against the baseline, replaced if it matches it,
# and committed. So it blocks; --allow-untracked opts into that handling. Every
# other untracked file is none of the migration's business: it neither blocks nor
# enters the migration commit.
MIGRATION_SET="$TMP_DIR/migration-set.txt"
for path in $OWNED_FILES; do
    is_exception "$path" || printf '%s\n' "$path"
done > "$MIGRATION_SET"

# PRESERVED_UNTRACKED = the untracked files we deliberately tolerate. The commit
# step (`git add -A`) would otherwise sweep them into the migration commit, so it
# unstages exactly these paths -- they stay untracked on disk, as they were.
PRESERVED_UNTRACKED="$TMP_DIR/preserved-untracked.txt"; : > "$PRESERVED_UNTRACKED"

# -z, not plain --porcelain: the latter C-quotes any path holding a space, a double
# quote or a backslash ("my notes.txt", quotes included). core.quotePath=false does
# NOT suppress that -- it only governs non-ASCII bytes. A quoted path would miss its
# unstage pathspec below and land in the migration commit. -z never quotes.
# (Paths with literal newlines stay unsupported: pathological, and no worse than before.)
UNTRACKED="$(git -C "$TARGET" status --porcelain --untracked-files=all -z \
    | tr '\0' '\n' | sed -n 's/^?? //p')"
if [ -n "$UNTRACKED" ]; then
    COLLIDING="$(printf '%s\n' "$UNTRACKED" | grep -Fxf "$MIGRATION_SET" || true)"
    if [ -n "$COLLIDING" ]; then
        if [ "$ALLOW_UNTRACKED" = "true" ]; then
            warn "$(printf '%s\n%s' \
                "--allow-untracked: $(printf '%s\n' "$COLLIDING" | grep -c .) untracked file(s) on the boilerplate-owned surface are being migrated as boilerplate:" \
                "$(printf '%s\n' "$COLLIDING" | sed 's/^/    /')")"
        else
            abort "$(printf '%s\n%s\n%s\n%s\n' \
                "untracked target files sit ON the boilerplate-owned surface. Migration would treat them" \
                "as installed boilerplate (classify against the baseline, possibly overwrite, and commit them):" \
                "$(printf '%s\n' "$COLLIDING" | sed 's/^/    /')" \
                "Commit, move, or delete them -- or re-run with --allow-untracked to migrate them anyway.")" 5
        fi
    fi
    # Everything else is off-surface and none of the migration's business: keep it
    # untracked and OUT of the migration commit (ABS-277 AC1).
    printf '%s\n' "$UNTRACKED" | grep -Fxvf "$MIGRATION_SET" > "$PRESERVED_UNTRACKED" || true
fi

# Confirm the drift baseline tag exists in the source checkout.
if ! git -C "$SOURCE" rev-parse -q --verify "refs/tags/v${FROM}" >/dev/null 2>&1; then
    abort "source checkout has no tag v${FROM} -- cannot establish the drift baseline for the installed version. Fetch tags in the source checkout and re-run." 9
fi

# ============================================================================
# Step 4: Classify every owned file (batch hash, no context reads)
#   baseline = git show v<from>:<path>   (installed-version original)
#   REPLACE  : exists in target, hash == baseline           (unmodified)
#   ADD      : missing in target (new file, or new in <to>)
#   CONFLICT : exists in target, hash != baseline            (local drift)
#   SKIP     : hash already == current source (no-op)
# ============================================================================
REPLACE_LIST=""; ADD_LIST=""; CONFLICT_LIST=""; MISSING_SRC_LIST=""
n_replace=0; n_add=0; n_conflict=0; n_skip=0

for path in $OWNED_FILES; do
    is_exception "$path" && continue
    in_sync_scope "$path" || continue
    src_file="$SOURCE/$path"
    # A mapped path with no materialized file in the current source is skipped
    # (never a silent removal of the target's copy); noted below if it occurs.
    if [ ! -f "$src_file" ]; then
        MISSING_SRC_LIST="$MISSING_SRC_LIST$path
"; continue
    fi

    tgt_file="$TARGET/$path"

    if [ ! -f "$tgt_file" ]; then
        ADD_LIST="$ADD_LIST$path
"; n_add=$((n_add + 1)); continue
    fi

    # Compare NORMALIZED content (ABS-249): upstream sides get the project's
    # setup tokens instantiated, all sides get CRs stripped. Agentic ADRs
    # additionally drop the project-owned acceptance frontmatter (ADR-A-0008).
    if is_substitutable "$path"; then sed_b="$SED_BASE"; sed_c="$SED_CUR"
    else                             sed_b="$SED_NOOP"; sed_c="$SED_NOOP"; fi
    if is_agentic_adr "$path"; then
        baseline_hash="$(git -C "$SOURCE" show "v${FROM}:${path}" 2>/dev/null | strip_acceptance_fields | norm_upstream "$sed_b" | hash_stdin || true)"
        tgt_hash="$(strip_acceptance_fields < "$tgt_file" | norm_target | hash_stdin)"
        src_hash="$(strip_acceptance_fields < "$src_file" | norm_upstream "$sed_c" | hash_stdin)"
    else
        baseline_hash="$(git -C "$SOURCE" show "v${FROM}:${path}" 2>/dev/null | norm_upstream "$sed_b" | hash_stdin || true)"
        tgt_hash="$(norm_target < "$tgt_file" | hash_stdin)"
        src_hash="$(norm_upstream "$sed_c" < "$src_file" | hash_stdin)"
    fi

    if [ "$tgt_hash" = "$src_hash" ]; then
        n_skip=$((n_skip + 1)); continue                       # already current (content)
    fi
    if [ -n "$baseline_hash" ] && [ "$tgt_hash" = "$baseline_hash" ]; then
        REPLACE_LIST="$REPLACE_LIST$path
"; n_replace=$((n_replace + 1))                              # unmodified content -> replace
    else
        CONFLICT_LIST="$CONFLICT_LIST$path
"; n_conflict=$((n_conflict + 1))                            # real drift -> conflict
    fi
done

log "classified: replace=$n_replace add=$n_add conflict=$n_conflict already-current=$n_skip"

# ============================================================================
# Step 4b: Integrity check of the ADOPTED copies (ABS-273)
# ----------------------------------------------------------------------------
# The pre-ABS-249 driver copied setup-instantiated files into the consumer with
# their literal setup tokens intact; consumers then hand-substituted them.
#
# For the setup wizard that hand-fix was semantically INVERTED. The wizard holds
# the setup tokens as DATA (its REPLACEMENT_KEYS array), so a HEALTHY copy still
# contains them literally -- see is_substitutable(), which exempts the wizard for
# exactly this reason. An instantiated wizard is CORRUPT: future setup runs
# substitute the wrong strings, or nothing at all. And because the driver treats
# the wizard as non-substitutable, a corrupt copy also CONFLICTs on every future
# migration, forever -- "resolving" that by keeping the local file cements the
# corruption. That is the permanent fork-pressure this check exists to kill.
#
# Repair: the wizard is boilerplate-owned with no legitimate local drift, so the
# fix is simply "restore from upstream" -- we promote it CONFLICT -> REPLACE. A
# project that genuinely wants to fork it declares it in ownership.local.yaml;
# then it is an exception, never classified here, and we only report it.
#
# The other files the old driver wrote with literal tokens (promote-release.sh,
# sync-claude-harness.sh) are a LOWER-severity class: they ARE substitutable, so
# the consumer's hand-substitution was directionally correct and the only
# residual risk is INCOMPLETE substitution. Those are REPORTED, never auto-repaired.
# ============================================================================
WIZARD="scripts/setup-template.sh"
RESIDUE_CANDIDATES="scripts/promote-release.sh scripts/sync-claude-harness.sh"
INTEGRITY_ROWS=""          # "<verdict>|<path>|<action>" rows for the report
n_integrity=0

# Print the wizard's replacement-key array block (the tokens it holds as DATA).
wizard_key_block() { sed -n '/^declare -a REPLACEMENT_KEYS=(/,/^)/p' "$1"; }

# True if the target's wizard has been token-instantiated. The check is SCOPED TO
# THE KEY ARRAY, not the whole file: a hand-substitution instantiates only the
# array, so a CORRUPT wizard still carries "{{" hits outside it (the wizard's own
# grep patterns and {{PLACEHOLDER}} doc examples -- text no consumer sed can reach).
# A whole-file token check therefore grades a corrupt wizard as healthy, which is
# why this is scoped. Measured against the real file: 10 such non-array lines carry
# "{{", and the array holds 30 keys. $1 = target copy, $2 = source copy.
# Detection stays token-GENERIC: no literal replacement key may appear in THIS
# file (setup sweeps it -- see build_token_sed).
#
# Corruption is judged ENTRY-WISE, not "does the array still contain any token".
# Every healthy entry is a quoted "{{TOKEN}}" on its own line; the consumer's sed
# rewrites entries IN PLACE ("BUSCH"), so ANY non-token entry means corrupt. This
# matters because the consumer substitutes from their manifest token map, which
# covers only a SUBSET of the 30 keys -- so the realistic damage is PARTIAL (e.g.
# 26/30 keys still literal). An "array still has some {{" check grades exactly that
# case HEALTHY and misses the very corruption this exists to find.
wizard_is_instantiated() {
    local block entries tokens

    # No key array in the source (renamed/restructured upstream) -> cannot judge.
    wizard_key_block "$2" | LC_ALL=C grep -q '{{' || return 1

    block=$(wizard_key_block "$1")
    entries=$(printf '%s\n' "$block" | LC_ALL=C grep -c '^[[:space:]]*"' || true)
    tokens=$(printf '%s\n' "$block" | LC_ALL=C grep -c '^[[:space:]]*"{{[A-Z_]*}}"' || true)

    # No key array at all in the target: not the upstream wizard -> restore it.
    [ "${entries:-0}" -eq 0 ] && return 0
    # Any entry that is no longer token-shaped -> instantiated (full OR partial).
    [ "${tokens:-0}" -lt "${entries:-0}" ]
}

if [ -f "$SOURCE/$WIZARD" ] && [ -f "$TARGET/$WIZARD" ] \
   && wizard_is_instantiated "$TARGET/$WIZARD" "$SOURCE/$WIZARD"; then
    if printf '%s' "$CONFLICT_LIST" | grep -qx -- "$WIZARD"; then
        warn "integrity: $WIZARD is token-instantiated (CORRUPT -- its replacement keys are data). Restoring it from upstream."
        CONFLICT_LIST="$(printf '%s' "$CONFLICT_LIST" | grep -vx -- "$WIZARD" || true)"
        if [ -n "$CONFLICT_LIST" ]; then CONFLICT_LIST="$CONFLICT_LIST
"; fi
        n_conflict=$((n_conflict - 1))
        REPLACE_LIST="$REPLACE_LIST$WIZARD
"
        n_replace=$((n_replace + 1))
        INTEGRITY_ROWS="| 🔴 CORRUPT | $WIZARD | **Repaired**: restored verbatim from upstream (boilerplate-owned, no legitimate drift). |
"
    else
        # Declared a project_owned_exception (or not ownership-mapped): the local
        # copy is the project's to keep, so we report instead of overwriting.
        warn "integrity: $WIZARD is token-instantiated (CORRUPT) but excluded from the replace set -- reporting only."
        INTEGRITY_ROWS="| 🔴 CORRUPT | $WIZARD | **Repair by hand** (path is a project-owned exception): \`cp $SOURCE/$WIZARD $TARGET/$WIZARD\` |
"
    fi
    n_integrity=$((n_integrity + 1))
fi

# Residue: setup's substitution never completed in the adopted copy.
for rp in $RESIDUE_CANDIDATES; do
    [ -f "$TARGET/$rp" ] || continue
    if has_mapped_residue "$TARGET/$rp"; then
        warn "integrity: $rp still carries setup tokens the project's map instantiates (old-driver residue)"
        INTEGRITY_ROWS="$INTEGRITY_ROWS| 🟡 TOKEN RESIDUE | $rp | Take the **incoming** version if this file also appears under Conflicts — the local difference is old-driver token residue, not intentional drift. |
"
        n_integrity=$((n_integrity + 1))
    fi
done

[ "$n_integrity" -eq 0 ] || warn "integrity: $n_integrity finding(s) -- see the report"

# ============================================================================
# Step 5: Apply on a dedicated branch in the target
# ============================================================================
BRANCH="boilerplate-migration-${FROM}-to-${TO}"
git -C "$TARGET" checkout -b "$BRANCH" >/dev/null 2>&1 || git -C "$TARGET" checkout "$BRANCH" >/dev/null 2>&1
log "branch: $BRANCH"

copy_file() {
    # copy $SOURCE/$1 -> $TARGET/$1 (creating parent dirs), instantiating the
    # project's setup tokens on the way in -- the write path runs through the
    # SAME substitution pipeline as the hash comparison (ABS-249). cp first, so
    # the file mode (e.g. the +x on scripts/) is preserved.
    local rel="$1" dst="$TARGET/$1"
    mkdir -p "$(dirname "$dst")"
    cp "$SOURCE/$rel" "$dst"
    subst_in_place "$rel" "$dst"
}

# Replace an agentic ADR's content while PRESERVING the target's acceptance
# frontmatter (status/accepted_by/accepted_date are project-owned, ADR-A-0008).
copy_adr_preserving_frontmatter() {
    local rel="$1" srcf="$SOURCE/$1" dstf="$TARGET/$1"
    local st ab ad hab=0 had=0
    st="$(fm_field "$dstf" status)"
    if grep -qE '^accepted_by:' "$dstf"; then hab=1; ab="$(fm_field "$dstf" accepted_by)"; fi
    if grep -qE '^accepted_date:' "$dstf"; then had=1; ad="$(fm_field "$dstf" accepted_date)"; fi
    mkdir -p "$(dirname "$dstf")"
    awk -v st="$st" -v ab="${ab:-}" -v ad="${ad:-}" -v hab="$hab" -v had="$had" '
        NR==1 && $0=="---" { infm=1; print; next }
        infm && $0=="---" {
            print "status: " st
            if (hab=="1") print "accepted_by: " ab
            if (had=="1") print "accepted_date: " ad
            infm=0; print; next
        }
        infm && /^(status|accepted_by|accepted_date):/ { next }
        { print }
    ' "$srcf" > "$dstf"
    subst_in_place "$rel" "$dstf"   # same substitution pipeline as the hash compare (ABS-249)
}

# The harness migrates through the GENERIC path -- there is no `.claude` special
# case (ADR-A-0008 Amendment 2026-07-14, Q3, which records why the former
# DELEGATE_CLAUDE block was retired: dead, broken three ways, and made redundant
# by ABS-249). One engine, one semantics: the harness inherits the same drift
# rules as every other domain (REPLACE / ADD / CONFLICT-reported, never silently
# overwritten). sync-claude-harness.sh stays a standalone consumer tool.
apply_copy() {
    local p="$1"
    # Frontmatter-preserving copy only when the project already has the ADR
    # (a REPLACE); a brand-new ADR (ADD) is copied verbatim from source.
    if is_agentic_adr "$p" && [ -f "$TARGET/$p" ]; then
        copy_adr_preserving_frontmatter "$p"
    else
        copy_file "$p"
    fi
}

printf '%s' "$REPLACE_LIST" | while IFS= read -r p; do [ -n "$p" ] && apply_copy "$p"; done
printf '%s' "$ADD_LIST"     | while IFS= read -r p; do [ -n "$p" ] && apply_copy "$p"; done

# --- Declared migrations for the skipped versions (ABS-227 AC5) --------------
# Optional executable steps the new versions declare, run in FROM-exclusive..TO
# order. A failure aborts BEFORE the marker is stamped or anything committed.
MIG_DIR="$SOURCE/.agentic/upgrade/migrations"
RAN_MIGRATIONS=""
if [ -d "$MIG_DIR" ]; then
    for mig in $(ls "$MIG_DIR" 2>/dev/null | sort); do
        mv="${mig%.sh}"
        case "$mig" in *.sh) ;; *) continue ;; esac
        [ "$(vnum "$mv")" -gt "$(vnum "$FROM")" ] || continue
        [ "$(vnum "$mv")" -le "$(vnum "$TO")" ] || continue
        log "running declared migration: $mig"
        if ! ( cd "$TARGET" && TARGET_PROJECT_PATH="$TARGET" bash "$MIG_DIR/$mig" ); then
            abort "declared migration step FAILED: $mig (no marker stamped, nothing committed). Review and re-run." 7
        fi
        RAN_MIGRATIONS="$RAN_MIGRATIONS$mig
"
    done
fi

# --- Stamp the version marker (final applied change) -------------------------
printf '%s\n' "$TO" > "$TARGET/.boilerplate-version"

# ============================================================================
# Step 6: Migration report (with pre-computed diff -u conflict hunks, AC3)
# ============================================================================
REPORT_DIR="$TARGET/work/migration-reports"
mkdir -p "$REPORT_DIR"
TODAY="$(date +%Y-%m-%d)"
REPORT="$REPORT_DIR/${TODAY}-${FROM}-to-${TO}.md"

# --- Fork budget (ADR-A-0008 Amendment 2026-07-13, ABS-259) -------------------
# One verdict per project_owned_exceptions entry: every locally held fork of a
# boilerplate-owned file becomes visible, attributed to an upstream ticket, and
# aged. REPORT-ONLY: it never changes the exit code and never blocks a migration
# -- failing the upgrade over a stale fork would punish the consumer at exactly
# the moment they are getting back onto upstream.
FORK_MAX_AGE_DAYS="${MIGRATE_FORK_MAX_AGE_DAYS:-90}"
# A typo'd budget must not silently grade every fork JUSTIFIED (nor leak a raw
# `[: integer expression expected` from the comparison below).
case "$FORK_MAX_AGE_DAYS" in
    ''|*[!0-9]*) warn "MIGRATE_FORK_MAX_AGE_DAYS='$FORK_MAX_AGE_DAYS' is not a number -- using the 90-day default"
                 FORK_MAX_AGE_DAYS=90 ;;
esac

# De-fork check: does the target already hold, byte for byte, what the CURRENT
# source ships at this pathspec? Compared against the incoming <to> content (not
# the v<from> baseline) -- equality means upstream has converged on the project's
# version, so the fork is redundant and the exception line is deletable. This is
# the same comparison the classify loop makes for its "already current" class,
# applied to the paths it skips. Prints: same | differs | orphan.
exception_defork_state() {
    local pathspec="$1" f tgt_h src_h found=0
    for f in $(git -C "$SOURCE" ls-files -- "$pathspec" 2>/dev/null); do
        [ -f "$SOURCE/$f" ] || continue
        found=1
        [ -f "$TARGET/$f" ] || { echo "differs"; return 0; }
        if is_agentic_adr "$f"; then
            tgt_h="$(hash_adr_content_file "$TARGET/$f")"; src_h="$(hash_adr_content_file "$SOURCE/$f")"
        else
            tgt_h="$(hash_file "$TARGET/$f")"; src_h="$(hash_file "$SOURCE/$f")"
        fi
        [ "$tgt_h" = "$src_h" ] || { echo "differs"; return 0; }   # a directory needs EVERY file to match
    done
    if [ "$found" = "1" ]; then echo "same"; else echo "orphan"; fi
}

FORK_ROWS=""
while IFS="$(printf '\t')" read -r ex_path ex_kind ex_ref ex_since; do
    [ -n "$ex_path" ] || continue
    ex_age=""; age_disp="—"; ref_disp="—"

    if [ "$ex_kind" = "structural" ]; then
        # The designed override surface (base ADR-A-0008) -- informational, never red.
        verdict="⚪ STRUCTURAL"
    else
        [ "$ex_ref" = "-" ] || ref_disp="$ex_ref"
        if [ "$ex_since" != "-" ]; then
            ex_age="$(days_between "$ex_since" "$TODAY")"
            # Unparsable, or dated in the future: not a valid fork start -> the
            # entry is unattributed (an age of "-172 days" is a typo, not a budget).
            if [ "$ex_age" = "NA" ] || [ "$ex_age" -lt 0 ]; then ex_age=""; else age_disp="$ex_age"; fi
        fi
        ex_state="$(exception_defork_state "$ex_path")"

        if [ "$ex_state" = "same" ]; then
            verdict="✅ DE-FORK"                       # precedes the justification verdicts
        elif [ "$ex_state" = "orphan" ]; then
            verdict="⚠️ ORPHAN"
        elif [ "$ex_ref" = "-" ] || [ -z "$ex_age" ]; then
            verdict="🔴 UNJUSTIFIED"                   # incl. every legacy bare-path entry
        elif [ "$ex_age" -gt "$FORK_MAX_AGE_DAYS" ]; then
            verdict="🟡 STALE"
        else
            verdict="🟢 JUSTIFIED"
        fi
    fi
    FORK_ROWS="$FORK_ROWS| $verdict | $ex_path | $ex_kind | $ref_disp | $age_disp |
"
done <<EOF
$EXCEPTIONS_TABLE
EOF

{
    echo "# Boilerplate Migration Report"
    echo
    echo "- **Date**: $TODAY"
    echo "- **Versions**: $FROM -> $TO"
    echo "- **Branch**: $BRANCH"
    echo "- **Generated by**: scripts/migrate-project.sh (mechanical driver, ABS-227)"
    echo
    echo "## Files Changed"
    echo
    printf '%s' "$REPLACE_LIST" | while IFS= read -r p; do [ -n "$p" ] && echo "- $p — replaced"; done
    printf '%s' "$ADD_LIST"     | while IFS= read -r p; do [ -n "$p" ] && echo "- $p — added"; done
    [ "$n_replace" -eq 0 ] && [ "$n_add" -eq 0 ] && echo "- none"
    echo
    echo "## Breaking Changes (from HARNESS_CHANGELOG.yml, $FROM -> $TO)"
    echo
    if [ -f "$SCRIPT_DIR/changelog-slice.sh" ] && [ -f "$SOURCE/HARNESS_CHANGELOG.yml" ]; then
        bash "$SCRIPT_DIR/changelog-slice.sh" --since "$FROM" --to "$TO" --file "$SOURCE/HARNESS_CHANGELOG.yml" 2>/dev/null || echo "- (changelog slice unavailable)"
    else
        echo "- (no changelog in source checkout)"
    fi
    echo
    echo "## Conflicts Needing Human Decision"
    echo
    if [ "$n_conflict" -eq 0 ]; then
        echo "none"
    else
        echo "The following boilerplate-owned files were locally modified (drift). They were"
        echo "**NOT** overwritten. Each block shows \`diff -u <your version> <incoming version>\`."
        echo "The migration seat reads ONLY these hunks — never the full files."
        echo
        printf '%s' "$CONFLICT_LIST" | while IFS= read -r p; do
            [ -z "$p" ] && continue
            echo "### $p"
            echo
            echo '```diff'
            # Diff against the INSTANTIATED incoming file (ABS-249) -- otherwise every
            # hunk would also show {{TOKEN}} vs value noise on top of the real drift.
            inc="$SOURCE/$p"
            if is_substitutable "$p" && has_tokens "$inc"; then
                LC_ALL=C sed -f "$SED_CUR" "$SOURCE/$p" > "$TMP_DIR/incoming"
                inc="$TMP_DIR/incoming"
            fi
            diff -u "$TARGET/$p" "$inc" 2>/dev/null \
                | sed "s#$TMP_DIR/incoming#INCOMING/$p#g; s#$TARGET/#TARGET/#g; s#$SOURCE/#INCOMING/#g" || true
            echo '```'
            echo
        done
    fi
    echo "## Integrity Check (adopted copies, ABS-273)"
    echo
    if [ "$n_integrity" -eq 0 ]; then
        echo "✅ No token corruption found in the copies the pre-ABS-249 driver wrote with literal"
        echo "tokens:"
        echo
        for ip in "$WIZARD" $RESIDUE_CANDIDATES; do echo "- \`$ip\`"; done
    else
        echo "The migration driver before ABS-249 copied setup-instantiated files with their literal"
        echo "tokens; consumers hand-substituted them afterwards. For \`$WIZARD\` that hand-fix was"
        echo "**inverted** — the wizard stores those tokens as DATA (its replacement-key array), so a"
        echo "healthy copy still contains them literally. An instantiated wizard substitutes the wrong"
        echo "strings on the next setup run and conflicts on **every** future migration."
        echo
        echo "| Verdict | Path | Action |"
        echo "| --- | --- | --- |"
        printf '%s' "$INTEGRITY_ROWS"
        echo
        echo "- 🔴 **CORRUPT** — the wizard was token-instantiated. It is boilerplate-owned with no"
        echo "  legitimate local drift, so the repair is a restore from upstream."
        echo "- 🟡 **TOKEN RESIDUE** — an adopted copy still carries setup tokens your project's map"
        echo "  instantiates: the hand-substitution was incomplete. Lower severity than the wizard —"
        echo "  the semantics were right, only the coverage was short."
        echo
        echo "Verify by hand at any time (no migration needed) — this is the driver's own ENTRY-WISE"
        echo "predicate: count the key array's entries that are still token-SHAPED, and compare against"
        echo "ALL its entries. Counting \`{{\` hits instead reports a corrupt wizard as healthy, because"
        echo "your substitution covered only a SUBSET of the keys, so the damage is usually PARTIAL"
        echo "(see SOP §3.1.2). Use exactly this:"
        echo
        echo '```bash'
        echo "BLOCK=\$(sed -n '/^declare -a REPLACEMENT_KEYS=(/,/^)/p' $WIZARD)"
        echo "ENTRIES=\$(printf '%s\n' \"\$BLOCK\" | grep -c '^[[:space:]]*\"')"
        echo "TOKENS=\$(printf '%s\n' \"\$BLOCK\" | grep -c '^[[:space:]]*\"{{[A-Z_]*}}\"')"
        echo "echo \"\$TOKENS/\$ENTRIES replacement keys still literal\""
        echo "# healthy: TOKENS == ENTRIES"
        echo "# corrupt: any shortfall — 0/30 (fully substituted) or e.g. 26/30 (partially)"
        echo '```'
    fi
    echo
    echo "## Fork Budget (project_owned_exceptions)"
    echo
    if [ -z "$FORK_ROWS" ]; then
        echo "No project-owned exceptions declared — nothing forked, nothing to pay back."
    else
        echo "Every locally held fork of a boilerplate-owned file, with its upstream ticket and age."
        echo "**Report-only**: the fork budget never blocks a migration (ADR-A-0008 Amendment 2026-07-13)."
        echo "Budget: **${FORK_MAX_AGE_DAYS} days** (override with \`MIGRATE_FORK_MAX_AGE_DAYS\`)."
        echo
        echo "| Verdict | Path | Kind | upstream_ref | Age (days) |"
        echo "| --- | --- | --- | --- | --- |"
        printf '%s' "$FORK_ROWS"
        echo
        echo "- ✅ **DE-FORK** — upstream now ships exactly your content: **delete the exception entry**."
        echo "- 🔴 **UNJUSTIFIED** — a fork with no \`upstream_ref\`/\`since\`: file the upstream ticket or drop the fork."
        echo "- 🟡 **STALE** — justified fork past the budget: chase the upstream ticket, or accept the fork permanently."
        echo "- 🟢 **JUSTIFIED** — forked, filed, in budget."
        echo "- ⚪ **STRUCTURAL** — the designed override surface: project-owned by design, never red."
        echo "- ⚠️ **ORPHAN** — upstream ships no file at this path: the exception is moot."
    fi
    echo
    echo "## Manual Follow-Ups"
    echo
    echo "- Review each conflict above; keep the local change as an \`overrides/\` entry or drop it and file an upstream feature request."
    echo "- Run the project's own test suite before merging."
    echo "- Open a PR and merge — **merging is human-only** (ADR-A-0005)."
    if [ -n "$RAN_MIGRATIONS" ]; then
        echo "- Declared migrations executed:"
        printf '%s' "$RAN_MIGRATIONS" | while IFS= read -r m; do [ -n "$m" ] && echo "  - $m"; done
    fi
    if [ -n "$MISSING_SRC_LIST" ]; then
        echo "- Ownership-mapped paths with no file in the current boilerplate source (left untouched in the target — no silent removal; likely removed upstream, confirm intent):"
        printf '%s' "$MISSING_SRC_LIST" | while IFS= read -r m; do [ -n "$m" ] && echo "  - $m"; done
    fi
} > "$REPORT"

log "report: $REPORT"

# ============================================================================
# Step 7: Commit (branch is the deliverable; NO merge, NO push -- ADR-A-0005)
# ============================================================================
if [ "$DO_COMMIT" = "true" ]; then
    git -C "$TARGET" add -A
    # Keep the tolerated off-surface untracked files OUT of the migration commit
    # (ABS-277): `add -A` stages them, so unstage exactly those paths again. The
    # migration commit stays an isolated, reviewable boilerplate-only diff.
    # One batched reset, not one per path: -uall can list a whole untracked build
    # directory. The [ ${#unstage[@]} -gt 0 ] guard is load-bearing -- a bare
    # `git reset -q --` carries NO pathspec and would unstage the entire migration.
    unstage=()
    while IFS= read -r u; do
        [ -n "$u" ] || continue
        unstage[${#unstage[@]}]="$u"
    done < "$PRESERVED_UNTRACKED"
    if [ ${#unstage[@]} -gt 0 ]; then
        git -C "$TARGET" reset -q -- "${unstage[@]}" 2>/dev/null || true
    fi
    git -C "$TARGET" commit -q -m "chore(boilerplate): migrate boilerplate $FROM -> $TO" \
        --author="boilerplate-migration <noreply@boilerplate>" 2>/dev/null \
        || git -C "$TARGET" commit -q -m "chore(boilerplate): migrate boilerplate $FROM -> $TO"
    ok "committed on $BRANCH (not merged, not pushed)"
fi

# ============================================================================
# Machine-readable summary on stdout (the ONLY thing on stdout)
# ============================================================================
if [ "$FORMAT" = "json" ]; then
    printf '{"status":"migrated","from":"%s","to":"%s","branch":"%s","replaced":%d,"added":%d,"conflicts":%d,"already_current":%d,"report":"%s"}\n' \
        "$FROM" "$TO" "$BRANCH" "$n_replace" "$n_add" "$n_conflict" "$n_skip" "${REPORT#$TARGET/}"
else
    echo "STATUS migrated from=$FROM to=$TO branch=$BRANCH"
    echo "| metric | count |"
    echo "| --- | --- |"
    echo "| replaced | $n_replace |"
    echo "| added | $n_add |"
    echo "| conflicts | $n_conflict |"
    echo "| already_current | $n_skip |"
    echo "REPORT ${REPORT#$TARGET/}"
fi
