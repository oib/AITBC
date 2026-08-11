#!/bin/bash
# =============================================================================
# Test: Mechanical boilerplate-migration driver (ABS-227)
# =============================================================================
# Builds a self-contained synthetic "source" boilerplate git repo (tagged
# v1.0.0 and v2.0.0, with an ownership map) plus a "target" consuming project
# installed at 1.0.0 with one drifted file, then drives scripts/migrate-project.sh
# and asserts the ABS-227 acceptance criteria:
#
#   AC1  end-to-end migration runs mechanically in ONE driver invocation
#        (classification/hash/replace happen in the driver, not an LLM context)
#   AC3  conflict hunks are emitted as `diff -u` in the driver report; the seat
#        reads only the report (report-format assertions)
#   AC4  missing ownership map -> deterministic abort with a handlungsanweisung
#   AC5  all abort cases unchanged: marker missing, version newer, dirty tree,
#        failed declared-migration step
#
# AC2 (changelog slicer) is covered by tests/test-changelog-slice.sh.
#
# ABS-228 (ADR-A-0008 Amendment 2026-07-12): the same happy-path fixture also
# exercises the scripts/ ownership surface — an unmodified runner is REPLACED,
# a drifted runner becomes a CONFLICT (never overwritten), and a project-added
# script outside the manifest is never touched.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/tooling/test-migrate-project.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DRIVER="$REPO_ROOT/scripts/migrate-project.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/migrate-project-test.XXXXXX")
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
assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3 (expected '$2', got '$1')"; FAIL=$((FAIL + 1))
    fi
}

git_q() { git -c user.email=t@t -c user.name=test -c commit.gpgsign=false -c init.defaultBranch=main "$@"; }

# -----------------------------------------------------------------------------
# Build the synthetic source boilerplate: v1.0.0 then v2.0.0
# -----------------------------------------------------------------------------
SRC="$TEST_DIR/source"
mkdir -p "$SRC/.agentic/upgrade" "$SRC/.agentic/overrides"
cd "$SRC" || exit 1
git_q init -q .

# --- v1.0.0 tree ---
echo "1.0.0" > .boilerplate-version
printf 'AGENTS v1\n' > AGENTS.md
printf 'shared v1\n' > shared.txt
printf 'thing v1\n' > .agentic/thing.md
printf 'project config (owned by project)\n' > .agentic/config.yaml
mkdir -p adrs/agentic
# Two agentic ADRs (content boilerplate-owned; acceptance frontmatter project-owned, ADR-A-0008)
printf -- '---\nid: ADR-A-0001\ntitle: Alpha\nstatus: proposed\ndate: "2026-01-01"\n---\n\nalpha body v1\n' > adrs/agentic/ADR-A-0001-alpha.md
printf -- '---\nid: ADR-A-0002\ntitle: Beta\nstatus: proposed\ndate: "2026-01-01"\n---\n\nbeta body v1\n' > adrs/agentic/ADR-A-0002-beta.md
# scripts/ surface (ADR-A-0008 Amendment 2026-07-12, ABS-228): a boilerplate-owned
# runner + adapter enumerated as explicit pathspecs, plus a wholly-owned subtree (scripts/lib/).
mkdir -p scripts/lib
printf 'runner v1\n'  > scripts/runner.sh
printf 'adapter v1\n' > scripts/adapter.sh
printf 'lib v1\n'     > scripts/lib/common.sh
# ABS-249: setup-instantiated files. Upstream carries the literal {{TOKEN}}s; the
# target carries the project's values (see make_target). Without token
# normalization each of these re-conflicts at EVERY migration.
printf 'ticket: AITBC-1\nbranch: main\nstable v1\n' > tokened-stable.md
printf 'ticket: AITBC-1\ndrifty v1\n' > tokened-drift.md
printf 'repo: https://github.com/oib/AITBC\nversion: v2.35.0\ntokened runner v1\n' > scripts/tokened.sh
chmod +x scripts/tokened.sh
printf 'crlf v1\n' > crlf.txt
# The wizard's own source: its literal {{TOKEN}}s are DATA (the replacement
# arrays). setup-template.sh excludes itself from its sweep, so the consumer's
# copy keeps the tokens -- the driver must neither substitute nor "normalize" it.
# Shaped like the real wizard (ABS-273): a `declare -a REPLACEMENT_KEYS=(...)`
# block PLUS a token outside it. A hand-substitution instantiates only the array,
# leaving the real wizard with 7 "{{" hits outside it (its own grep patterns and
# doc examples) -- so the corruption check must be scoped to the array block, not
# the whole file. The real-file shape is pinned in the ABS-249 parity block below.
cat > scripts/setup-template.sh <<'WIZ'
declare -a REPLACEMENT_KEYS=(
  "AITBC"
  "main"
)
echo "wizard v1 — run {{DEV_COMMAND}}"
WIZ
# ABS-258 / ADR-A-0022: a boilerplate-owned agent def. The project customizes it
# via an OVERLAY (.agentic/overrides/agents/<role>.append.md) rather than editing
# it, which is the whole point: the def stays byte-pristine and therefore keeps
# classifying REPLACE across migrations instead of CONFLICTing forever.
mkdir -p harness/claude/agents
printf 'qas def v1\n' > harness/claude/agents/qas.md
# ABS-248 / ADR-A-0008 Amendment 2026-07-14: the HARNESS surface. The driver maps
# the GENERATED, shipped domains (.claude/, .gemini/, ...) at the paths a consumer
# actually has -- never harness/claude/ (seat-edit source; consumers have no
# harness/ dir). `.claude/skills/tokened-skill.md` is the ABS-249 regression guard:
# a setup-instantiated harness file must classify REPLACE, not CONFLICT.
# .gemini/ deliberately does NOT exist at v1: it arrives as a NEW upstream domain
# in v2, which is exactly the ADR's risk case -- an unadopted provider domain would
# otherwise land on a Claude-only consumer as a pile of unwanted ADDs.
mkdir -p .claude/agents .claude/skills
printf 'be def v1\n'                                  > .claude/agents/be-developer.md
printf 'prefix: AITBC\nskill v1\n'        > .claude/skills/tokened-skill.md
printf 'team roster (project-owned identity)\n'       > .claude/team-config.json
printf 'hook wiring (project-owned identity)\n'       > .claude/hooks-config.json
cat > .agentic/upgrade/ownership.yaml <<'YAML'
version: 1
boilerplate_owned:
  - .agentic/
  - AGENTS.md
  - shared.txt
  - adrs/agentic/
  - scripts/runner.sh
  - scripts/adapter.sh
  - scripts/tokened.sh
  - scripts/setup-template.sh
  - scripts/lib/
  - tokened-stable.md
  - tokened-drift.md
  - crlf.txt
  - harness/claude/agents/
  - .claude/
  - .gemini/
project_owned_exceptions:
  - .agentic/config.yaml
  - .agentic/overrides/
  - path: .claude/team-config.json
    kind: structural
  - path: .claude/hooks-config.json
    kind: structural
YAML
cat > HARNESS_CHANGELOG.yml <<'YAML'
schema_version: "1.0.0"
generated_at: "2026-01-01T00:00:00Z"
releases:
  - version: "2.0.0"
    date: "2026-02-01"
    summary: "v2 release"
    changes:
      - path: "AGENTS.md"
        category: METHODOLOGY
        change_type: modified
        description: "roster update"
        breaking: true
    migration_notes:
      - "Review the roster change."
  - version: "1.0.0"
    date: "2026-01-01"
    summary: "initial"
    changes: []
YAML
git_q add -A && git_q commit -q -m "v1.0.0"
git_q tag v1.0.0

