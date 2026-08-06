#!/bin/bash
# =============================================================================
# Test: byte-stable per-ticket packet cache (ABS-176)
# =============================================================================
# build_packet caches the context packet byte-stable at $PACKETS_DIR/<ticket>.md
# so same-seat re-spawns (rework bounce / salvage / crash retry) resend a
# byte-identical prompt and hit the provider prompt cache instead of paying for
# the packet again. The cache is keyed on the tracker `updated` field plus the
# header coordinates (from/to/role/resume) and the content-shaping env inputs
# TRACKER_CMD + ORCH_PACKET_MAX_BYTES (ABS-202): a matching key reuses the file
# verbatim, and any ticket edit bumps `updated` and invalidates it.
#
# build_packet is pure given (tracker dump, header args), so this suite SOURCES
# scripts/orchestrator.sh (main is source-guarded) and calls build_packet
# directly with a stubbed `tracker` returning a controlled dump — deterministic,
# no real adapter, no wall-clock dependence.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-packet-cache.sh
# =============================================================================

set -euo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

# ABS-285: scrub ambient ORCH_* before driving the real seam/runner. A seat
# exports ~37 of them; a non-empty one leaks into the code under test and makes
# the result a function of the calling seat instead of the commit. Prefix-unset
# covers vars added later. This test sets every ORCH_* it needs, below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}
assert_ne() {
    local a="$1" b="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$a" != "$b" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected difference, both were '$a')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"; FAIL=$((FAIL + 1)); fi
}

# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

# Isolated packet dir + a stubbed tracker returning a controlled ticket dump.
TMP="$(mktemp -d /tmp/packet-cache-test-XXXXXX)"
PACKETS_DIR="$TMP/packets"   # override the sourced global
mkdir -p "$PACKETS_DIR"
trap 'rm -rf "$TMP"' EXIT

DUMP=""   # set per scenario; the stub echoes it verbatim
tracker() { case "${1:-}" in get) printf '%s\n' "$DUMP" ;; *) : ;; esac; }

make_dump() {  # <updated> <extra-body-line>
    printf -- '---\nid: ABS-999\ntype: ticket\ntitle: cache probe\nstatus: Ready for Development\nupdated: %s\n---\n\n## Goal\n\n%s\n' "$1" "$2"
}

echo -e "${CYAN}=== Packet cache (ABS-176) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}AC1 — two builds of an unchanged ticket are byte-identical${NC}"
# =============================================================================
DUMP="$(make_dump "2026-07-10T00:00:00Z" "cache the packet")"
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/p1.txt"
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/p2.txt"
if cmp -s "$TMP/p1.txt" "$TMP/p2.txt"; then r=identical; else r=differ; fi
assert_eq "$r" "identical" "consecutive builds of the same unchanged ticket are byte-identical"
assert_eq "$([ -f "$PACKETS_DIR/ABS-999.md" ] && echo yes || echo no)" "yes" "packet cached to \$PACKETS_DIR/<ticket>.md"

# =============================================================================
echo -e "\n${CYAN}AC2 — a changed \`updated\` invalidates the cache${NC}"
# =============================================================================
# Rebuild at T1, snapshot it, then bump `updated` + change the body -> the next
# packet must carry the new state and differ from the cached one.
DUMP="$(make_dump "2026-07-10T00:00:00Z" "OLD-BODY-MARKER")"
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/before.txt"
DUMP="$(make_dump "2026-07-10T09:00:00Z" "NEW-BODY-MARKER")"
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/after.txt"
assert_contains "$(cat "$TMP/after.txt")" "NEW-BODY-MARKER" "changed ticket -> packet carries the new state"
assert_not_contains "$(cat "$TMP/after.txt")" "OLD-BODY-MARKER" "changed ticket -> stale state is gone"
assert_ne "$(cat "$TMP/before.txt")" "$(cat "$TMP/after.txt")" "changed \`updated\` invalidates the cache (packets differ)"
assert_contains "$(cat "$PACKETS_DIR/ABS-999.meta")" "updated=2026-07-10T09:00:00Z" "cache meta records the new \`updated\` key"

