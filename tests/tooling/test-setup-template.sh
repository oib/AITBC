#!/bin/bash
# =============================================================================
# Test: Bootstrap Wizard (scripts/setup-template.sh) [ABS-31, ABS-35]
# =============================================================================
# Regression + conformance test for the template setup wizard (bootstrap v2).
#
# Covers:
#   - placeholder replacement, incl. sed-hostile chars ("|", "&")   [ABS-31]
#   - DB_PASSWORD written to .env only, never to tracked files      [ABS-31]
#   - dependency preflight banner never aborts the run              [ABS-31]
#   - non-interactive full run via --values                        [ABS-47]
#   - missing required keys => non-zero exit listing the keys       [ABS-47]
#   - manifest + .active-profile generation                        [ABS-48]
#   - gap report: neutral (ready) and fake profile (NOT ready)     [ABS-49]
#   - run-twice idempotency ("nothing to replace")                 [ABS-50]
#   - --finalize deletes the wizard + TEMPLATE_SETUP.md            [ABS-50]
#
# Run from repo root: bash tests/tooling/test-setup-template.sh
#
# All fixtures copy the wizard INTO a temp tree and run the COPY -- never the
# repo's own scripts/setup-template.sh.
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WIZARD_SRC="$REPO_ROOT/scripts/setup-template.sh"
NEUTRAL_PROFILE_SRC="$REPO_ROOT/profiles/neutral/profile.yaml"

TEST_DIR=$(mktemp -d /tmp/setup-template-test-XXXXXX)
trap "rm -rf $TEST_DIR" EXIT

PASS=0
FAIL=0
TOTAL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

assert_contains() {
    local output="$1"; local expected="$2"; local label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output (first 30 lines):${NC}"
        echo "$output" | head -30 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1"; local expected="$2"; local label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect to find: $expected)"
        FAIL=$((FAIL + 1))
    fi
}

assert_exit_code() {
    local actual="$1"; local expected="$2"; local label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -eq "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

assert_exit_nonzero() {
    local actual="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -ne 0 ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected non-zero, got 0)"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_exists() {
    local path="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ -f "$path" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (file not found: $path)"; FAIL=$((FAIL + 1))
    fi
}

assert_file_absent() {
    local path="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ ! -f "$path" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (file should be absent: $path)"; FAIL=$((FAIL + 1))
    fi
}

assert_file_contains() {
    local file="$1"; local expected="$2"; local label="$3"
    TOTAL=$((TOTAL + 1))
    if [ -f "$file" ] && grep -qF -- "$expected" "$file"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected file to contain: $expected)"
        if [ -f "$file" ]; then
            echo -e "  ${YELLOW}  File contents (first 20 lines):${NC}"
            head -20 "$file" | sed 's/^/    /'
        else
            echo -e "  ${YELLOW}  File does not exist: $file${NC}"
        fi
        FAIL=$((FAIL + 1))
    fi
}

assert_file_not_contains() {
    local file="$1"; local expected="$2"; local label="$3"
    TOTAL=$((TOTAL + 1))
    if [ -f "$file" ] && ! grep -qF -- "$expected" "$file"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect file to contain: $expected)"
        FAIL=$((FAIL + 1))
    fi
}