# --- v2.0.0 tree: modify owned files, add a new one, bump marker ---
echo "2.0.0" > .boilerplate-version
printf 'AGENTS v2\n' > AGENTS.md
printf 'shared v2\n' > shared.txt
printf 'thing v2\n' > .agentic/thing.md
printf 'brand new in v2\n' > .agentic/newfile.md
# scripts/ get upstream fixes v1 -> v2 (ABS-228)
printf 'runner v2\n'  > scripts/runner.sh
printf 'adapter v2\n' > scripts/adapter.sh
printf 'lib v2\n'     > scripts/lib/common.sh
# ABS-249: tokened-stable.md and crlf.txt do NOT change upstream (v1 == v2) --
# their only target-side difference is instantiation / CRLF. tokened.sh and
# tokened-drift.md DO change upstream.
printf 'repo: https://github.com/oib/AITBC\nversion: v2.35.0\ntokened runner v2\n' > scripts/tokened.sh
printf 'ticket: AITBC-1\ndrifty v2\n' > tokened-drift.md
cat > scripts/setup-template.sh <<'WIZ'
declare -a REPLACEMENT_KEYS=(
  "AITBC"
  "main"
)
echo "wizard v2 — run {{DEV_COMMAND}}"
WIZ
# The agent def gets an upstream improvement v1 -> v2 (ABS-258).
printf 'qas def v2\n' > harness/claude/agents/qas.md
# ABS-248: harness fixes ship v1 -> v2. team-config/hooks-config ALSO change
# upstream -- the exception must hold anyway (that is the whole point: a consumer's
# roster/hook wiring is never clobbered, however much upstream moves).
mkdir -p .claude/commands .gemini
printf 'be def v2\n'                            > .claude/agents/be-developer.md
printf 'prefix: AITBC\nskill v2\n'  > .claude/skills/tokened-skill.md
printf 'team roster UPSTREAM REWRITE\n'         > .claude/team-config.json
printf 'hook wiring UPSTREAM REWRITE\n'         > .claude/hooks-config.json
printf 'brand new harness command\n'            > .claude/commands/new-cmd.md
# A whole provider domain arrives new in v2 (the sync_scope gate's reason to exist).
printf 'gemini def v2\n'                        > .gemini/gem.md
# ADR bodies change upstream v1 -> v2; source keeps status: proposed (acceptance is project-owned)
printf -- '---\nid: ADR-A-0001\ntitle: Alpha\nstatus: proposed\ndate: "2026-01-01"\n---\n\nalpha body v2\n' > adrs/agentic/ADR-A-0001-alpha.md
printf -- '---\nid: ADR-A-0002\ntitle: Beta\nstatus: proposed\ndate: "2026-01-01"\n---\n\nbeta body v2\n' > adrs/agentic/ADR-A-0002-beta.md
git_q add -A && git_q commit -q -m "v2.0.0"
git_q tag v2.0.0

# -----------------------------------------------------------------------------
# Helper: build a fresh target project installed at v1.0.0 (clean tree)
# -----------------------------------------------------------------------------
make_target() {
    local dir="$1"
    rm -rf "$dir"; mkdir -p "$dir"
    ( cd "$SRC" && git archive --format=tar v1.0.0 ) | ( cd "$dir" && tar -xf - )
    cd "$dir" || exit 1
    # --- ABS-249: replay what setup-template.sh did at install time -----------
    # The manifest is the evidence for the token map; the files below are the
    # instantiated result (tokens replaced, HARNESS_VERSION = the installed
    # v1.0.0). crlf.txt additionally gets CRLF line endings.
    cat > .harness-manifest.yml <<'YAML'
manifest_version: "1.1"
identity:
  PROJECT_NAME: "Busch"
  PROJECT_REPO: "busch-app"
  GITHUB_ORG: "busch-org"
  TICKET_PREFIX: "BUSCH"
  MAIN_BRANCH: "main"
substitutions: {}
YAML
    printf 'ticket: BUSCH-1\nbranch: main\nstable v1\n' > tokened-stable.md
    printf 'ticket: BUSCH-1\ndrifty v1\n' > tokened-drift.md
    printf 'repo: https://github.com/busch-org/busch-app\nversion: v1.0.0\ntokened runner v1\n' > scripts/tokened.sh
    chmod +x scripts/tokened.sh
    printf 'crlf v1\r\n' > crlf.txt
    # --- ABS-248: the installed harness ---------------------------------------
    # The skill was token-instantiated at install (BUSCH), exactly like every other
    # setup-swept file. The identity files carry the PROJECT's own roster/wiring --
    # never upstream's. No sync_scope in this manifest => default scope [".claude"],
    # so .gemini/ must NOT be migrated into a Claude-only project.
    printf 'prefix: BUSCH\nskill v1\n'      > .claude/skills/tokened-skill.md
    printf 'OUR team roster\n'              > .claude/team-config.json
    printf 'OUR hook wiring\n'              > .claude/hooks-config.json
    git_q init -q .
    git_q add -A && git_q commit -q -m "install boilerplate 1.0.0"
}

# =============================================================================
echo -e "\n${CYAN}=== AC1 + AC3: end-to-end migration (one driver invocation) ===${NC}\n"
# =============================================================================
TARGET="$TEST_DIR/happy"
make_target "$TARGET"
# Introduce local drift on one owned file (a project customization):
cd "$TARGET" || exit 1
printf 'AGENTS v1 LOCALLY PATCHED\n' > AGENTS.md
# Modify a project-owned exception too (must never be touched):
printf 'project config EDITED locally\n' > .agentic/config.yaml
# ADR-A-0001: the project ACCEPTED it (flip status + add accepted_by/accepted_date);
# the body is still the pristine v1 content -> only acceptance frontmatter changed.
printf -- '---\nid: ADR-A-0001\ntitle: Alpha\nstatus: accepted\naccepted_by: alice\naccepted_date: "2026-05-01"\ndate: "2026-01-01"\n---\n\nalpha body v1\n' > adrs/agentic/ADR-A-0001-alpha.md
# ADR-A-0002: the project locally edited the BODY (real content drift).
printf -- '---\nid: ADR-A-0002\ntitle: Beta\nstatus: proposed\ndate: "2026-01-01"\n---\n\nbeta body LOCALLY FORKED\n' > adrs/agentic/ADR-A-0002-beta.md
# scripts/ (ABS-228): runner.sh + lib/common.sh stay pristine v1 (-> REPLACE with v2);
# adapter.sh is locally forked (-> CONFLICT, never overwritten); project-only.sh is a
# project-added script NOT in the ownership map (-> never touched, never a conflict).
printf 'adapter LOCALLY FORKED\n' > scripts/adapter.sh
printf 'my own project script\n'  > scripts/project-only.sh
# ABS-249: tokened-drift.md carries REAL drift on top of the instantiation
# (-> must stay a conflict); tokened-stable.md / crlf.txt / scripts/tokened.sh
# carry ONLY the instantiation (-> must not be conflicts).
printf 'ticket: BUSCH-1\ndrifty LOCALLY FORKED\n' > tokened-drift.md
# ABS-258 / ADR-A-0022: the project customizes the qas def the RIGHT way — it adds
# an overlay and leaves the def itself pristine. This is the exact scenario the
# ADR exists for (the field report's "replace body, re-append project section"
# ritual), so the def must migrate cleanly and the overlay must survive untouched.
mkdir -p .agentic/overrides/agents
printf 'PROJECT SECTION for qas (overlay, not a fork)\n' > .agentic/overrides/agents/qas.append.md
git_q add -A && git_q commit -q -m "local customizations"

OUT="$(bash "$DRIVER" "$TARGET" --source "$SRC" 2>/dev/null)"
RC=$?
assert_eq "$RC" "0" "driver exits 0 on successful migration"
assert_contains "$OUT" "STATUS migrated from=1.0.0 to=2.0.0" "stdout has machine-readable migrated status"
assert_contains "$OUT" "| replaced | 10 |" "stdout summary reports 10 replaced (shared.txt + thing.md + accepted ADR-A-0001 + runner.sh + lib/common.sh + tokened.sh + setup-template.sh + overlaid qas def + ABS-248 harness: be-developer def + tokened skill)"
assert_contains "$OUT" "| added | 2 |" "stdout summary reports 2 added (newfile.md + ABS-248 new harness command)"
assert_contains "$OUT" "| conflicts | 4 |" "stdout summary reports 4 conflicts (AGENTS.md + drifted ADR-A-0002 + drifted adapter.sh + drifted tokened-drift.md)"