# An unchanged `updated` from here reuses the cache verbatim (cache hit).
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/again.txt"
if cmp -s "$TMP/after.txt" "$TMP/again.txt"; then r=identical; else r=differ; fi
assert_eq "$r" "identical" "unchanged \`updated\` re-build reuses the cached packet verbatim"

# =============================================================================
echo -e "\n${CYAN}Cache key includes the header coordinates (no stale from_status)${NC}"
# =============================================================================
# A different spawn coordinate (from_status) must NOT reuse a prior seat's cached
# header — this protects the ABS-135 from_status guarantee.
DUMP="$(make_dump "2026-07-10T12:00:00Z" "coord probe")"
build_packet ABS-999 "In Progress" "In Review" be-developer "$TMP/coordA.txt"
build_packet ABS-999 "In Test" "Story Acceptance" qas "$TMP/coordB.txt"
assert_contains "$(cat "$TMP/coordB.txt")" "from_status: In Test" "different from/role rebuilds with the correct header"
assert_not_contains "$(cat "$TMP/coordB.txt")" "from_status: In Progress" "cache does not leak a prior seat's from_status"

# =============================================================================
echo -e "\n${CYAN}ABS-202 — a changed TRACKER_CMD invalidates the cache${NC}"
# =============================================================================
# TRACKER_CMD is written verbatim into the packet header. A cross-run change to
# the adapter path on an otherwise-unchanged ticket (same `updated`) must rebuild
# the packet with the new value, not serve one built under the old adapter.
DUMP="$(make_dump "2026-07-10T14:00:00Z" "tracker_cmd probe")"
TRACKER_CMD="/path/to/adapter-OLD.sh"
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/tcOld.txt"
TRACKER_CMD="/path/to/adapter-NEW.sh"
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/tcNew.txt"
assert_contains "$(cat "$TMP/tcNew.txt")" "tracker_cmd: /path/to/adapter-NEW.sh" "changed TRACKER_CMD -> packet carries the new adapter value"
assert_not_contains "$(cat "$TMP/tcNew.txt")" "adapter-OLD.sh" "changed TRACKER_CMD -> stale adapter value is gone"
assert_ne "$(cat "$TMP/tcOld.txt")" "$(cat "$TMP/tcNew.txt")" "changed TRACKER_CMD invalidates the cache (packets differ)"
assert_contains "$(cat "$PACKETS_DIR/ABS-999.meta")" "tracker_cmd=/path/to/adapter-NEW.sh" "cache meta folds TRACKER_CMD into the signature"

# =============================================================================
echo -e "\n${CYAN}ABS-202 — a changed ORCH_PACKET_MAX_BYTES invalidates the cache${NC}"
# =============================================================================
# ORCH_PACKET_MAX_BYTES drives the body-truncation budget. A cross-run change to
# the cap on an otherwise-unchanged ticket (same `updated`) must rebuild the
# packet under the new cap. Use a body large enough that a small cap truncates it
# while a large cap keeps it whole.
BIG_BODY="$(printf 'X%.0s' $(seq 1 2000))"
DUMP="$(make_dump "2026-07-10T15:00:00Z" "$BIG_BODY")"
ORCH_PACKET_MAX_BYTES=512
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/capSmall.txt"
ORCH_PACKET_MAX_BYTES=32768
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/capLarge.txt"
assert_contains "$(cat "$TMP/capSmall.txt")" "[packet truncated: over ORCH_PACKET_MAX_BYTES]" "small cap -> body is truncated"
assert_not_contains "$(cat "$TMP/capLarge.txt")" "[packet truncated: over ORCH_PACKET_MAX_BYTES]" "raised cap -> body is no longer truncated"
assert_ne "$(cat "$TMP/capSmall.txt")" "$(cat "$TMP/capLarge.txt")" "changed ORCH_PACKET_MAX_BYTES invalidates the cache (packets differ)"
assert_contains "$(cat "$PACKETS_DIR/ABS-999.meta")" "max_bytes=32768" "cache meta folds ORCH_PACKET_MAX_BYTES into the signature"
# Restore defaults for any later scenarios.
TRACKER_CMD="$REPO_ROOT/scripts/mock-tracker.sh"