# -----------------------------------------------------------------------------
# Build a fixture project tree with the wizard + neutral profile inside it.
# Args: $1 = fixture dir path
# -----------------------------------------------------------------------------
make_fixture() {
    local fx="$1"
    mkdir -p "$fx/scripts" "$fx/docs" "$fx/profiles/neutral"
    cp "$WIZARD_SRC" "$fx/scripts/setup-template.sh"
    chmod +x "$fx/scripts/setup-template.sh"
    cp "$NEUTRAL_PROFILE_SRC" "$fx/profiles/neutral/profile.yaml"
    if [ -f "$REPO_ROOT/.harness-manifest.schema.json" ]; then
        cp "$REPO_ROOT/.harness-manifest.schema.json" "$fx/.harness-manifest.schema.json"
    fi

    echo "# AITBC template setup" > "$fx/TEMPLATE_SETUP.md"

    cat > "$fx/.gitignore" <<'EOF'
.env
.env.local
node_modules/
EOF

    cat > "$fx/.env.template" <<'EOF'
# Environment template
PROJECT_NAME="YourProjectName"
TICKET_PREFIX="PROJ"
EOF

    cat > "$fx/README.md" <<'EOF'
# AITBC

Repo: AITBC
Short: AITBC
Org: oib
Company: AITBC
Ticket prefix: AITBC
Main branch: main
DB user: aitbc
DB password: {{DB_PASSWORD}}
Registry: ghcr.io/oib
EOF

    cat > "$fx/docs/CONFIG.yml" <<'EOF'
project: AITBC
db_password: {{DB_PASSWORD}}
registry: ghcr.io/oib
EOF
}

# A --values file exercising sed-hostile "|" and "&" characters.
write_values_file() {
    cat > "$1" <<'EOF'
PROJECT_NAME=TestProject
PROJECT_REPO=test-project
PROJECT_SHORT=TSTP
PROJECT_DOMAIN=testproject.example.com
GITHUB_ORG=test-org
COMPANY_NAME=Acme & Sons | Partners
AUTHOR_NAME=Jane Smith
AUTHOR_FIRST_NAME=Jane
AUTHOR_LAST_NAME=Smith
AUTHOR_HANDLE=janesmith
AUTHOR_EMAIL=jane@example.com
AUTHOR_WEBSITE=https://janesmith.dev
SECURITY_EMAIL=security@example.com
ARCHITECT_GITHUB_HANDLE=lead-dev
TICKET_PREFIX=TSTP
LINEAR_WORKSPACE=test-workspace
MAIN_BRANCH=main
MCP_LINEAR_SERVER=linear-mcp
MCP_CONFLUENCE_SERVER=confluence-mcp
DB_USER=app_user
DB_PASSWORD=S3cr3t|Pass&Word
DB_NAME=app_dev
DB_CONTAINER=app-postgres
DEV_CONTAINER=app-dev
STAGING_CONTAINER=app-staging
CONTAINER_REGISTRY=ghcr.io/test-org & co
EOF
}

# =============================================================================
echo -e "\n${CYAN}=== Test 0: Script syntax ===${NC}\n"
# =============================================================================
syntax_output=$(bash -n "$WIZARD_SRC" 2>&1)
assert_exit_code $? 0 "setup-template.sh has valid bash syntax"

# =============================================================================
echo -e "\n${CYAN}=== Fixture setup (non-interactive via --values) ===${NC}\n"
# =============================================================================
FIXTURE="$TEST_DIR/fixture-project"
make_fixture "$FIXTURE"
write_values_file "$FIXTURE/bootstrap.values"

set +e
run_output=$(cd "$FIXTURE" && bash "$FIXTURE/scripts/setup-template.sh" \
    --values "$FIXTURE/bootstrap.values" --yes 2>&1)
run_exit=$?
set -e

# =============================================================================
echo -e "\n${CYAN}=== Test 1: Non-interactive --values run replaces placeholders, exits 0 [ABS-47] ===${NC}\n"
# =============================================================================
assert_exit_code "$run_exit" 0 "wizard exits 0 on a full non-interactive --values run"

assert_file_contains "$FIXTURE/README.md" "# TestProject" "PROJECT_NAME replaced in README.md"
assert_file_contains "$FIXTURE/README.md" "Repo: test-project" "PROJECT_REPO replaced"
assert_file_contains "$FIXTURE/README.md" "Short: TSTP" "PROJECT_SHORT replaced"
assert_file_contains "$FIXTURE/README.md" "Org: test-org" "GITHUB_ORG replaced"
assert_file_contains "$FIXTURE/README.md" "Ticket prefix: TSTP" "TICKET_PREFIX replaced"
assert_file_contains "$FIXTURE/README.md" "Main branch: main" "MAIN_BRANCH replaced"
assert_file_contains "$FIXTURE/README.md" "DB user: app_user" "DB_USER replaced"