# Marker updated
assert_eq "$(cat "$TARGET/.boilerplate-version")" "2.0.0" "target marker stamped to 2.0.0"
# Unmodified owned file replaced with v2
assert_eq "$(cat "$TARGET/shared.txt")" "shared v2" "unmodified shared.txt replaced with v2"
assert_eq "$(cat "$TARGET/.agentic/thing.md")" "thing v2" "unmodified thing.md replaced with v2"
# New file added
assert_eq "$(cat "$TARGET/.agentic/newfile.md")" "brand new in v2" "new file added from v2"
# Drifted file NOT overwritten
assert_eq "$(cat "$TARGET/AGENTS.md")" "AGENTS v1 LOCALLY PATCHED" "drifted AGENTS.md left untouched"
# Project-owned exception untouched
assert_eq "$(cat "$TARGET/.agentic/config.yaml")" "project config EDITED locally" "project-owned config.yaml never touched"
# Branch created + committed
assert_eq "$(git -C "$TARGET" rev-parse --abbrev-ref HEAD)" "boilerplate-migration-1.0.0-to-2.0.0" "on the migration branch"
assert_contains "$(git -C "$TARGET" log --oneline -1)" "migrate boilerplate 1.0.0 -> 2.0.0" "migration commit landed"

# AC3: report format (seat reads ONLY this report)
REPORT="$(cat "$TARGET"/work/migration-reports/*-1.0.0-to-2.0.0.md)"
assert_contains "$REPORT" "## Conflicts Needing Human Decision" "report has Conflicts section"
assert_contains "$REPORT" "### AGENTS.md" "report lists the drifted file as a conflict"
assert_contains "$REPORT" '```diff' "report fences the conflict as a diff block"
assert_contains "$REPORT" "@@" "report diff has a hunk header (@@) — pre-computed diff -u"
assert_contains "$REPORT" "-AGENTS v1 LOCALLY PATCHED" "diff shows the local (target) line"
assert_contains "$REPORT" "+AGENTS v2" "diff shows the incoming line"
assert_contains "$REPORT" "Review the roster change." "report embeds the changelog migration note (slicer)"
assert_not_contains "$REPORT" "### shared.txt" "unmodified replaced files are NOT listed as conflicts"

# ADR-A-0008 special case: acceptance frontmatter drift is IGNORED
ADR1="$(cat "$TARGET/adrs/agentic/ADR-A-0001-alpha.md")"
assert_contains "$ADR1" "alpha body v2" "accepted ADR-A-0001 gets the upstream v2 content"
assert_contains "$ADR1" "status: accepted" "ADR-A-0001 project acceptance status PRESERVED"
assert_contains "$ADR1" "accepted_by: alice" "ADR-A-0001 accepted_by PRESERVED"
assert_contains "$ADR1" 'accepted_date: "2026-05-01"' "ADR-A-0001 accepted_date PRESERVED"
assert_not_contains "$REPORT" "### adrs/agentic/ADR-A-0001-alpha.md" "accepted ADR (frontmatter-only change) is NOT a spurious conflict"
# Real ADR body drift IS a conflict, left untouched
assert_contains "$REPORT" "### adrs/agentic/ADR-A-0002-beta.md" "ADR-A-0002 real body drift IS a conflict"
assert_eq "$(sed -n '$p' "$TARGET/adrs/agentic/ADR-A-0002-beta.md")" "beta body LOCALLY FORKED" "drifted ADR-A-0002 body left untouched"

# --- ABS-228: scripts/ ownership surface (Amendment 2026-07-12) ---------------
# AC2: an UNMODIFIED boilerplate-owned runner is replaced with the upstream version.
assert_eq "$(cat "$TARGET/scripts/runner.sh")" "runner v2" "AC2: unmodified runner.sh replaced with v2"
assert_eq "$(cat "$TARGET/scripts/lib/common.sh")" "lib v2" "AC2: unmodified scripts/lib/ subtree file replaced with v2"
assert_not_contains "$REPORT" "### scripts/runner.sh" "AC2: unmodified runner is NOT a spurious conflict"
# AC3: a DRIFTED consumer runner becomes a CONFLICT in the report and is NEVER overwritten.
assert_contains "$REPORT" "### scripts/adapter.sh" "AC3: drifted adapter.sh IS listed as a conflict"
assert_eq "$(cat "$TARGET/scripts/adapter.sh")" "adapter LOCALLY FORKED" "AC3: drifted adapter.sh left untouched (not overwritten)"
assert_contains "$REPORT" "-adapter LOCALLY FORKED" "AC3: conflict diff shows the local (target) runner line"
assert_contains "$REPORT" "+adapter v2" "AC3: conflict diff shows the incoming runner line"
# Manifest boundary: a project-added script NOT in the map is never touched, never reported.
assert_eq "$(cat "$TARGET/scripts/project-only.sh")" "my own project script" "manifest boundary: project-added script left untouched"
assert_not_contains "$REPORT" "scripts/project-only.sh" "manifest boundary: unmapped project script is not in the report"

# --- ABS-249: setup-token normalization before the diff -----------------------
# AC2: a file whose ONLY local change is the setup instantiation is classified
# unmodified -- never a conflict (the ADR-A-0005/0012/0014 re-conflict loop).
assert_not_contains "$REPORT" "### tokened-stable.md" "AC2: token-only file (unchanged upstream) is NOT a conflict"
assert_not_contains "$REPORT" "- tokened-stable.md" "AC2: token-only file is classified unmodified (already-current, not rewritten)"
assert_eq "$(cat "$TARGET/tokened-stable.md")" "$(printf 'ticket: BUSCH-1\nbranch: main\nstable v1')" "AC2: token-only file keeps its instantiated content"
assert_not_contains "$REPORT" "### crlf.txt" "AC2: CRLF-only difference is NOT a conflict (CR normalization)"
assert_not_contains "$REPORT" "### scripts/tokened.sh" "AC2: instantiated script with a real upstream change is a REPLACE, not a conflict"

# AC1 + write path: an unmodified instantiated file is replaced WITH the tokens
# substituted (the driver must not write literal {{TOKEN}}s into the project --
# the promote-release.sh / setup-template.sh / sync-claude-harness.sh caveat).
TOKENED="$(cat "$TARGET/scripts/tokened.sh")"
assert_contains "$TOKENED" "tokened runner v2" "AC1: unmodified instantiated script replaced with the v2 content"
assert_not_contains "$TOKENED" "{{" "write path: no literal {{TOKEN}} written into the target"
assert_contains "$TOKENED" "repo: https://github.com/busch-org/busch-app" "write path: derived GITHUB_REPO_URL instantiated on write"
assert_contains "$TOKENED" "version: v2.0.0" "write path: HARNESS_VERSION instantiated to the NEW version on write"
assert_eq "$([ -x "$TARGET/scripts/tokened.sh" ] && echo yes || echo no)" "yes" "write path: substituted script keeps its executable bit"

# Sweep-set parity: setup-template.sh excludes ITSELF from substitution (its
# literal {{TOKEN}}s are the replacement arrays). The driver mirrors that: the
# wizard is compared and written RAW -- never substituted, never a spurious
# conflict just because it still carries tokens in the project.
WIZ="$(cat "$TARGET/scripts/setup-template.sh")"
assert_not_contains "$REPORT" "### scripts/setup-template.sh" "sweep parity: token-carrying wizard is NOT a conflict"
assert_contains "$WIZ" "wizard v2" "sweep parity: wizard still gets the upstream v2 content"
assert_contains "$WIZ" 'AITBC' "sweep parity: wizard's literal {{TOKEN}} data is NOT substituted on write"

# AC3: real drift under the instantiation stays a conflict, untouched.
assert_contains "$REPORT" "### tokened-drift.md" "AC3: real drift in an instantiated file IS still a conflict"
assert_eq "$(cat "$TARGET/tokened-drift.md")" "$(printf 'ticket: BUSCH-1\ndrifty LOCALLY FORKED')" "AC3: drifted instantiated file left untouched"
assert_contains "$REPORT" "-drifty LOCALLY FORKED" "AC3: conflict diff shows the local line"
assert_contains "$REPORT" "+drifty v2" "AC3: conflict diff shows the incoming line"
assert_not_contains "$REPORT" "AITBC" "AC3: conflict hunks show instantiated incoming content, not token noise"

