#!/usr/bin/env bash
# =============================================================================
# ABS-554 — extract_usage_note reads the SESSION totals (.usage.*), never the
#           last .usage.iterations[] entry
# =============================================================================
# Origin (v3-pilot #5, 2026-07-25): every SPAWN-USAGE line understated token
# volume by 20-65x. The parser read the cost/usage fields out of the Claude Code
# result JSON with `sed -n 's/.*"input_tokens"...\1/p'`. The leading `.*` is
# GREEDY, so the match landed on the LAST occurrence in the flattened JSON —
# which sits inside `.usage.iterations[]` (the usage of the FINAL assistant
# message) rather than in the session sum `.usage.*`. Affected: input_tokens,
# cache_read_input_tokens, cache_creation_input_tokens, output_tokens.
# total_cost_usd was correct only because it occurs exactly once.
#
# Reference case, packets/PILOT-34.20260725T135054Z.33876.txt.out.33876 (91 turns):
#   .usage.*            (TRUTH)  input=6335 cache_read=11534075 cache_create=163881 output=53915
#   .usage.iterations[-1] (LOGGED) input=2    cache_read=177377    cache_create=201    output=390
#   .total_cost_usd = 8.788496500000003
# -> factor 65 on cache_read, the field that carries the real input volume.
#
# The fix parses STRUCTURALLY (jq, exact paths) instead of guessing by text
# position, because JSON does not guarantee key order — "first match instead of
# last" would only be a luckier heuristic. The fail-soft contract is unchanged:
# missing fields degrade to empty values, the line always appears, exit 0.
#
# This suite also carries the PRE-FIX implementation verbatim (extract_usage_note
# __legacy_greedy below) and asserts that it produces the WRONG numbers on the
# same fixture — so the regression proof stays re-runnable instead of living in a
# handoff note.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/test-usage-note-parse.sh
# =============================================================================
set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

# ABS-285: scrub ambient ORCH_* so the result is a function of the commit, not of
# the seat that ran the suite. Also drop backend/tracker env — this suite sources
# orchestrator.sh and must never reach a live backend.
unset "${!ORCH_@}"
unset BACKEND_URL BACKEND_TOKEN TRACKER_CMD 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/usage-note-parse-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label"
        echo -e "  ${YELLOW}    expected:${NC} $expected"
        echo -e "  ${YELLOW}    actual:  ${NC} $actual"; FAIL=$((FAIL + 1)); fi
}
assert_ne() {
    local actual="$1" unexpected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" != "$unexpected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $unexpected)"; FAIL=$((FAIL + 1)); fi
}

# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

# The PRE-ABS-554 implementation, verbatim — kept only to prove the defect.
__legacy_greedy() {
    local flat t_in c_read c_create t_out cost
    flat="$(printf '%s' "$1" | tr '\n' ' ')"
    t_in="$(printf '%s' "$flat"     | sed -n 's/.*"input_tokens"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
    c_read="$(printf '%s' "$flat"   | sed -n 's/.*"cache_read_input_tokens"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
    c_create="$(printf '%s' "$flat" | sed -n 's/.*"cache_creation_input_tokens"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
    t_out="$(printf '%s' "$flat"    | sed -n 's/.*"output_tokens"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
    cost="$(printf '%s' "$flat"     | sed -n 's/.*"total_cost_usd"[[:space:]]*:[[:space:]]*\([0-9.][0-9.]*\).*/\1/p' | head -1)"
    printf 'tokens_in=%s cache_read=%s cache_create=%s tokens_out=%s cost_usd=%s' \
        "$t_in" "$c_read" "$c_create" "$t_out" "$cost"
}

note_field() {  # <note> <key> -> value
    printf '%s' "$1" | tr ' ' '\n' | sed -n "s/^$2=//p"
}

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
# 1. The real reference result JSON (PILOT-34), reduced to the fields that matter
#    but with the ORIGINAL key order and the ORIGINAL numbers.
REAL_JSON='{"type":"result","subtype":"error_max_turns","is_error":true,"num_turns":91,
"session_id":"b4dc4656-ddc6-43b0-b833-fc68ed07d794","total_cost_usd":8.788496500000003,
"usage":{"input_tokens":6335,"cache_creation_input_tokens":163881,"cache_read_input_tokens":11534075,
"output_tokens":53915,"server_tool_use":{"web_search_requests":0},"service_tier":"standard",
"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":163881},
"iterations":[{"input_tokens":2,"output_tokens":390,"cache_read_input_tokens":177377,
"cache_creation_input_tokens":201,"cache_creation":{"ephemeral_5m_input_tokens":0,
"ephemeral_1h_input_tokens":201},"type":"message"}]},
"modelUsage":{"claude-opus-4-8":{"inputTokens":6335,"outputTokens":53915,
"cacheReadInputTokens":11534075,"cacheCreationInputTokens":163881,"costUSD":8.785397500000002}}}'
REAL_EXPECTED='tokens_in=6335 cache_read=11534075 cache_create=163881 tokens_out=53915 cost_usd=8.788496500000003'