assert_file_contains "$FIXTURE/README.md" "Company: Acme & Sons | Partners" \
    "COMPANY_NAME containing '|' and '&' substituted correctly"
assert_file_contains "$FIXTURE/README.md" "Registry: ghcr.io/test-org & co" \
    "CONTAINER_REGISTRY containing '&' substituted correctly"
assert_file_contains "$FIXTURE/docs/CONFIG.yml" "project: TestProject" \
    "placeholder replaced in nested docs/CONFIG.yml"
assert_file_contains "$FIXTURE/docs/CONFIG.yml" "registry: ghcr.io/test-org & co" \
    "CONTAINER_REGISTRY with '&' substituted correctly in a second file"

for token in "AITBC" "AITBC" "AITBC" \
             "oib" "AITBC" "AITBC" \
             "main" "aitbc" "ghcr.io/oib"; do
    assert_file_not_contains "$FIXTURE/README.md" "$token" "no remnant of $token in README.md"
done

# =============================================================================
echo -e "\n${CYAN}=== Test 2: Secrets handling -- DB_PASSWORD never in tracked files [ABS-31] ===${NC}\n"
# =============================================================================
assert_file_not_contains "$FIXTURE/README.md" "S3cr3t|Pass&Word" \
    "DB_PASSWORD value absent from README.md"
assert_file_not_contains "$FIXTURE/docs/CONFIG.yml" "S3cr3t|Pass&Word" \
    "DB_PASSWORD value absent from docs/CONFIG.yml"

assert_file_exists "$FIXTURE/.env" ".env created from .env.template"
assert_file_contains "$FIXTURE/.env" 'DB_PASSWORD="S3cr3t|Pass&Word"' \
    "DB_PASSWORD written to .env with correct value"
assert_file_contains "$FIXTURE/.env" 'PROJECT_NAME="YourProjectName"' \
    ".env retains other content copied from .env.template"
assert_file_contains "$FIXTURE/.gitignore" ".env" ".gitignore still ignores .env after run"

# =============================================================================
echo -e "\n${CYAN}=== Test 3: Dependency preflight banner printed, run continues [ABS-31] ===${NC}\n"
# =============================================================================
assert_contains "$run_output" "Bash version:" "wizard reports bash version"
assert_contains "$run_output" "Setup complete!" "wizard reaches completion banner"

# =============================================================================
echo -e "\n${CYAN}=== Test 4: Manifest + .active-profile generated [ABS-48] ===${NC}\n"
# =============================================================================
assert_file_exists "$FIXTURE/.harness-manifest.yml" ".harness-manifest.yml generated"
assert_file_contains "$FIXTURE/.harness-manifest.yml" 'manifest_version: "1.1"' \
    "manifest declares schema version 1.1"
assert_file_contains "$FIXTURE/.harness-manifest.yml" 'PROJECT_NAME: "TestProject"' \
    "manifest identity carries PROJECT_NAME"
assert_file_contains "$FIXTURE/.harness-manifest.yml" 'TICKET_PREFIX: "TSTP"' \
    "manifest identity carries TICKET_PREFIX"
assert_file_contains "$FIXTURE/.harness-manifest.yml" 'MAIN_BRANCH: "main"' \
    "manifest identity carries MAIN_BRANCH"

assert_file_exists "$FIXTURE/.active-profile" ".active-profile written"
TOTAL=$((TOTAL + 1))
if [ "$(cat "$FIXTURE/.active-profile")" = "neutral" ]; then
    echo -e "  ${GREEN}PASS${NC} .active-profile contains 'neutral' (default)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} .active-profile should contain 'neutral'"; FAIL=$((FAIL + 1))
fi