# =============================================================================
echo -e "\n${CYAN}=== ABS-249: sweep-set parity with setup-template.sh ===${NC}\n"
# =============================================================================
# is_substitutable() must mirror setup-template.sh's SWEEP_INCLUDE_GLOBS. If setup
# starts instantiating a new file type and the driver doesn't know about it, every
# file of that type silently re-conflicts at EVERY migration -- the ABS-249 bug,
# reintroduced. Mechanical guard so the two lists cannot drift apart unnoticed.
SETUP="$REPO_ROOT/scripts/setup-template.sh"
DRIVER_CASE="$(sed -n '/^is_substitutable()/,/^}/p' "$DRIVER")"
MISSING=""
set -f   # the globs are literals ("*.md"), not patterns to expand against the cwd
for g in $(sed -n '/^SWEEP_INCLUDE_GLOBS=(/,/^)/p' "$SETUP" | grep -o '"[^"]*"' | tr -d '"'); do
    case "$DRIVER_CASE" in *"$g"*) ;; *) MISSING="$MISSING $g" ;; esac
done
set +f
assert_eq "$MISSING" "" "every setup-template.sh SWEEP_INCLUDE_GLOB is handled by the driver's is_substitutable()"
assert_contains "$DRIVER_CASE" "setup-template.sh" "driver mirrors setup's own-source exclusion (its {{TOKEN}}s are data)"

# ABS-273 fail-open guard. The integrity check finds the wizard's keys by matching the
# literal shape `^declare -a REPLACEMENT_KEYS=(` ... `^)`. Every other ABS-273 test runs
# against a STUB fixture, so if that declaration is ever renamed, indented or reformatted
# in the real setup-template.sh, wizard_key_block() would return nothing, the corruption
# check would silently return "not instantiated" (fail OPEN -- it stops catching the exact
# damage it exists for), and every stub-based test would still pass. Worse, the SOP 3.1.2
# hand-check would then print 0, which the SOP defines as CORRUPT -- telling a consumer
# with a healthy wizard that it is broken. So run the DRIVER'S OWN extractor against the
# REAL file: drift on either side (renamed function, changed pattern, reshaped wizard)
# fails this closed instead.
eval "$(sed -n '/^wizard_key_block()/,/^}/p' "$DRIVER")"
REAL_KEYS="$(wizard_key_block "$SETUP" 2>/dev/null | LC_ALL=C grep -c '{{' || true)"
assert_eq "$([ "${REAL_KEYS:-0}" -gt 0 ] && echo found || echo none)" "found" \
    "ABS-273: the driver's own wizard_key_block() still matches the REAL setup-template.sh and finds literal keys (fail-open guard)"

# The driver is itself swept by setup (it is a *.sh and is NOT excluded), so ANY
# literal replacement key in its source becomes a project value in the consumer's
# copy -- a `printf 's|v2.35.0|...'` would ship as `s|v2.25.0|...|`
# and rewrite version strings in the files it WRITES. Build tokens via %s instead.
# Keys are read from setup's own array, so a new upstream token is covered too.
DRIVER_SRC="$(cat "$DRIVER")"
LITERAL_KEYS=""
while IFS= read -r key; do
    case "$DRIVER_SRC" in *"$key"*) LITERAL_KEYS="$LITERAL_KEYS $key" ;; esac
done < <(sed -n '/^declare -a REPLACEMENT_KEYS=(/,/^)/p' "$SETUP" | grep -o '{{[A-Z_]*}}')
assert_eq "$LITERAL_KEYS" "" "driver source carries NO literal setup replacement key (it is swept by setup)"

# --- ABS-258 / ADR-A-0022: an OVERLAID agent def migrates without conflict -----
# The payoff of composing overlays at the spawn seam instead of editing the def:
# the def is byte-pristine, so it takes the upstream improvement (REPLACE) while
# the project's customization survives in the overlay. Neither file conflicts —
# which is exactly the recurring "re-append the project section" ritual, gone.
assert_eq "$(cat "$TARGET/harness/claude/agents/qas.md")" "qas def v2" "ABS-258: overlaid agent def is REPLACED with the upstream v2 def"
assert_not_contains "$REPORT" "### harness/claude/agents/qas.md" "ABS-258: an overlaid def is NOT a conflict (the overlay is not drift)"
assert_eq "$(cat "$TARGET/.agentic/overrides/agents/qas.append.md")" "PROJECT SECTION for qas (overlay, not a fork)" "ABS-258: the project's overlay survives migration untouched"
assert_not_contains "$REPORT" "qas.append.md" "ABS-258: the overlay (project-owned exception) is not in the report at all"

# --- ABS-273: a HEALTHY target reports a clean integrity check ----------------
assert_contains "$REPORT" "## Integrity Check (adopted copies, ABS-273)" "ABS-273: report always carries the integrity section"
assert_contains "$REPORT" "✅ No token corruption found" "ABS-273: healthy adopted copies -> clean verdict"

# =============================================================================
echo -e "\n${CYAN}=== ABS-273: integrity check + repair of token-corrupted copies ===${NC}\n"
# =============================================================================
# The pre-ABS-249 driver shipped setup-instantiated files with literal tokens and
# consumers hand-substituted them. For the WIZARD that fix was inverted: its
# replacement-key array holds the tokens as DATA, so an instantiated copy is
# CORRUPT -- it substitutes the wrong strings on the next setup run, and (because
# the driver never substitutes the wizard) it conflicts on EVERY future migration.
CORRUPT="$TEST_DIR/corrupt"
make_target "$CORRUPT"
cd "$CORRUPT" || exit 1
# Exactly what the consumer's hand-substitution produced: the KEY ARRAY instantiated,
# while the tokens outside it (unmapped, e.g. {{DEV_COMMAND}}) survive untouched. So
# the corrupt file STILL CONTAINS "{{" -- a whole-file token check would grade it
# healthy. Reproduced from the real wizard: hand-substituting its REPLACEMENT_KEYS
# leaves 10 non-array lines carrying "{{" behind. This is the regression this fixture pins.
cat > scripts/setup-template.sh <<'WIZ'
declare -a REPLACEMENT_KEYS=(
  "BUSCH"
  "main"
)
echo "wizard v1 — run {{DEV_COMMAND}}"
WIZ
# AC3, the lower-severity class: an adopted copy the old driver wrote with literal
# tokens where the hand-substitution stayed INCOMPLETE (a mapped token survives).
printf 'ticket: AITBC-1\npromote v1\n' > scripts/promote-release.sh
git_q add -A && git_q commit -q -m "hand-fixed adoption (old driver)"

# NOTE: own variable names — later sections (ABS-259) still assert against the
# happy-path $OUT/$REPORT. Clobbering them here would break THEM, not this block.
OUT_C="$(bash "$DRIVER" "$CORRUPT" --source "$SRC" 2>/dev/null)"
assert_eq "$?" "0" "ABS-273: driver still exits 0 on a corrupted target"
REPORT_C="$(cat "$CORRUPT"/work/migration-reports/*-1.0.0-to-2.0.0.md)"

# AC1: detection — and it must survive the partial-substitution shape above, i.e.
# a corrupt wizard that still carries non-array tokens (the real-world case).
assert_contains "$REPORT_C" "| 🔴 CORRUPT | scripts/setup-template.sh |" "AC1: instantiated wizard detected as CORRUPT"
assert_contains "$(git -C "$CORRUPT" show HEAD~1:scripts/setup-template.sh 2>/dev/null || true)" "{{DEV_COMMAND}}" "AC1 regression: the corrupt copy still contained {{TOKEN}}s — detection is array-scoped, not whole-file"
# AC2: repair = restore from upstream (boilerplate-owned, no legitimate drift)
WIZ_C="$(cat "$CORRUPT/scripts/setup-template.sh")"
assert_contains "$WIZ_C" 'AITBC' "AC2: wizard's literal replacement keys restored from upstream"
assert_contains "$WIZ_C" "wizard v2" "AC2: restored wizard is the current upstream version"
assert_contains "$REPORT_C" "**Repaired**: restored verbatim from upstream" "AC2: report states the repair"
# The permanent-conflict generator is gone: the wizard is a REPLACE, not a CONFLICT.
assert_not_contains "$REPORT_C" "### scripts/setup-template.sh" "AC2: repaired wizard is NOT left as a recurring conflict"
assert_contains "$OUT_C" "| conflicts | 0 |" "AC2: corrupted wizard no longer counts as unresolvable drift"
# AC3: residue in the lower-severity class is reported, never auto-repaired
assert_contains "$REPORT_C" "| 🟡 TOKEN RESIDUE | scripts/promote-release.sh |" "AC3: incomplete substitution in an adopted copy is reported"
assert_contains "$(cat "$CORRUPT/scripts/promote-release.sh")" 'AITBC' "AC3: residue class is report-only — the file is not rewritten"

