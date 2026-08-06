#!/bin/bash
# =============================================================================
# Test: ADR id uniqueness guard (ABS-283)
# =============================================================================
# An ADR id is the CITATION KEY: agent defs, SOPs and tickets cite decisions by
# id. So an id that points at more than one decision makes every citation
# ambiguous. That is not hypothetical — it is the bug this guard closes:
# four parallel branches (ABS-254, ABS-255, ABS-256, ABS-258) each grabbed
# `ADR-A-0022` while `main` topped out at `0021`, and `docs/sop/ORCHESTRATOR_SOP.md`
# ended up citing "ADR-A-0022" for TWO different decisions.
#
# Seats pick "the next number" with no reservation mechanism, so the collision
# cannot be prevented here — but it CAN be made mechanically visible instead of
# silent. Asserts over every adrs/**/*.md except README.md:
#   1. no two ADR files share the same NUMBER in their FILENAME (name_id). Keying
#      on the filename — not the frontmatter `id:` — means a file WITHOUT
#      frontmatter can no longer silently occupy a number, the exact blind spot
#      that let the double-0028 ADR through (ABS-558/ABS-560).
#   2. every ADR HAS a frontmatter `id:` and it matches the id in the filename
#      (ADR-A-0023-foo.md must carry `id: ADR-A-0023` — a renumber that renames
#       the file but forgets the frontmatter, or vice versa, is caught; a missing
#       frontmatter id is itself a FAIL)
# Plus self-checks on synthetic fixtures so the guard itself is proven to bite.
#
# Auto-discovered by .github/workflows/tests.yml and scripts/pre-release-check.sh
# (both glob tests/test-*.sh) — no CI change needed.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-adr-id-uniqueness.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ADR_DIR="$REPO_ROOT/adrs"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "  ${GREEN}PASS${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC} $1"; FAIL=$((FAIL + 1)); }

# adr_files <dir> — every ADR under dir, README.md excluded, sorted.
adr_files() { find "$1" -type f -name '*.md' ! -name 'README.md' | sort; }

# fm_id <file> — the frontmatter `id:` value (first block only, quotes trimmed).
fm_id() {
    awk '/^---[[:space:]]*$/ { c++; next } c >= 2 { exit }
         c == 1 && $1 == "id:" { sub(/^[^:]*:[[:space:]]*/, ""); gsub(/^[ \t"]+|[ \t"]+$/, ""); print; exit }' "$1"
}

# name_id <file> — the id encoded in the filename (ADR-A-0023-foo.md -> ADR-A-0023).
name_id() { basename "$1" .md | sed -E 's/^(ADR-[A-Z]+-[0-9]+).*/\1/'; }

# check_names <dir> — echo one error line per file whose frontmatter id and
# filename id disagree (or whose frontmatter id is missing). Silent when clean.
check_names() {
    local f fid nid
    adr_files "$1" | while IFS= read -r f; do
        fid="$(fm_id "$f")"
        nid="$(name_id "$f")"
        if [ -z "$fid" ]; then
            echo "$(basename "$f"): missing frontmatter id:"
        elif [ "$fid" != "$nid" ]; then
            echo "$(basename "$f"): frontmatter id '$fid' != filename id '$nid'"
        fi
    done
}

# check_dupes <dir> — echo one error line per NUMBER (filename id) claimed by >1
# file. Keys on the FILENAME id (name_id), NOT the frontmatter id: a file WITHOUT
# frontmatter still carries a number in its name, so it can no longer silently
# occupy a number the way the frontmatterless double-0028 ADR did (ABS-558/ABS-560).
# Silent when clean.
check_dupes() {
    local f
    adr_files "$1" | while IFS= read -r f; do
        printf '%s\t%s\n' "$(name_id "$f")" "$(basename "$f")"
    done | awk -F'\t' '
        { count[$1]++; files[$1] = files[$1] " " $2 }
        END { for (id in count) if (count[id] > 1) printf "duplicate id %s claimed by:%s\n", id, files[id] }' \
        | sort
}

echo -e "${CYAN}=== ADR id uniqueness guard (ABS-283) ===${NC}\n"