# --- Schema-validate the generated manifest against .harness-manifest.schema.json ---
# Prefer python3 + jsonschema when importable; otherwise fall back to a plain
# assertion of required-field presence and absence of empty-string identity
# values (the concrete regression this guards against: SHOULD 1 above).
if command -v python3 &>/dev/null && python3 -c "import jsonschema, yaml" &>/dev/null \
        && [ -f "$FIXTURE/.harness-manifest.schema.json" ]; then
    schema_validate_output=$(python3 - "$FIXTURE/.harness-manifest.yml" "$FIXTURE/.harness-manifest.schema.json" <<'PYEOF' 2>&1
import sys
import json
import yaml
import jsonschema

manifest_path, schema_path = sys.argv[1], sys.argv[2]
with open(manifest_path) as f:
    manifest = yaml.safe_load(f)
with open(schema_path) as f:
    schema = json.load(f)

validator_cls = jsonschema.validators.validator_for(schema)
validator_cls.check_schema(schema)
validator = validator_cls(schema, format_checker=jsonschema.FormatChecker())
errors = sorted(validator.iter_errors(manifest), key=lambda e: e.path)
if errors:
    for e in errors:
        print(f"SCHEMA ERROR: {list(e.path)}: {e.message}")
    sys.exit(1)
print("SCHEMA OK")
sys.exit(0)
PYEOF
)
    schema_validate_exit=$?
    TOTAL=$((TOTAL + 1))
    if [ "$schema_validate_exit" -eq 0 ]; then
        echo -e "  ${GREEN}PASS${NC} generated manifest passes jsonschema validation"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} generated manifest fails jsonschema validation"
        echo "$schema_validate_output" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
else
    echo "  (jsonschema not importable or schema file missing -- falling back to plain assertions)"
    assert_file_contains "$FIXTURE/.harness-manifest.yml" 'PROJECT_SHORT: "TSTP"' \
        "manifest identity carries required field PROJECT_SHORT (schema fallback)"
    assert_file_contains "$FIXTURE/.harness-manifest.yml" 'GITHUB_ORG: "test-org"' \
        "manifest identity carries required field GITHUB_ORG (schema fallback)"
    TOTAL=$((TOTAL + 1))
    if ! grep -qE ': ""$' "$FIXTURE/.harness-manifest.yml"; then
        echo -e "  ${GREEN}PASS${NC} manifest has no empty-string identity values (schema fallback)"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} manifest contains an empty-string identity value (schema fallback)"
        FAIL=$((FAIL + 1))
    fi
fi

# =============================================================================
echo -e "\n${CYAN}=== Test 5: Gap report for neutral profile => ready [ABS-49] ===${NC}\n"
# =============================================================================
assert_file_exists "$FIXTURE/bootstrap-gap-report.md" "gap report generated"
assert_file_contains "$FIXTURE/bootstrap-gap-report.md" "ready for agentic execution" \
    "neutral profile is ready for agentic execution"
assert_file_not_contains "$FIXTURE/bootstrap-gap-report.md" "NOT ready" \
    "neutral profile gap report is not marked NOT ready"
assert_file_contains "$FIXTURE/bootstrap-gap-report.md" "task-tracking" \
    "gap report lists task-tracking capability"
assert_contains "$run_output" "ready for agentic execution" \
    "wizard prints readiness verdict"

# =============================================================================
echo -e "\n${CYAN}=== Test 6: --finalize deletes wizard + TEMPLATE_SETUP.md [ABS-50] ===${NC}\n"
# =============================================================================
# Default (non-finalize) run above must NOT have deleted anything.
assert_file_exists "$FIXTURE/scripts/setup-template.sh" \
    "wizard is NOT self-deleted on a default run (idempotency-safe)"
assert_file_exists "$FIXTURE/TEMPLATE_SETUP.md" \
    "TEMPLATE_SETUP.md is NOT removed on a default run"

# Now run with --finalize and assert cleanup happens.
set +e
finalize_output=$(cd "$FIXTURE" && bash "$FIXTURE/scripts/setup-template.sh" \
    --values "$FIXTURE/bootstrap.values" --yes --finalize 2>&1)
finalize_exit=$?
set -e
assert_exit_code "$finalize_exit" 0 "--finalize run exits 0"
assert_file_absent "$FIXTURE/scripts/setup-template.sh" \
    "--finalize deletes the wizard copy"