# --- AC4: the REPORT's hand-check states the same predicate as the driver --------
# The report is the one artefact the consumer actually reads, and it tells them to
# "verify by hand at any time". It shipped the SUPERSEDED all-or-nothing predicate
# (`grep -c '{{'`, legend "corrupt: 0") while the driver 300 lines up was already
# entry-wise: on the realistic PARTIAL damage the snippet prints 27, reads non-zero,
# and its own legend calls that HEALTHY -- 15 lines under a table saying CORRUPT.
#
# That bug reached its THIRD generation (whole-file -> array-scoped -> all-or-nothing
# -> entry-wise) for exactly one reason: nothing tested the report's TEXT. These
# assertions are that missing test. They pin the predicate the consumer is handed.
assert_contains "$REPORT_C" '# healthy: TOKENS == ENTRIES' "AC4: the report's hand-check legend is entry-wise"
assert_contains "$REPORT_C" 'echo "$TOKENS/$ENTRIES replacement keys still literal"' "AC4: the report's snippet compares token-shaped entries against ALL entries"
assert_not_contains "$REPORT_C" "corrupt: 0" "AC4 regression: the superseded all-or-nothing legend is gone from the report"
assert_not_contains "$REPORT_C" "| grep -c '{{'" "AC4 regression: the superseded whole-array token count is gone from the report"

# Parity, so there is no FOURTH generation: the snippet the report hands the consumer
# must carry the driver's OWN token predicate, character for character. If someone
# changes how wizard_is_instantiated() recognises a healthy entry, this fails until
# the report is changed with it -- report, SOP §3.1.2 and driver state ONE predicate.
WIZ_PRED='^[[:space:]]*"{{[A-Z_]*}}"'
assert_contains "$(cat "$DRIVER")" "$WIZ_PRED" "AC4: the driver's detector uses the token-shape predicate"
assert_contains "$REPORT_C" "$WIZ_PRED" "AC4: the report hands the consumer the driver's own predicate (no drift)"

# --- AC1, PARTIAL substitution: the LIKELY real-world shape of the damage --------
# The consumer substitutes from their manifest token map, which covers only a SUBSET
# of the wizard's 30 keys. So the realistic corrupt wizard has SOME keys instantiated
# and the rest still literal (e.g. 26/30). A detector asking "does the key array still
# contain any {{ ?" grades exactly that HEALTHY and misses the corruption it exists to
# find -- the array-scoped variant of the whole-file bug. Corruption is therefore
# judged ENTRY-WISE: any array entry that is no longer "{{TOKEN}}"-shaped is damage.
PARTIAL="$TEST_DIR/partial"
make_target "$PARTIAL"
cd "$PARTIAL" || exit 1
cat > scripts/setup-template.sh <<'WIZ'
declare -a REPLACEMENT_KEYS=(
  "BUSCH"
  "main"
)
echo "wizard v1 — run {{DEV_COMMAND}}"
WIZ
git_q add -A && git_q commit -q -m "hand-fixed adoption, partial (old driver)"
OUT_P="$(bash "$DRIVER" "$PARTIAL" --source "$SRC" 2>/dev/null)"
REPORT_P="$(cat "$PARTIAL"/work/migration-reports/*-1.0.0-to-2.0.0.md)"
assert_contains "$REPORT_P" "| 🔴 CORRUPT | scripts/setup-template.sh |" "AC1: PARTIALLY instantiated wizard detected as CORRUPT (key array still holds a literal token)"
assert_contains "$(cat "$PARTIAL/scripts/setup-template.sh")" "wizard v2" "AC2: partially corrupted wizard is restored from upstream too"
assert_contains "$OUT_P" "| conflicts | 0 |" "AC2: partially corrupted wizard is not left as a recurring conflict"

# =============================================================================
echo -e "\n${CYAN}=== up-to-date: same version is a no-op ===${NC}\n"
# =============================================================================
UPTODATE="$TEST_DIR/uptodate"
make_target "$UPTODATE"
echo "2.0.0" > "$UPTODATE/.boilerplate-version"
( cd "$UPTODATE" && git_q commit -aq -m "bump" )
OUT="$(bash "$DRIVER" "$UPTODATE" --source "$SRC" 2>/dev/null)"; RC=$?
assert_eq "$RC" "0" "up-to-date target exits 0"
assert_contains "$OUT" "STATUS up-to-date" "up-to-date reported"

# =============================================================================
echo -e "\n${CYAN}=== AC4: missing ownership map -> deterministic abort ===${NC}\n"
# =============================================================================
SRC_NOMAP="$TEST_DIR/source-nomap"
cp -R "$SRC" "$SRC_NOMAP"
rm -f "$SRC_NOMAP/.agentic/upgrade/ownership.yaml"
TARGET4="$TEST_DIR/nomap-target"
make_target "$TARGET4"
ERR="$(bash "$DRIVER" "$TARGET4" --source "$SRC_NOMAP" 2>&1 1>/dev/null)"; RC=$?
assert_eq "$RC" "6" "missing ownership map exits 6"
assert_contains "$ERR" "Ownership map not found" "abort names the missing map"
assert_contains "$ERR" "no LLM tree-classification fallback" "abort states no LLM fallback"
assert_contains "$ERR" "Handlungsanweisung" "abort gives a handlungsanweisung"

# =============================================================================
echo -e "\n${CYAN}=== AC5: abort cases unchanged ===${NC}\n"
# =============================================================================
# (a) marker missing
TARGET5a="$TEST_DIR/nomarker"; make_target "$TARGET5a"
rm -f "$TARGET5a/.boilerplate-version"; ( cd "$TARGET5a" && git_q commit -aq -m "drop marker" )
ERR="$(bash "$DRIVER" "$TARGET5a" --source "$SRC" 2>&1 1>/dev/null)"; RC=$?
assert_eq "$RC" "3" "missing .boilerplate-version marker exits 3"
assert_contains "$ERR" "no .boilerplate-version marker" "marker-missing message present"

# (b) target version newer than source
TARGET5b="$TEST_DIR/newer"; make_target "$TARGET5b"
echo "3.0.0" > "$TARGET5b/.boilerplate-version"; ( cd "$TARGET5b" && git_q commit -aq -m "future version" )
ERR="$(bash "$DRIVER" "$TARGET5b" --source "$SRC" 2>&1 1>/dev/null)"; RC=$?
assert_eq "$RC" "4" "target-newer-than-source exits 4"
assert_contains "$ERR" "NEWER than source" "newer-version message present"

# (c) dirty working tree -- TRACKED modification still blocks (ABS-277)
TARGET5c="$TEST_DIR/dirty"; make_target "$TARGET5c"
echo "uncommitted" >> "$TARGET5c/shared.txt"   # leave uncommitted
ERR="$(bash "$DRIVER" "$TARGET5c" --source "$SRC" 2>&1 1>/dev/null)"; RC=$?
assert_eq "$RC" "5" "tracked modification exits 5"
assert_contains "$ERR" "TRACKED files" "tracked-dirty message present"
assert_contains "$ERR" "shared.txt" "tracked-dirty message NAMES the offending path (AC3)"