# 2. Short spawn: session usage, no iterations[] at all (the common case).
NO_ITER_JSON='{"type":"result","total_cost_usd":0.7123,"usage":{"input_tokens":2,
"cache_creation_input_tokens":18000,"cache_read_input_tokens":250000,"output_tokens":1234}}'

# 3. iterations[] BEFORE the session fields — JSON guarantees no key order.
ORDER_JSON='{"total_cost_usd":1.25,"usage":{"iterations":[{"input_tokens":1,
"cache_read_input_tokens":99,"cache_creation_input_tokens":2,"output_tokens":3,"type":"message"}],
"input_tokens":500,"cache_creation_input_tokens":600,"cache_read_input_tokens":700000,
"output_tokens":800}}'

# =============================================================================
echo -e "${CYAN}=== ABS-554 extract_usage_note — session totals, not iterations[] ===${NC}\n"
# =============================================================================
echo -e "${CYAN}CORE: the real PILOT-34 result JSON${NC}"
note="$(extract_usage_note "$REAL_JSON")"
assert_eq "$note" "$REAL_EXPECTED" \
    "session sums surfaced (input/cache_read/cache_create/output from .usage.*)"

# The regression proof: the PRE-FIX parser on the SAME fixture reports the last
# iteration's usage. This is what shipped for two releases.
legacy="$(__legacy_greedy "$REAL_JSON")"
assert_eq "$legacy" \
    'tokens_in=2 cache_read=177377 cache_create=201 tokens_out=390 cost_usd=8.788496500000003' \
    "PRE-FIX parser reproduces the defect on the same fixture (greedy = last match)"
assert_ne "$legacy" "$REAL_EXPECTED" \
    "=> the core assertion above is RED against the pre-ABS-554 implementation"

# =============================================================================
echo -e "\n${CYAN}total_cost_usd is unchanged (it was the only correct field before)${NC}"
# =============================================================================
assert_eq "$(note_field "$note" cost_usd)" "8.788496500000003" \
    "cost_usd read verbatim, full float precision preserved"
assert_eq "$(note_field "$legacy" cost_usd)" "$(note_field "$note" cost_usd)" \
    "cost_usd identical before and after the fix (single occurrence in the JSON)"

# =============================================================================
echo -e "\n${CYAN}AC4 plausibility: logged tokens must explain total_cost_usd${NC}"
# =============================================================================
# Price-anchored sanity check on the REAL fixture, whose serving model is known
# from .modelUsage (claude-opus-4-8). Published rates per 1M tokens (Anthropic
# model catalog, 2026-06-24): input $5.00, output $25.00; cache read = 0.1x input
# = $0.50, cache write = 1.25x input (5m TTL) = $6.25 (2x = $10.00 for the 1h
# TTL this spawn actually used, which lands even closer). Tolerance 25% absorbs
# the TTL ambiguity and the small side-model share (a haiku sub-agent contributed
# $0.003 here). This is a TEST assert on a fixture, NOT a runtime gate in the
# runner — the runner must never fail a spawn over an arithmetic sanity check.
implied_cost() {  # <t_in> <c_read> <c_create> <t_out> -> USD
    awk -v i="$1" -v cr="$2" -v cc="$3" -v o="$4" \
        'BEGIN{ printf "%.6f", (i*5.00 + cr*0.50 + cc*6.25 + o*25.00) / 1000000 }'
}
within() {  # <actual> <reference> <tolerance-fraction>
    awk -v a="$1" -v b="$2" -v t="$3" \
        'BEGIN{ if (b == 0) exit 1; d = (a-b)/b; if (d < 0) d = -d; exit (d <= t) ? 0 : 1 }'
}
cost="$(note_field "$note" cost_usd)"
fixed="$(implied_cost "$(note_field "$note" tokens_in)" "$(note_field "$note" cache_read)" \
                      "$(note_field "$note" cache_create)" "$(note_field "$note" tokens_out)")"