# --- 1. the real ADR tree has no duplicate ids --------------------------------
echo -e "${CYAN}repo ADR ids are unique${NC}"
dupes="$(check_dupes "$ADR_DIR")"
if [ -z "$dupes" ]; then
    pass "no duplicate ADR id across $(adr_files "$ADR_DIR" | wc -l | tr -d ' ') ADR file(s)"
else
    while IFS= read -r d; do fail "$d"; done <<EOF
$dupes
EOF
fi

# --- 2. frontmatter id == filename id for every ADR ---------------------------
echo -e "\n${CYAN}frontmatter id matches filename id${NC}"
mismatches="$(check_names "$ADR_DIR")"
if [ -z "$mismatches" ]; then
    pass "every ADR's frontmatter id agrees with its filename"
else
    while IFS= read -r m; do fail "$m"; done <<EOF
$mismatches
EOF
fi

# --- 3. self-check: the guard actually bites (ABS-283 error class) ------------
echo -e "\n${CYAN}guard bites synthetic violations (proves the check is live)${NC}"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# clean fixture: distinct filename ids, frontmatter agrees -> both checks silent.
printf -- '---\nid: ADR-A-0001\nstatus: proposed\n---\nbody\n' > "$tmp/ADR-A-0001-alpha.md"
printf -- '---\nid: ADR-A-0002\nstatus: proposed\n---\nbody\n' > "$tmp/ADR-A-0002-beta.md"
printf -- '# not an ADR\n' > "$tmp/README.md"
[ -z "$(check_dupes "$tmp")" ] && pass "clean fixture: no false duplicate" \
    || fail "clean fixture wrongly reported a duplicate"
[ -z "$(check_names "$tmp")" ] && pass "clean fixture: no false id/filename mismatch" \
    || fail "clean fixture wrongly reported a mismatch"

# (a) two files sharing one FILENAME number == the ABS-283 collision class.
printf -- '---\nid: ADR-A-0002\nstatus: proposed\n---\nbody\n' > "$tmp/ADR-A-0002-beta-dup.md"
[ -n "$(check_dupes "$tmp")" ] && pass "duplicate filename number across two files is caught" \
    || fail "duplicate filename number slipped through"
rm -f "$tmp/ADR-A-0002-beta-dup.md"

# (b) frontmatter id disagrees with filename id (0003 in name, 0002 in frontmatter)
# == a half-executed renumber, exactly what ABS-254/ABS-256 left behind.
printf -- '---\nid: ADR-A-0002\nstatus: proposed\n---\nbody\n' > "$tmp/ADR-A-0003-gamma.md"
[ -n "$(check_names "$tmp")" ] && pass "frontmatter/filename id mismatch is caught" \
    || fail "id/filename mismatch slipped through"
rm -f "$tmp/ADR-A-0003-gamma.md"

# (c) a missing frontmatter id is itself a FAIL, not a silent unique (ABS-560 AC2).
printf -- '---\nstatus: proposed\n---\nbody\n' > "$tmp/ADR-A-0004-delta.md"
[ -n "$(check_names "$tmp")" ] && pass "missing frontmatter id is caught" \
    || fail "missing frontmatter id slipped through"
rm -f "$tmp/ADR-A-0004-delta.md"

# (d) THE ABS-558 incident, reproduced: two files claim the SAME number and one
# has NO frontmatter. The old dupe check keyed on the frontmatter id and skipped
# the frontmatterless file, so the double-0028 went silent. Now it must be caught
# AND name BOTH files (ABS-560 AC3).
printf -- '---\nid: ADR-A-0028\nstatus: proposed\n---\nbody\n' > "$tmp/ADR-A-0028-eventbus-a.md"
printf -- 'body without any frontmatter\n' > "$tmp/ADR-A-0028-eventbus-b.md"
dup28="$(check_dupes "$tmp")"
if printf '%s' "$dup28" | grep -q 'ADR-A-0028-eventbus-a.md' \
    && printf '%s' "$dup28" | grep -q 'ADR-A-0028-eventbus-b.md'; then
    pass "duplicate number with a frontmatterless file is caught and names both files"
else
    fail "frontmatterless duplicate slipped through or did not name both files: $dup28"
fi
rm -f "$tmp/ADR-A-0028-eventbus-a.md" "$tmp/ADR-A-0028-eventbus-b.md"

echo ""
echo -e "${CYAN}=== ADR id uniqueness guard: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} ===${NC}"
[ "$FAIL" -eq 0 ]