# =============================================================================
echo -e "\n${CYAN}=== ABS-277: clean-tree gate blocks only REAL collisions ===${NC}\n"
# =============================================================================
# (a) AC1: an unrelated untracked file does NOT block. This is the consumer's
#     exact case (extension/package-lock.json on a Windows v2.21.2->v2.25.0 run):
#     pre-ABS-277 the blanket `git status --porcelain` check made it an exit 5.
TARGET277a="$TEST_DIR/untracked-unrelated"; make_target "$TARGET277a"
mkdir -p "$TARGET277a/extension"
printf 'lockfile noise\n' > "$TARGET277a/extension/package-lock.json"   # untracked, off-surface
printf 'scratch\n'        > "$TARGET277a/notes.txt"                     # untracked, off-surface
# A path with a SPACE: `git status --porcelain` C-quotes it ("my notes.txt"), which
# would miss its unstage pathspec and commit the file. The driver reads -z for that
# reason; without it this file gets tracked, and dropping the branch then DELETES it.
printf 'spaced\n'         > "$TARGET277a/my notes.txt"                  # untracked, off-surface
OUT="$(bash "$DRIVER" "$TARGET277a" --source "$SRC" 2>/dev/null)"; RC=$?
assert_eq "$RC" "0" "unrelated untracked files do NOT block the migration (AC1)"
assert_contains "$OUT" "STATUS migrated from=1.0.0 to=2.0.0" "migration ran to completion despite untracked noise"
assert_eq "$(cat "$TARGET277a/extension/package-lock.json")" "lockfile noise" "unrelated untracked file left untouched"
assert_eq "$(cat "$TARGET277a/.agentic/newfile.md")" "brand new in v2" "owned file still added normally"
# ...and they must stay OUT of the migration commit: `git add -A` would otherwise
# sweep them in, which is what the old blanket gate was implicitly protecting.
COMMITTED="$(git -C "$TARGET277a" show --stat --name-only --format= HEAD)"
assert_not_contains "$COMMITTED" "extension/package-lock.json" "off-surface untracked file NOT swept into the migration commit"
assert_not_contains "$COMMITTED" "notes.txt" "off-surface untracked file NOT swept into the migration commit (2)"
assert_contains "$COMMITTED" ".agentic/newfile.md" "the migration's own writes ARE in the commit"
assert_eq "$(cat "$TARGET277a/my notes.txt")" "spaced" "untracked path WITH A SPACE left untouched"
assert_eq "$(git -C "$TARGET277a" ls-files -- 'my notes.txt')" "" "untracked path WITH A SPACE stays untracked, NOT committed"
assert_contains "$(git -C "$TARGET277a" status --porcelain)" "?? extension/" "tolerated file is still untracked afterwards"

# (b) AC1 + AC3: an untracked file ON the owned surface DOES block, and the
#     message names it. .agentic/newfile.md is an ADD in v2 -- migration would
#     overwrite this file with no git history to recover it.
TARGET277b="$TEST_DIR/untracked-collide"; make_target "$TARGET277b"
printf 'my precious local file\n' > "$TARGET277b/.agentic/newfile.md"   # untracked, ON surface
printf 'lockfile noise\n'         > "$TARGET277b/unrelated.txt"         # untracked, off-surface
ERR="$(bash "$DRIVER" "$TARGET277b" --source "$SRC" 2>&1 1>/dev/null)"; RC=$?
assert_eq "$RC" "5" "untracked file colliding with the owned surface exits 5 (AC1)"
assert_contains "$ERR" "sit ON the boilerplate-owned surface" "collision message present"
assert_contains "$ERR" ".agentic/newfile.md" "collision message NAMES the colliding path (AC3)"
assert_not_contains "$ERR" "unrelated.txt" "collision message does NOT name off-surface untracked files (AC3)"
assert_contains "$ERR" "--allow-untracked" "collision message points at the override flag (AC2)"
assert_eq "$(cat "$TARGET277b/.agentic/newfile.md")" "my precious local file" "colliding file NOT overwritten on abort"

# (c) AC2: --allow-untracked forces past the collision. The file is then handed to
#     the normal classifier, which keys on file EXISTENCE: no v1.0.0 baseline exists
#     for it, so it lands as a CONFLICT -- reported for a human decision, never
#     silently overwritten. That is the safe outcome the flag opts into.
OUT="$(bash "$DRIVER" "$TARGET277b" --source "$SRC" --allow-untracked 2>/dev/null)"; RC=$?
assert_eq "$RC" "0" "--allow-untracked proceeds through an owned-surface collision (AC2)"
assert_eq "$(cat "$TARGET277b/.agentic/newfile.md")" "my precious local file" "colliding file is classified, NOT silently overwritten"
REPORT277="$(cat "$TARGET277b"/work/migration-reports/*-1.0.0-to-2.0.0.md)"
assert_contains "$REPORT277" "### .agentic/newfile.md" "colliding file surfaces as a conflict for human decision"

# (d) A project-owned EXCEPTION is not part of the migration set, so an untracked
#     file there never blocks -- migration would not touch it anyway.
TARGET277d="$TEST_DIR/untracked-exception"; make_target "$TARGET277d"
mkdir -p "$TARGET277d/.agentic/overrides"
printf 'local override\n' > "$TARGET277d/.agentic/overrides/mine.md"    # untracked, exception path
OUT="$(bash "$DRIVER" "$TARGET277d" --source "$SRC" 2>/dev/null)"; RC=$?
assert_eq "$RC" "0" "untracked file under a project-owned exception does NOT block"
assert_eq "$(cat "$TARGET277d/.agentic/overrides/mine.md")" "local override" "exception-path file left untouched"

# (d) declared migration step fails -> abort 7, marker NOT stamped, no commit
SRC_MIG="$TEST_DIR/source-mig"
cp -R "$SRC" "$SRC_MIG"
mkdir -p "$SRC_MIG/.agentic/upgrade/migrations"
cat > "$SRC_MIG/.agentic/upgrade/migrations/1.5.0.sh" <<'SH'
#!/bin/bash
echo "declared migration 1.5.0 failing on purpose" >&2
exit 1
SH
chmod +x "$SRC_MIG/.agentic/upgrade/migrations/1.5.0.sh"
TARGET5d="$TEST_DIR/migfail"; make_target "$TARGET5d"
ERR="$(bash "$DRIVER" "$TARGET5d" --source "$SRC_MIG" 2>&1 1>/dev/null)"; RC=$?
assert_eq "$RC" "7" "failed declared migration exits 7"
assert_contains "$ERR" "declared migration step FAILED" "migration-failure message present"
assert_eq "$(cat "$TARGET5d/.boilerplate-version")" "1.0.0" "marker NOT stamped after failed migration"
assert_not_contains "$(git -C "$TARGET5d" log --oneline)" "migrate boilerplate" "no migration commit after failed migration"

# =============================================================================
echo -e "\n${CYAN}=== ABS-259: fork budget (ADR-A-0008 Amendment 2026-07-13) ===${NC}\n"
# =============================================================================
# The happy-path fixture above declares LEGACY bare-path exceptions
# (.agentic/config.yaml, .agentic/overrides/). They must stay valid exceptions
# (never touched -- asserted above) while grading as unattributed forks.
assert_contains "$REPORT" "## Fork Budget (project_owned_exceptions)" "report has the Fork Budget section"
assert_contains "$REPORT" "UNJUSTIFIED | .agentic/config.yaml |" "legacy bare-path exception grades UNJUSTIFIED (backward compatible)"

# --- A source whose map uses the new block-mapping schema ---------------------
SRC_FORK="$TEST_DIR/source-fork"
cp -R "$SRC" "$SRC_FORK"
cat > "$SRC_FORK/.agentic/upgrade/ownership.yaml" <<'YAML'
version: 1
boilerplate_owned:
  - .agentic/
  - AGENTS.md
  - shared.txt
  - adrs/agentic/
  - scripts/runner.sh
  - scripts/adapter.sh
  - scripts/lib/