# =============================================================================
echo -e "\n${CYAN}AC3 dedup — packet carries no role-def/commons workflow rules${NC}"
# =============================================================================
# The ABS-123 skills reminder lives verbatim in every role-def; it must not be
# duplicated in the packet. The runtime tracker_cmd + duty-note stay (ABS-180).
DUMP="$(make_dump "2026-07-10T13:00:00Z" "dedup probe")"
build_packet ABS-999 "Ready for Development" "In Progress" be-developer "$TMP/dedup.txt"
assert_not_contains "$(cat "$TMP/dedup.txt")" "invoke them via the Skill tool instead of rebuilding their content" "packet drops the role-def skills reminder (dedup)"
assert_contains "$(cat "$TMP/dedup.txt")" "tracker_cmd:" "packet keeps the runtime tracker_cmd (ABS-180)"
assert_contains "$(cat "$TMP/dedup.txt")" "note: use tracker_cmd above" "packet keeps the tracker-cmd duty-note (ABS-180)"

# =============================================================================
echo -e "\n${CYAN}ABS-238 — packet mode embeds the server-composed packet${NC}"
# =============================================================================
# A packet-capable adapter: `capabilities` lists "packet" and `packet <id>` returns
# a pre-composed body. build_packet must embed that body under === TICKET === with
# NO byte-cap truncation and NO separate === LATEST HANDOFF === section (the server
# packet already carries the handoff in slot 3).
PKT_BODY="$(printf -- '---\nid: ABS-777\ntype: ticket\nstatus: Ready for Development\nupdated: 2026-07-11T00:00:00Z\n---\n\n## Goal\n\ncomposed goal\n\n## Comments\n\n### 2026-07-11T00:00:00Z | kind: handoff | actor: be-developer\n\nSERVER-COMPOSED-HANDOFF\n')"
packet_tracker() {
    case "${1:-}" in
        capabilities) printf 'packet\nbrief\n' ;;
        packet)       printf '%s\n' "$PKT_BODY" ;;
        get)          printf '%s\n' "$PKT_BODY" ;;  # header resume/updated derivation
        *) : ;;
    esac
}
tracker() { packet_tracker "$@"; }
unset _ORCH_PKT_CAP_RESOLVED ORCH_PACKET_MODE
build_packet ABS-777 "Ready for Development" "In Progress" be-developer "$TMP/pkt.txt"
PKT_OUT="$(cat "$TMP/pkt.txt")"
assert_contains "$PKT_OUT" "SERVER-COMPOSED-HANDOFF" "packet-mode embeds the server packet body"
assert_contains "$PKT_OUT" "=== TICKET ===" "packet-mode keeps the === TICKET === marker"
assert_not_contains "$PKT_OUT" "=== LATEST HANDOFF ===" "packet-mode omits the separate handoff section"
assert_not_contains "$PKT_OUT" "[packet truncated" "packet-mode never truncates"
assert_contains "$(cat "$PACKETS_DIR/ABS-777.meta")" "pkt_mode=packet" "cache meta records packet mode"

# =============================================================================
echo -e "\n${CYAN}ABS-238 — the capability probe fires once per run${NC}"
# =============================================================================
: > "$TMP/capcalls"
tracker() {
    case "${1:-}" in
        capabilities) echo x >> "$TMP/capcalls"; printf 'packet\nbrief\n' ;;
        packet|get)   printf '%s\n' "$PKT_BODY" ;;
        *) : ;;
    esac
}
unset _ORCH_PKT_CAP_RESOLVED
build_packet ABS-701 "Ready for Development" "In Progress" be-developer "$TMP/p701.txt"
build_packet ABS-702 "Ready for Development" "In Progress" be-developer "$TMP/p702.txt"
build_packet ABS-703 "Ready for Development" "In Progress" be-developer "$TMP/p703.txt"
assert_eq "$(wc -l < "$TMP/capcalls" | tr -d ' ')" "1" "capabilities probe fires exactly once across 3 spawns"