assert_file_absent "$FIXTURE/TEMPLATE_SETUP.md" \
    "--finalize removes TEMPLATE_SETUP.md"
assert_file_exists "$WIZARD_SRC" "repo's real scripts/setup-template.sh is untouched"

# =============================================================================
echo -e "\n${CYAN}=== Test 7: Missing required keys => non-zero, lists keys [ABS-47] ===${NC}\n"
# =============================================================================
FIXTURE_MISS="$TEST_DIR/fixture-missing"
make_fixture "$FIXTURE_MISS"
cat > "$FIXTURE_MISS/only-name.values" <<'EOF'
PROJECT_NAME=OnlyName
EOF

set +e
miss_output=$(cd "$FIXTURE_MISS" && bash "$FIXTURE_MISS/scripts/setup-template.sh" \
    --values "$FIXTURE_MISS/only-name.values" --yes 2>&1)
miss_exit=$?
set -e
assert_exit_nonzero "$miss_exit" "wizard exits non-zero when required keys are missing"
assert_contains "$miss_output" "missing required values" "wizard reports missing required values"
assert_contains "$miss_output" "PROJECT_REPO" "missing-key list names PROJECT_REPO"
assert_contains "$miss_output" "PROJECT_SHORT" "missing-key list names PROJECT_SHORT"
assert_contains "$miss_output" "GITHUB_ORG" "missing-key list names GITHUB_ORG"
assert_contains "$miss_output" "TICKET_PREFIX" "missing-key list names TICKET_PREFIX"
# No replacement should have happened.
assert_file_contains "$FIXTURE_MISS/README.md" "AITBC" \
    "no replacement applied when required keys missing"

# =============================================================================
echo -e "\n${CYAN}=== Test 8: Gap report NOT ready + non-zero for a bad profile [ABS-49] ===${NC}\n"
# =============================================================================
FIXTURE_BAD="$TEST_DIR/fixture-bad-profile"
make_fixture "$FIXTURE_BAD"
write_values_file "$FIXTURE_BAD/bootstrap.values"
# A fake profile where a REQUIRED capability (task-tracking) has provider none.
mkdir -p "$FIXTURE_BAD/profiles/broken"
cat > "$FIXTURE_BAD/profiles/broken/profile.yaml" <<'EOF'
profile: broken
capabilities:
  task-tracking:
    provider: none
    required: true
  docs:
    provider: mock
    required: true
  git:
    provider: github
    required: true
  notifications:
    provider: task-tracking
    required: true
EOF

set +e
bad_output=$(cd "$FIXTURE_BAD" && bash "$FIXTURE_BAD/scripts/setup-template.sh" \
    --values "$FIXTURE_BAD/bootstrap.values" --yes --profile broken 2>&1)
bad_exit=$?
set -e
assert_exit_nonzero "$bad_exit" "wizard exits non-zero on a NOT-ready profile (no --allow-gaps)"
assert_file_contains "$FIXTURE_BAD/bootstrap-gap-report.md" "NOT ready for agentic execution" \
    "gap report marks the broken profile NOT ready"
assert_file_contains "$FIXTURE_BAD/bootstrap-gap-report.md" "task-tracking" \
    "gap report names the blocking task-tracking capability"

# Same profile with --allow-gaps must succeed.
set +e
allow_output=$(cd "$FIXTURE_BAD" && bash "$FIXTURE_BAD/scripts/setup-template.sh" \
    --values "$FIXTURE_BAD/bootstrap.values" --yes --profile broken --allow-gaps 2>&1)
allow_exit=$?
set -e
assert_exit_code "$allow_exit" 0 "--allow-gaps lets a NOT-ready profile complete (exit 0)"

# =============================================================================
echo -e "\n${CYAN}=== Test 9: Run-twice idempotency [ABS-50] ===${NC}\n"
# =============================================================================
FIXTURE_IDEM="$TEST_DIR/fixture-idempotent"
make_fixture "$FIXTURE_IDEM"
write_values_file "$FIXTURE_IDEM/bootstrap.values"