project_owned_exceptions:
  # STRUCTURAL: project-owned by design. The source DOES ship a default
  # config.yaml and the target edited it -- this must NEVER grade red.
  - path: .agentic/config.yaml
    kind: structural
  # Justified fork (flips to STALE when the budget is exceeded).
  - path: scripts/adapter.sh
    kind: fork
    upstream_ref: ABS-999
    since: "2024-01-01"
  # Second dated fork, exactly 100 days later (spans the 2024 leap February).
  # QUOTED path + trailing comment, and the target holds it PRISTINE at v1: the old
  # cleaning order left a stray trailing quote, is_exception never matched, and the
  # pinned file was silently REPLACED with v2. Regression guard (ABS-259).
  - path: "shared.txt"   # pinned by us, quoted + commented
    kind: fork
    upstream_ref: ABS-997
    since: "2024-04-10"
  # DE-FORKABLE, and deliberately a legacy bare path with no upstream_ref:
  # DE-FORK must take precedence over UNJUSTIFIED.
  - scripts/runner.sh
  # UNJUSTIFIED legacy bare path (target still v1, upstream ships v2).
  - scripts/lib/common.sh
  # ORPHAN: upstream ships no file at this path.
  - path: scripts/gone.sh
    kind: fork
    upstream_ref: ABS-998
    since: "2024-01-01"
YAML

make_fork_target() {
    make_target "$1"
    cd "$1" || exit 1
    printf 'adapter LOCALLY FORKED\n' > scripts/adapter.sh   # fork, differs from upstream v2
    printf 'runner v2\n'              > scripts/runner.sh    # upstream CONVERGED on our version -> DE-FORK
    printf 'gone local\n'             > scripts/gone.sh      # upstream ships no such file -> ORPHAN
    printf 'project config EDITED locally\n' > .agentic/config.yaml
    # scripts/lib/common.sh stays pristine v1 (upstream v2) -> UNJUSTIFIED
    # shared.txt stays PRISTINE v1 and is a quoted+commented exception -> it must be
    # skipped (still "shared v1"), not silently upgraded to v2.
    git_q add -A && git_q commit -q -m "local forks"
}

# --- Run 1: generous budget -> the dated fork is JUSTIFIED --------------------
FORKT="$TEST_DIR/forkbudget"
make_fork_target "$FORKT"
OUT="$(MIGRATE_FORK_MAX_AGE_DAYS=100000 bash "$DRIVER" "$FORKT" --source "$SRC_FORK" 2>/dev/null)"; RC=$?
assert_eq "$RC" "0" "fork budget never changes the exit code (report-only)"
FREPORT="$(cat "$FORKT"/work/migration-reports/*-1.0.0-to-2.0.0.md)"

assert_contains "$FREPORT" " JUSTIFIED | scripts/adapter.sh | fork | ABS-999 |" "AC3: justified fork (upstream_ref + since, in budget)"
assert_contains "$FREPORT" "UNJUSTIFIED | scripts/lib/common.sh |" "AC3: unjustified fork (legacy bare path, no upstream_ref)"
assert_contains "$FREPORT" "DE-FORK | scripts/runner.sh |" "AC3: de-forkable fork (target content == current upstream)"
assert_contains "$FREPORT" "ORPHAN | scripts/gone.sh |" "orphan: upstream ships no file at that path"
assert_contains "$FREPORT" "STRUCTURAL | .agentic/config.yaml |" "structural exception is graded STRUCTURAL"
# The trap: a shipped-and-edited config.yaml must NOT be red just because it differs.
assert_not_contains "$FREPORT" "UNJUSTIFIED | .agentic/config.yaml |" "structural exception is NEVER red (kind is explicit, never inferred)"
assert_not_contains "$FREPORT" "STALE | .agentic/config.yaml |" "structural exception never ages out"
# DE-FORK precedence: runner.sh has no upstream_ref, yet upstream shipped its content.
assert_not_contains "$FREPORT" "UNJUSTIFIED | scripts/runner.sh |" "DE-FORK takes precedence over UNJUSTIFIED"
# Exceptions are still exceptions: never overwritten, never a conflict.
assert_eq "$(cat "$FORKT/scripts/adapter.sh")" "adapter LOCALLY FORKED" "block-mapping exception is still never touched"
assert_not_contains "$FREPORT" "### scripts/adapter.sh" "an exception is never reported as a conflict"
# Regression (ABS-259): a QUOTED path with a trailing comment must still be honoured
# as an exception. The old cleaning order left a stray trailing quote, so is_exception
# never matched and this pinned-at-v1 file was SILENTLY REPLACED with v2.
assert_eq "$(cat "$FORKT/shared.txt")" "shared v1" "quoted+commented exception path is honoured (pinned file NOT silently upgraded)"
assert_contains "$FREPORT" " JUSTIFIED | shared.txt | fork | ABS-997 |" "quoted+commented exception is graded, not mis-parsed"

# Age is computed (awk days-from-civil -- no date -d / date -j).
AGE_A="$(printf '%s\n' "$FREPORT" | grep -F ' JUSTIFIED | scripts/adapter.sh' | awk -F'|' '{gsub(/ /,"",$6); print $6}')"
AGE_S="$(printf '%s\n' "$FREPORT" | grep -F ' JUSTIFIED | shared.txt'         | awk -F'|' '{gsub(/ /,"",$6); print $6}')"
case "$AGE_A" in ''|*[!0-9]*) NUMERIC=no ;; *) NUMERIC=yes ;; esac
assert_eq "$NUMERIC" "yes" "AC2: exception age is reported as an integer number of days"
# Exact, non-rotting arithmetic check: the two `since` dates are exactly 100 days
# apart across the 2024 leap February, so their ages must differ by exactly 100
# whatever today is.
if [ "$NUMERIC" = "yes" ] && [ -n "$AGE_S" ]; then
    assert_eq "$((AGE_A - AGE_S))" "100" "AC2: age arithmetic is exact across a leap February (100-day span)"
else
    assert_eq "unparsable-ages" "100" "AC2: age arithmetic is exact across a leap February (100-day span)"
fi

# --- Run 2: zero budget -> the SAME justified fork goes STALE -----------------
FORKT2="$TEST_DIR/forkbudget-stale"
make_fork_target "$FORKT2"
OUT="$(MIGRATE_FORK_MAX_AGE_DAYS=0 bash "$DRIVER" "$FORKT2" --source "$SRC_FORK" 2>/dev/null)"; RC=$?
assert_eq "$RC" "0" "a stale fork NEVER blocks the migration (exit code unchanged)"
SREPORT="$(cat "$FORKT2"/work/migration-reports/*-1.0.0-to-2.0.0.md)"
assert_contains "$SREPORT" "STALE | scripts/adapter.sh | fork | ABS-999 |" "AC2: justified fork past the budget grades STALE"
assert_contains "$SREPORT" "Budget: **0 days**" "MIGRATE_FORK_MAX_AGE_DAYS overrides the 90-day default"
assert_contains "$SREPORT" "DE-FORK | scripts/runner.sh |" "de-fork verdict is independent of the age budget"
assert_eq "$(cat "$FORKT2/scripts/adapter.sh")" "adapter LOCALLY FORKED" "stale fork is still never overwritten"

# =============================================================================
echo -e "\n${CYAN}=== ABS-264: consumer-declarable forks via ownership.local.yaml (map union) ===${NC}\n"
# =============================================================================
# A source whose map declares ownership.local.yaml as a structural exception
# (matching the shipped ownership.yaml). The driver reads the map from the
# working checkout, so overwriting SRC_LOCAL's ownership.yaml is enough — no
# re-tag needed (baseline hashing still uses the v1.0.0 tag).
SRC_LOCAL="$TEST_DIR/source-local"
cp -R "$SRC" "$SRC_LOCAL"
cat > "$SRC_LOCAL/.agentic/upgrade/ownership.yaml" <<'YAML'
version: 1
boilerplate_owned:
  - .agentic/
  - AGENTS.md
  - shared.txt
  - adrs/agentic/
  - scripts/runner.sh
  - scripts/adapter.sh
  - scripts/lib/
project_owned_exceptions:
  - path: .agentic/config.yaml
    kind: structural
  # Carried as a structural exception so the consumer's fork-declaration map
  # itself has zero conflict surface (AC3).
  - path: .agentic/upgrade/ownership.local.yaml
    kind: structural
YAML

