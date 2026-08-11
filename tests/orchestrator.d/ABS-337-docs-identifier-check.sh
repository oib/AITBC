# =============================================================================
# ABS-337 — docs-story identifier checker (fabricated ORCH_*/scripts/* tokens)
# -----------------------------------------------------------------------------
# Sourced by tests/tooling/test-orchestrator.sh (shared assert helpers / counters).
#
# scripts/docs-identifier-check.sh fails a docs-only change whose prose cites an
# ORCH_* env token absent from scripts/ or a scripts/* path that does not exist —
# the mechanical factual gate the ABS-124 skip matrix strips off a skip-review +
# skip-test docs story (closes the ABS-303 fabricated-knob defect). Gated behind
# ORCH_DOCS_IDENTIFIER_CHECK (default 0 = off = today's behaviour).
# =============================================================================
echo -e "\n${CYAN}ABS-337 — docs-story identifier checker (fabricated ORCH_*/scripts/* tokens)${NC}"

_ABS337_CHECK="$REPO_ROOT/scripts/docs-identifier-check.sh"
_ABS337_SB="$(mktemp -d /tmp/abs337-XXXXXX)"
_ABS337_RUNLOG="$_ABS337_SB/run.log"

# A docs file under one of the gated scopes, citing a FABRICATED ORCH_ knob
# inside a copy-pasteable snippet (the exact ABS-303 shape).
mkdir -p "$_ABS337_SB/work/improvement-proposals" "$_ABS337_SB/docs"
_abs337_doc() {  # _abs337_doc <relpath> <body>
    local rel="$1" body="$2"
    mkdir -p "$_ABS337_SB/$(dirname "$rel")"
    printf '%s\n' "$body" > "$_ABS337_SB/$rel"
    printf '%s' "$_ABS337_SB/$rel"
}

# Checker invocations are captured with an explicit rc (the suite runs under
# `set -e`, so an expected non-zero exit must not abort this include).
# --- AC1: a fabricated ORCH_* token fails the checker (named) --------------------
# A fabricated knob token, assembled so this test file itself carries no literal
# ORCH_* token the checker's own `git grep scripts/` could later trip over.
_fab_tok="ORCH_$(printf 'LABEL')_FILTER"
_bad_orch="$(_abs337_doc "work/improvement-proposals/2026-bad-knob.md" \
    "Run the fence with ${_fab_tok}=foo to scope the sweep.")"
_rc=0
ORCH_DOCS_IDENTIFIER_CHECK=1 ORCH_RUN_LOG="$_ABS337_RUNLOG" \
    bash "$_ABS337_CHECK" "$_bad_orch" >"$_ABS337_SB/out1" 2>"$_ABS337_SB/err1" || _rc=$?
assert_eq "$_rc" "1" "ABS-337 AC1: a fabricated ORCH_*_FILTER token fails the checker"
assert_contains "$(cat "$_ABS337_SB/err1")" "$_fab_tok" \
    "ABS-337 AC1: the failure names the offending token"
assert_contains "$(cat "$_ABS337_SB/err1")" "2026-bad-knob.md" \
    "ABS-337 AC1: the failure names the offending file"

# --- AC2: a fabricated scripts/* path fails the checker --------------------------
_bad_path="$(_abs337_doc "docs/bad-path.md" \
    "Then run scripts/does-not-exist.sh to reconcile.")"
_rc=0
ORCH_DOCS_IDENTIFIER_CHECK=1 \
    bash "$_ABS337_CHECK" "$_bad_path" >"$_ABS337_SB/out2" 2>"$_ABS337_SB/err2" || _rc=$?
assert_eq "$_rc" "1" "ABS-337 AC2: a fabricated scripts/does-not-exist.sh path fails the checker"
assert_contains "$(cat "$_ABS337_SB/err2")" "does-not-exist.sh" \
    "ABS-337 AC2: the failure names the offending path"

# --- AC3: only REAL tokens -> passes --------------------------------------------
_good="$(_abs337_doc "work/improvement-proposals/2026-good.md" \
    "Set ORCH_START_LABEL and see scripts/orchestrator.sh for the loop.")"
_rc=0
ORCH_DOCS_IDENTIFIER_CHECK=1 \
    bash "$_ABS337_CHECK" "$_good" >"$_ABS337_SB/out3" 2>"$_ABS337_SB/err3" || _rc=$?
assert_eq "$_rc" "0" "ABS-337 AC3: a doc citing only real tokens (ORCH_START_LABEL, scripts/orchestrator.sh) passes"

# --- AC4: the gate defaults to 0 = off -> today's behaviour (no gate) -----------
# Same fabricated-token doc, but the knob unset/0: the checker is a clean no-op.
_rc=0
ORCH_DOCS_IDENTIFIER_CHECK=0 \
    bash "$_ABS337_CHECK" "$_bad_orch" >"$_ABS337_SB/out4" 2>"$_ABS337_SB/err4" || _rc=$?
assert_eq "$_rc" "0" "ABS-337 AC4: gate OFF (=0) is a no-op even on a fabricated token (today's behaviour)"

# --- AC5: a failure emits a runlog/audit line naming token(s) + file(s) ---------
# Grep the DOCS-IDENTIFIER-FAIL run-log line for the token and file (assert_contains
# is the suite's boolean helper; assert_true is not defined here).
_abs337_faillines="$(grep 'DOCS-IDENTIFIER-FAIL' "$_ABS337_RUNLOG" 2>/dev/null || true)"
assert_contains "$_abs337_faillines" "$_fab_tok" \
    "ABS-337 AC5: a failure writes a run-log audit line naming the token"
assert_contains "$_abs337_faillines" "2026-bad-knob.md" \
    "ABS-337 AC5: the run-log audit line names the offending file"

# --- AC6: a non-docs diff is untouched ------------------------------------------
# A file OUTSIDE work/improvement-proposals/ and docs/ carrying a fabricated
# token must be ignored (the checker only gates the two docs scopes).
mkdir -p "$_ABS337_SB/notdocs"
printf '%s referenced in a non-docs file\n' "$_fab_tok" > "$_ABS337_SB/notdocs/notes.txt"
_rc=0
ORCH_DOCS_IDENTIFIER_CHECK=1 \
    bash "$_ABS337_CHECK" "$_ABS337_SB/notdocs/notes.txt" >"$_ABS337_SB/out6" 2>"$_ABS337_SB/err6" || _rc=$?
assert_eq "$_rc" "0" "ABS-337 AC6: a non-docs file with a fabricated token is untouched by the checker"

rm -rf "$_ABS337_SB"
unset _ABS337_CHECK _ABS337_SB _ABS337_RUNLOG _bad_orch _bad_path _good _fab_tok _rc _abs337_faillines
