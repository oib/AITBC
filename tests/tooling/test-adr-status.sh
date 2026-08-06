#!/bin/bash
# =============================================================================
# Test: ADR status guard (ABS-213 / ADR-A-0020 decision (d))
# =============================================================================
# AC3 mechanical guard for the design-first story-routing path: an agent-authored
# ADR must ship `status: proposed` — acceptance is human-only (ADR-A-0004). The
# lesson is ADR-A-0018, which was authored `accepted` and had to be downgraded.
#
# This is a SUITE test (not a .claude hook) per ADR-A-0020(d): .claude/ is
# governor-generated (ABS-94), so the durable, version-controlled home for the
# guard is here. Auto-discovered by scripts/pre-release-check.sh (tests/test-*.sh).
#
# Asserts over every adrs/**/*.md except README.md:
#   1. a `status:` field exists and is in {proposed, accepted, superseded, deprecated}
#   2. status accepted|superseded  =>  non-empty accepted_by AND accepted_date
#      (the human-acceptance evidence a proposed ADR omits)
# Plus a self-check on synthetic fixtures so the guard itself is proven to bite.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-adr-status.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ADR_DIR="$REPO_ROOT/adrs"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "  ${GREEN}PASS${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC} $1"; FAIL=$((FAIL + 1)); }

# fm_block <file> — print the first frontmatter block (between the first two `---`).
fm_block() { awk '/^---[[:space:]]*$/ { c++; next } c == 1 { print } c >= 2 { exit }' "$1"; }

# fm_status <file> — the status token (field 2), inline `# comment` stripped.
fm_status() { fm_block "$1" | awk '$1 == "status:" { print $2; exit }'; }

# fm_value <file> <field> — value after `field:`, quotes/space trimmed ("" if absent/empty).
fm_value() {
    fm_block "$1" | awk -v k="$2:" '
        $1 == k { sub(/^[^:]*:[[:space:]]*/, ""); gsub(/^[ \t"]+|[ \t"]+$/, ""); print; exit }'
}

VALID_STATUS="proposed accepted superseded deprecated"

# check_adr <file> — echo an error string on violation, nothing when clean.
check_adr() {
    local f="$1" st ok by dt s
    st="$(fm_status "$f")"
    if [ -z "$st" ]; then echo "missing status: field"; return; fi
    ok=0; for s in $VALID_STATUS; do [ "$st" = "$s" ] && ok=1; done
    if [ "$ok" = 0 ]; then echo "invalid status '$st'"; return; fi
    if [ "$st" = "accepted" ] || [ "$st" = "superseded" ]; then
        by="$(fm_value "$f" accepted_by)"; dt="$(fm_value "$f" accepted_date)"
        [ -n "$by" ] || { echo "status '$st' without accepted_by"; return; }
        [ -n "$dt" ] || { echo "status '$st' without accepted_date"; return; }
    fi
}

echo -e "${CYAN}=== ADR status guard (ABS-213 / ADR-A-0020 d) ===${NC}\n"

# --- 1. every real ADR passes the guard --------------------------------------
echo -e "${CYAN}repo ADRs conform (status valid; accepted => human-acceptance fields)${NC}"
found=0
while IFS= read -r f; do
    found=$((found + 1))
    err="$(check_adr "$f")"
    if [ -z "$err" ]; then pass "$(basename "$f")"; else fail "$(basename "$f"): $err"; fi
done <<EOF
$(find "$ADR_DIR" -type f -name '*.md' ! -name 'README.md' | sort)
EOF
[ "$found" -gt 0 ] && pass "scanned $found ADR file(s)" || fail "no ADR files found under $ADR_DIR"

# --- 2. ADR-A-0020 (this ticket's decision record) is present + human-accepted --
# Operator accepted ADR-A-0020 on 2026-07-12 (human-only, ADR-A-0004): the story PR
# is the acceptance PR (ABS-212 closeout convention), so it carries status: accepted
# WITH the human-acceptance frontmatter (accepted_by + accepted_date) — the exact
# evidence a proposed ADR omits and this guard requires for accepted.
echo -e "\n${CYAN}ADR-A-0020 design-first routing is human-accepted with acceptance evidence${NC}"
adr20="$(find "$ADR_DIR" -type f -name 'ADR-A-0020-*.md' | head -1)"
if [ -n "$adr20" ] && [ "$(fm_status "$adr20")" = "accepted" ] \
    && [ -n "$(fm_value "$adr20" accepted_by)" ] && [ -n "$(fm_value "$adr20" accepted_date)" ]; then
    pass "ADR-A-0020 present, status: accepted with accepted_by + accepted_date"
else
    fail "ADR-A-0020 missing or not accepted-with-evidence (got '${adr20:+$(fm_status "$adr20")}')"
fi

# --- 3. self-check: the guard actually bites on the ADR-A-0018 error class ----
echo -e "\n${CYAN}guard bites synthetic violations (proves the check is live)${NC}"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# accepted without acceptance evidence == the ADR-A-0018 error class.
printf -- '---\nid: X\nstatus: accepted\n---\nbody\n' > "$tmp/bad-accepted.md"
[ -n "$(check_adr "$tmp/bad-accepted.md")" ] && pass "accepted-without-accepted_by is caught" \
    || fail "accepted-without-accepted_by slipped through"

# an invalid status value.
printf -- '---\nid: X\nstatus: draft\n---\nbody\n' > "$tmp/bad-status.md"
[ -n "$(check_adr "$tmp/bad-status.md")" ] && pass "invalid status value is caught" \
    || fail "invalid status value slipped through"

# a well-formed proposed ADR passes.
printf -- '---\nid: X\nstatus: proposed\n---\nbody\n' > "$tmp/good-proposed.md"
[ -z "$(check_adr "$tmp/good-proposed.md")" ] && pass "well-formed proposed ADR passes" \
    || fail "well-formed proposed ADR wrongly rejected"

# a well-formed accepted ADR (with evidence) passes.
printf -- '---\nid: X\nstatus: accepted\naccepted_by: "H"\naccepted_date: "2026-01-01"\n---\nbody\n' > "$tmp/good-accepted.md"
[ -z "$(check_adr "$tmp/good-accepted.md")" ] && pass "accepted-with-evidence passes" \
    || fail "accepted-with-evidence wrongly rejected"

echo ""
echo -e "${CYAN}=== ADR status guard: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} ===${NC}"
[ "$FAIL" -eq 0 ]