set +e
idem1=$(cd "$FIXTURE_IDEM" && bash "$FIXTURE_IDEM/scripts/setup-template.sh" \
    --values "$FIXTURE_IDEM/bootstrap.values" --yes 2>&1)
idem1_exit=$?
idem2=$(cd "$FIXTURE_IDEM" && bash "$FIXTURE_IDEM/scripts/setup-template.sh" \
    --values "$FIXTURE_IDEM/bootstrap.values" --yes 2>&1)
idem2_exit=$?
set -e
assert_exit_code "$idem1_exit" 0 "first run exits 0"
assert_exit_code "$idem2_exit" 0 "second (idempotent) run exits 0"
assert_contains "$idem1" "Replacing 'AITBC'" "first run performs replacement"
assert_contains "$idem2" "Nothing to replace" "second run detects nothing to replace"
assert_file_contains "$FIXTURE_IDEM/README.md" "# TestProject" \
    "README stays correctly substituted after two runs"
# The wizard copy must survive both runs (no self-delete without --finalize).
assert_file_exists "$FIXTURE_IDEM/scripts/setup-template.sh" \
    "wizard copy survives two runs (no default self-delete)"

# =============================================================================
echo -e "\n${CYAN}=== Test 10: Non-TTY missing --yes on a bad-profile guard [ABS-47] ===${NC}\n"
# =============================================================================
# Non-interactive without --yes must not hang; it exits non-zero asking for --yes.
FIXTURE_NOYES="$TEST_DIR/fixture-noyes"
make_fixture "$FIXTURE_NOYES"
write_values_file "$FIXTURE_NOYES/bootstrap.values"
set +e
noyes_output=$(cd "$FIXTURE_NOYES" && bash "$FIXTURE_NOYES/scripts/setup-template.sh" \
    --values "$FIXTURE_NOYES/bootstrap.values" </dev/null 2>&1)
noyes_exit=$?
set -e
assert_exit_nonzero "$noyes_exit" "non-interactive run without --yes exits non-zero (no hang)"
assert_contains "$noyes_output" "pass --yes" "wizard advises passing --yes in non-interactive mode"

# =============================================================================
echo -e "\n${CYAN}=== Test 11: Gap report provider parsing scoped to its own capability block [ABS-35] ===${NC}\n"
# =============================================================================
# Regression for the _cap_provider MUST-FIX: a required capability with NO
# provider line within 6 lines of its header (the old grep -A6 window), with
# the NEXT capability declaring a provider right after. The old
# `grep -A6 ... | grep provider: | head -1` bled into the next capability's
# block and misreported the gap as ready; the fix scopes strictly to the
# current capability's own lines (up to the next same-indent key).
FIXTURE_SCOPE="$TEST_DIR/fixture-scope-provider"
make_fixture "$FIXTURE_SCOPE"
write_values_file "$FIXTURE_SCOPE/bootstrap.values"
mkdir -p "$FIXTURE_SCOPE/profiles/scoped"
cat > "$FIXTURE_SCOPE/profiles/scoped/profile.yaml" <<'EOF'
profile: scoped
capabilities:
  task-tracking:
    interface: adapters/task-tracking.md
    implemented_by:
      agents: [tdm]
      commands: [start-work, end-work]
      skills: [safe-workflow]
    required: true
  docs:
    interface: adapters/docs.md
    provider: mock
    implemented_by:
      agents: [tech-writer]
    required: true
  git:
    interface: adapters/git.md
    provider: github
    required: true
  notifications:
    interface: adapters/notifications.md
    provider: task-tracking
    required: true
EOF

set +e
scope_output=$(cd "$FIXTURE_SCOPE" && bash "$FIXTURE_SCOPE/scripts/setup-template.sh" \
    --values "$FIXTURE_SCOPE/bootstrap.values" --yes --profile scoped 2>&1)