TARGETL="$TEST_DIR/local-map"
make_target "$TARGETL"
cd "$TARGETL" || exit 1
# The consumer declares a fork that upstream does NOT exempt: scripts/runner.sh is
# boilerplate-owned (pristine v1 here; upstream ships v2). Without the local map it
# would be REPLACED; with it, it must be PRESERVED and graded in the report (AC1).
# A local `boilerplate_owned:` block must be IGNORED (subtract-only, AC2).
LOCAL_MAP_CONTENT='version: 1
# Subtract-only guard (AC2): a local boilerplate_owned MUST be ignored.
boilerplate_owned:
  - scripts/project-only.sh
project_owned_exceptions:
  - path: scripts/runner.sh
    kind: fork
    upstream_ref: LOCAL-1
    since: "2026-01-01"'
printf '%s\n' "$LOCAL_MAP_CONTENT" > .agentic/upgrade/ownership.local.yaml
# A project-added file the consumer never declared in the SOURCE map — must migrate
# normally regardless of local-map content (shared.txt stays pristine v1 -> REPLACE).
git_q add -A && git_q commit -q -m "declare a local fork via ownership.local.yaml"

LERR="$TEST_DIR/local-map.err"
OUT="$(MIGRATE_FORK_MAX_AGE_DAYS=100000 bash "$DRIVER" "$TARGETL" --source "$SRC_LOCAL" 2>"$LERR")"; RC=$?
LREPORT="$(cat "$TARGETL"/work/migration-reports/*-1.0.0-to-2.0.0.md)"

# AC6: report-only — the union never changes the exit code.
assert_eq "$RC" "0" "AC6: exit code unchanged (report-only) with a local map present"
# AC1: a fork declared ONLY in ownership.local.yaml is honored (PRESERVED, not REPLACE)…
assert_eq "$(cat "$TARGETL/scripts/runner.sh")" "runner v1" "AC1: fork declared only in ownership.local.yaml is PRESERVED (not replaced)"
assert_not_contains "$LREPORT" "### scripts/runner.sh" "AC1: a local-map exception is never a CONFLICT"
# …AND appears in the Fork Budget report table.
assert_contains "$LREPORT" "scripts/runner.sh | fork | LOCAL-1 |" "AC1: local-map fork appears in the ## Fork Budget table with its verdict"
# AC2: subtract-only — an upstream-owned file the consumer never declared migrates normally.
assert_eq "$(cat "$TARGETL/shared.txt")" "shared v2" "AC2: an undeclared upstream-owned file still migrates (local map only subtracts)"
assert_contains "$(cat "$LERR")" "SUBTRACT-ONLY" "AC2: a local boilerplate_owned: block is IGNORED with a warning (never extends the managed surface)"
# AC3: ownership.local.yaml is itself carried as a structural exception.
assert_eq "$(cat "$TARGETL/.agentic/upgrade/ownership.local.yaml")" "$LOCAL_MAP_CONTENT" "AC3: ownership.local.yaml is PRESERVED byte-for-byte through migration"
assert_contains "$LREPORT" "STRUCTURAL | .agentic/upgrade/ownership.local.yaml" "AC3: ownership.local.yaml is graded STRUCTURAL in the report"

# =============================================================================
echo -e "\n${CYAN}=== ABS-248: the harness surface enters the ownership map (ADR-A-0008 Amdt 2026-07-14) ===${NC}\n"
# =============================================================================
# Before ABS-248 NO harness domain was mapped, so `git ls-files` never yielded a
# `.claude/` path, the REPLACE/ADD lists never contained one, and the harness never
# migrated at all -- consumers hand-applied the `.claude` delta for three releases.

# --- Case 1: a Claude-only project (no sync_scope => schema default [".claude"]) --
TARGETH="$TEST_DIR/harness"
make_target "$TARGETH"
HERR="$TEST_DIR/harness.err"
OUTH="$(bash "$DRIVER" "$TARGETH" --source "$SRC" 2>"$HERR")"; RCH=$?
HREPORT="$(cat "$TARGETH"/work/migration-reports/*-1.0.0-to-2.0.0.md)"
HALL="$OUTH$(cat "$HERR")"

assert_eq "$RCH" "0" "AC1: driver exits 0 with the harness surface mapped"
# AC1 -- the census is non-empty: the harness actually migrates. This is THE bug.
assert_eq "$(cat "$TARGETH/.claude/agents/be-developer.md")" "be def v2" "AC1: a pristine harness agent-def is REPLACED with upstream v2 (harness census non-empty)"
assert_eq "$(cat "$TARGETH/.claude/commands/new-cmd.md")" "brand new harness command" "AC1: a brand-new upstream harness file is ADDed"

# AC2 -- the ABS-249 regression guard. A setup-instantiated harness file must
# classify REPLACE and be re-instantiated; if the driver hashed the RAW upstream
# baseline it would mismatch the substituted target and CONFLICT on every release
# -- the ~193 phantom conflicts that made shipping the original ACs negative value.
assert_eq "$(cat "$TARGETH/.claude/skills/tokened-skill.md")" "$(printf 'prefix: BUSCH\nskill v2')" "AC2: a token-substituted harness file is REPLACED and re-instantiated (BUSCH), not left at v1"
assert_not_contains "$HREPORT" "### .claude/skills/tokened-skill.md" "AC2 (ABS-249 regression guard): an instantiated harness file classifies REPLACE, NOT a phantom CONFLICT"

# AC3 -- project identity is never clobbered, even though upstream REWROTE both files.
assert_eq "$(cat "$TARGETH/.claude/team-config.json")" "OUR team roster" "AC3: .claude/team-config.json byte-unchanged (identity never clobbered, though upstream rewrote it)"
assert_eq "$(cat "$TARGETH/.claude/hooks-config.json")" "OUR hook wiring" "AC3: .claude/hooks-config.json byte-unchanged"
assert_not_contains "$HREPORT" "### .claude/team-config.json" "AC3: an identity exception is never reported as a CONFLICT"

# AC4 -- the sync_scope gate: the migration surface equals the INSTALL surface.
assert_eq "$([ -e "$TARGETH/.gemini/gem.md" ] && echo present || echo absent)" "absent" "AC4: a Claude-only target (default sync_scope) receives ZERO .gemini/ ADDs"

# AC5 -- the delegation is gone; the generic path is the single mechanism.
assert_not_contains "$HALL" "sync-claude-harness" "AC5: the driver never delegates to sync-claude-harness.sh (the dead, thrice-broken DELEGATE_CLAUDE path is retired)"

# --- Case 2: a project that ADOPTED .gemini in its manifest sync_scope ------------
TARGETG="$TEST_DIR/harness-gemini"
make_target "$TARGETG"
cd "$TARGETG" || exit 1
# Real schema shape: nested under `sync:`, quoted, trailing slashes.
cat >> .harness-manifest.yml <<'YAML'
sync:
  sync_scope:
    - ".claude/"
    - ".gemini/"
YAML
git_q add -A && git_q commit -q -m "adopt the .gemini harness"
bash "$DRIVER" "$TARGETG" --source "$SRC" >/dev/null 2>&1
assert_eq "$(cat "$TARGETG/.gemini/gem.md")" "gemini def v2" "AC4: a target that ADOPTS .gemini in sync_scope DOES receive the .gemini harness"

# --- Case 3: manifest `protected:` is folded into the exception set --------------
TARGETP="$TEST_DIR/harness-protected"
make_target "$TARGETP"
cd "$TARGETP" || exit 1
# v1.0-style scope-relative path (no domain prefix): the driver normalizes it by
# prepending `.claude/`, exactly as the harness loader does. The file is left
# PRISTINE, so without the fold it would classify REPLACE and be overwritten --
# which is what makes this assertion load-bearing rather than vacuous.
cat >> .harness-manifest.yml <<'YAML'
protected:
  - "agents/be-developer.md"
YAML
git_q add -A && git_q commit -q -m "protect the be-developer def via the manifest"
bash "$DRIVER" "$TARGETP" --source "$SRC" >/dev/null 2>&1
assert_eq "$(cat "$TARGETP/.claude/agents/be-developer.md")" "be def v1" "AC3: a manifest-\`protected:\` harness file is honored by migration (v1.0 scope-relative path normalized to .claude/)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
# =============================================================================
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}\n"
    exit 1
else
    echo -e "  Failed: 0\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