# =============================================================================
echo -e "\n${CYAN}ABS-238 — adapter without a packet op falls back to full${NC}"
# =============================================================================
# No `capabilities` op (mock/jira) -> probe resolves to full, legacy dump is used.
DUMP="$(make_dump "2026-07-12T00:00:00Z" "fallback body")"
tracker() { case "${1:-}" in get) printf '%s\n' "$DUMP" ;; *) : ;; esac; }
unset _ORCH_PKT_CAP_RESOLVED ORCH_PACKET_MODE
build_packet ABS-808 "Ready for Development" "In Progress" be-developer "$TMP/fallback.txt"
assert_eq "${_ORCH_PKT_CAP_RESOLVED:-unset}" "full" "adapter without a packet op resolves to full"
assert_contains "$(cat "$TMP/fallback.txt")" "fallback body" "fallback uses the legacy get dump"
assert_contains "$(cat "$PACKETS_DIR/ABS-808.meta")" "pkt_mode=full" "meta records full mode on fallback"

# =============================================================================
echo -e "\n${CYAN}ABS-238 — ORCH_PACKET_MODE=full is byte-identical to the natural fallback${NC}"
# =============================================================================
# The kill-switch must reproduce the legacy path exactly. Compare (a) a NON-capable
# adapter (natural full fallback) against (b) a packet-CAPABLE adapter forced to
# full via ORCH_PACKET_MODE=full — same ticket state, headers normalized on the id.
DUMP="$(make_dump "2026-07-12T05:00:00Z" "parity body")"
# (a) natural fallback: adapter has no capabilities op.
tracker() { case "${1:-}" in get) printf '%s\n' "$DUMP" ;; *) : ;; esac; }
unset _ORCH_PKT_CAP_RESOLVED ORCH_PACKET_MODE
build_packet TCKA "Ready for Development" "In Progress" be-developer "$TMP/parityA.txt"
# (b) forced full on a packet-capable adapter; `packet` must NOT be consulted.
: > "$TMP/probeB"
tracker() {
    case "${1:-}" in
        capabilities) echo x >> "$TMP/probeB"; printf 'packet\n' ;;
        get)          printf '%s\n' "$DUMP" ;;
        packet)       printf 'WRONG-SHOULD-NOT-APPEAR\n' ;;
        *) : ;;
    esac
}
unset _ORCH_PKT_CAP_RESOLVED
ORCH_PACKET_MODE=full
build_packet TCKB "Ready for Development" "In Progress" be-developer "$TMP/parityB.txt"
unset ORCH_PACKET_MODE
sed 's/TCKA/TCK/' "$TMP/parityA.txt" > "$TMP/parityAn.txt"
sed 's/TCKB/TCK/' "$TMP/parityB.txt" > "$TMP/parityBn.txt"
if cmp -s "$TMP/parityAn.txt" "$TMP/parityBn.txt"; then r=identical; else r=differ; fi
assert_eq "$r" "identical" "ORCH_PACKET_MODE=full reproduces the legacy full-dump byte-for-byte"
assert_not_contains "$(cat "$TMP/parityB.txt")" "WRONG-SHOULD-NOT-APPEAR" "forced-full never calls the packet op"
assert_eq "$(wc -l < "$TMP/probeB" | tr -d ' ')" "0" "ORCH_PACKET_MODE=full skips the probe entirely"
# Restore the default mock tracker for any later scenarios.
tracker() { case "${1:-}" in get) printf '%s\n' "$DUMP" ;; *) : ;; esac; }

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