scope_exit=$?
set -e
assert_exit_nonzero "$scope_exit" "wizard exits non-zero when a required capability's provider is beyond its own block"
assert_file_contains "$FIXTURE_SCOPE/bootstrap-gap-report.md" "| task-tracking | unset | MISSING |" \
    "gap report marks task-tracking MISSING, not masked by docs' provider"
assert_file_contains "$FIXTURE_SCOPE/bootstrap-gap-report.md" "NOT ready for agentic execution" \
    "gap report verdict is NOT ready (not falsely 'ready')"
assert_file_not_contains "$FIXTURE_SCOPE/bootstrap-gap-report.md" "| task-tracking | mock |" \
    "task-tracking provider is not misreported as docs' 'mock' value"

# =============================================================================
echo -e "\n${CYAN}=== Test 12: Optional identity fields omitted from manifest when empty [ABS-35] ===${NC}\n"
# =============================================================================
# A --values file that leaves every OPTIONAL identity field blank/absent.
# The manifest heredoc must omit those keys entirely (not emit `KEY: ""`),
# since format: email/uri under a strict FormatChecker rejects empty strings.
FIXTURE_EMPTY="$TEST_DIR/fixture-empty-identity"
make_fixture "$FIXTURE_EMPTY"
cat > "$FIXTURE_EMPTY/bootstrap.values" <<'EOF'
PROJECT_NAME=MinimalProject
PROJECT_REPO=minimal-project
PROJECT_SHORT=MINP
GITHUB_ORG=minimal-org
TICKET_PREFIX=MINP
MAIN_BRANCH=main
EOF

set +e
empty_output=$(cd "$FIXTURE_EMPTY" && bash "$FIXTURE_EMPTY/scripts/setup-template.sh" \
    --values "$FIXTURE_EMPTY/bootstrap.values" --yes --allow-gaps 2>&1)
empty_exit=$?
set -e
assert_exit_code "$empty_exit" 0 "run with only required identity fields succeeds"
assert_file_contains "$FIXTURE_EMPTY/.harness-manifest.yml" 'PROJECT_NAME: "MinimalProject"' \
    "manifest still carries required PROJECT_NAME"
assert_file_not_contains "$FIXTURE_EMPTY/.harness-manifest.yml" 'SECURITY_EMAIL: ""' \
    "manifest omits empty-string SECURITY_EMAIL rather than emitting it"
assert_file_not_contains "$FIXTURE_EMPTY/.harness-manifest.yml" 'AUTHOR_EMAIL: ""' \
    "manifest omits empty-string AUTHOR_EMAIL rather than emitting it"
assert_file_not_contains "$FIXTURE_EMPTY/.harness-manifest.yml" 'AUTHOR_WEBSITE: ""' \
    "manifest omits empty-string AUTHOR_WEBSITE rather than emitting it"
TOTAL=$((TOTAL + 1))
if ! grep -qE ': ""$' "$FIXTURE_EMPTY/.harness-manifest.yml"; then
    echo -e "  ${GREEN}PASS${NC} manifest has no empty-string values anywhere in identity block"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} manifest still contains an empty-string identity value"
    grep -E ': ""$' "$FIXTURE_EMPTY/.harness-manifest.yml" | sed 's/^/    /'
    FAIL=$((FAIL + 1))
fi

# =============================================================================
echo -e "\n${CYAN}=== Test 13: TICKET_PREFIX upper-cased and validated against schema pattern [ABS-35] ===${NC}\n"
# =============================================================================
# Lowercase input is upper-cased automatically; non-conforming values hard-fail
# in non-interactive mode (schema: ^[A-Z][A-Z0-9]{1,9}$).
FIXTURE_TP="$TEST_DIR/fixture-ticket-prefix"
make_fixture "$FIXTURE_TP"
cat > "$FIXTURE_TP/bootstrap.values" <<'EOF'
PROJECT_NAME=CaseProject
PROJECT_REPO=case-project
PROJECT_SHORT=CASE
GITHUB_ORG=case-org
TICKET_PREFIX=abc
MAIN_BRANCH=main
EOF
set +e
tp_lower_output=$(cd "$FIXTURE_TP" && bash "$FIXTURE_TP/scripts/setup-template.sh" \
    --values "$FIXTURE_TP/bootstrap.values" --yes --allow-gaps 2>&1)