broken="$(implied_cost "$(note_field "$legacy" tokens_in)" "$(note_field "$legacy" cache_read)" \
                       "$(note_field "$legacy" cache_create)" "$(note_field "$legacy" tokens_out)")"
TOTAL=$((TOTAL + 1))
if within "$fixed" "$cost" 0.25; then
    echo -e "  ${GREEN}PASS${NC} fixed tokens imply \$$fixed vs logged \$$cost (within 25%)"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} fixed tokens imply \$$fixed but cost_usd is \$$cost (>25% apart)"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))
if within "$broken" "$cost" 0.25; then
    echo -e "  ${RED}FAIL${NC} pre-fix tokens (\$$broken) pass the plausibility band — band is useless"
    FAIL=$((FAIL + 1))
else
    echo -e "  ${GREEN}PASS${NC} pre-fix tokens imply only \$$broken vs \$$cost — band catches the defect"
    PASS=$((PASS + 1))
fi

# =============================================================================
echo -e "\n${CYAN}Short spawn: .usage present, no iterations[]${NC}"
# =============================================================================
assert_eq "$(extract_usage_note "$NO_ITER_JSON")" \
    "tokens_in=2 cache_read=250000 cache_create=18000 tokens_out=1234 cost_usd=0.7123" \
    "all five fields read from .usage.* (ABS-165 cache fields still surfaced)"

# =============================================================================
echo -e "\n${CYAN}Key order independence (iterations[] BEFORE the session fields)${NC}"
# =============================================================================
assert_eq "$(extract_usage_note "$ORDER_JSON")" \
    "tokens_in=500 cache_read=700000 cache_create=600 tokens_out=800 cost_usd=1.25" \
    "path-addressed, so key order is irrelevant (a first-match heuristic would fail here)"

# =============================================================================
echo -e "\n${CYAN}Preamble before the result JSON${NC}"
# =============================================================================
PREAMBLE_JSON="spawn-claude: NOTICE something on stdout
warning: another line
$NO_ITER_JSON"
assert_eq "$(extract_usage_note "$PREAMBLE_JSON")" \
    "tokens_in=2 cache_read=250000 cache_create=18000 tokens_out=1234 cost_usd=0.7123" \
    "re-anchored at the first '{' — preamble does not break the parse"

# =============================================================================
echo -e "\n${CYAN}Fail-soft contract: the line always appears, exit 0${NC}"
# =============================================================================
for label_input in \
    "empty stdout|" \
    "truncated JSON|{\"type\":\"result\",\"usage\":{\"input_tok" \
    "not JSON at all|## Handoff — kind: handoff, status: done (stub spawn stdout)" \
    "JSON without usage|{\"result\":\"ok\"}"
do
    label="${label_input%%|*}"; input="${label_input#*|}"
    rc=0; out="$(extract_usage_note "$input")" || rc=$?
    assert_eq "$out" "tokens_in= cache_read= cache_create= tokens_out= cost_usd=" \
        "$label -> empty fields, line still shaped"
    assert_eq "$rc" "0" "$label -> exit 0 (pipeline never breaks)"
done

# =============================================================================
echo -e "\n${CYAN}Fallback path: jq unavailable/broken${NC}"
# =============================================================================
# A jq shim that always fails forces the text fallback (documented in
# scripts/orchestrator.sh as a positional heuristic, weaker than the jq path).
mkdir -p "$TEST_DIR/bin"
printf '#!/bin/sh\nexit 1\n' > "$TEST_DIR/bin/jq"
chmod +x "$TEST_DIR/bin/jq"
saved_path="$PATH"
PATH="$TEST_DIR/bin:$PATH"
fb_real="$(extract_usage_note "$REAL_JSON")"
fb_broken="$(extract_usage_note '{"type":"result","usage":{"input_tok')"
PATH="$saved_path"
assert_eq "$fb_real" "$REAL_EXPECTED" \
    "no usable jq -> FIRST-match text fallback still yields the session sums on real key order"
assert_eq "$fb_broken" "tokens_in= cache_read= cache_create= tokens_out= cost_usd=" \
    "no usable jq + broken JSON -> empty fields, no crash"

# =============================================================================
echo ""
echo -e "${CYAN}=== Results: $PASS/$TOTAL passed ===${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}$FAIL test(s) failed${NC}"
    exit 1
fi
echo -e "${GREEN}All tests passed${NC}"
exit 0