tp_lower_exit=$?
set -e
assert_exit_code "$tp_lower_exit" 0 "lowercase TICKET_PREFIX run succeeds"
assert_file_contains "$FIXTURE_TP/.harness-manifest.yml" 'TICKET_PREFIX: "ABC"' \
    "lowercase TICKET_PREFIX is upper-cased in the manifest"

FIXTURE_TP_BAD="$TEST_DIR/fixture-ticket-prefix-bad"
make_fixture "$FIXTURE_TP_BAD"
cat > "$FIXTURE_TP_BAD/bootstrap.values" <<'EOF'
PROJECT_NAME=BadProject
PROJECT_REPO=bad-project
PROJECT_SHORT=BADP
GITHUB_ORG=bad-org
TICKET_PREFIX=1
MAIN_BRANCH=main
EOF
set +e
tp_bad_output=$(cd "$FIXTURE_TP_BAD" && bash "$FIXTURE_TP_BAD/scripts/setup-template.sh" \
    --values "$FIXTURE_TP_BAD/bootstrap.values" --yes --allow-gaps 2>&1)
tp_bad_exit=$?
set -e
assert_exit_nonzero "$tp_bad_exit" "non-conforming TICKET_PREFIX hard-fails in non-interactive mode"
assert_contains "$tp_bad_output" "TICKET_PREFIX" "error message names TICKET_PREFIX"

# =============================================================================
echo -e "\n${CYAN}=== Test 14: Directory excludes -- node_modules/dist never traversed [ABS-179] ===${NC}\n"
# =============================================================================
# The shared exclude list (.git node_modules dist build .next vendor worktrees
# tmp) must apply to ALL sweeps. Placeholder files planted inside an excluded
# directory must NOT be substituted and must NOT surface in the REMAINING
# report -- proving those trees are never traversed (the hours-long bug).
FIXTURE_EXCL="$TEST_DIR/fixture-excludes"
make_fixture "$FIXTURE_EXCL"
write_values_file "$FIXTURE_EXCL/bootstrap.values"
mkdir -p "$FIXTURE_EXCL/node_modules/some-pkg" "$FIXTURE_EXCL/dist"
cat > "$FIXTURE_EXCL/node_modules/some-pkg/README.md" <<'EOF'
# AITBC in node_modules
Framework: {{EXCLUDED_ONLY_TOKEN}}
EOF
echo "project: AITBC" > "$FIXTURE_EXCL/dist/build.yml"

set +e
excl_output=$(cd "$FIXTURE_EXCL" && bash "$FIXTURE_EXCL/scripts/setup-template.sh" \
    --values "$FIXTURE_EXCL/bootstrap.values" --yes 2>&1)
excl_exit=$?
set -e
assert_exit_code "$excl_exit" 0 "wizard exits 0 with placeholder files present in excluded dirs"
# Tracked source under the repo root IS still substituted.
assert_file_contains "$FIXTURE_EXCL/README.md" "# TestProject" \
    "tracked README.md is still substituted with excludes in place"
# Files inside excluded directories are left completely untouched.
assert_file_contains "$FIXTURE_EXCL/node_modules/some-pkg/README.md" "AITBC" \
    "placeholder in node_modules/ is NOT substituted (dir excluded)"
assert_file_contains "$FIXTURE_EXCL/dist/build.yml" "AITBC" \
    "placeholder in dist/ is NOT substituted (dir excluded)"
# A token that exists ONLY inside node_modules must not appear in the REMAINING
# report -- if node_modules were traversed, it would be listed there.
assert_not_contains "$excl_output" "{{EXCLUDED_ONLY_TOKEN}}" \
    "node_modules-only placeholder is NOT listed in the REMAINING report (dir not traversed)"

# =============================================================================
# Summary
# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ $FAIL -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    exit 1
else
    echo -e "  Failed: 0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
