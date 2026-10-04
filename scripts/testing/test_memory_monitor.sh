#!/bin/bash
# Dry-run proof for the memory-monitor.sh guards (Task 108 item 4):
#   - `systemctl list-units` can emit a "●" attention marker in column 1 —
#     it must never reach `systemctl show` as a unit name (journal showed
#     `Invalid unit name "●"`).
#   - `--value` properties can be "[not set]" or "infinity" — arithmetic on
#     them used to abort the run; a non-numeric limit is "no limit".
#
# Runs the real, unmodified script with a stubbed systemctl — nothing
# outside the temp dir is touched. Exits non-zero on any failed assertion.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SBX="$(mktemp -d /tmp/t108-memmon.XXXXXX)"
trap 'rm -rf "$SBX"' EXIT

FAILS=0
check() { # description command...
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"
    else
        echo "  FAIL: $desc"
        FAILS=$((FAILS + 1))
    fi
}

STUB_BIN="$SBX/bin"; MM_STATE="$SBX/state"; STUB_LOG="$SBX/systemctl.log"
mkdir -p "$STUB_BIN" "$MM_STATE"

cat > "$STUB_BIN/systemctl" <<'EOF'
#!/bin/bash
echo "systemctl $*" >> "$STUB_LOG"
cmd="${1:-}"; shift || true
case "$cmd" in
    list-units)
        # A flagged unit row leads with the "●" attention marker, like the
        # real journal did; the rest are plain running rows.
        cat <<UNITS
● aitbc-marked.service   loaded active running marked
aitbc-noset.service      loaded active running noset
aitbc-good.service       loaded active running good
aitbc-infinity.service   loaded active running inf
UNITS
        ;;
    show)
        unit=""; prop=""
        while [ $# -gt 0 ]; do
            case "$1" in
                -p)       prop="$2"; shift 2 ;;
                --value)  shift ;;
                *)        unit="$1"; shift ;;
            esac
        done
        case "$unit" in
            ●|"") echo "Failed to show unit: Invalid unit name \"$unit\"" >&2; exit 1 ;;
        esac
        f="$MM_STATE/$unit.$prop"
        if [ -f "$f" ]; then cat "$f"; else echo "[not set]"; fi
        ;;
    *)  exit 0 ;;
esac
EOF
chmod +x "$STUB_BIN/systemctl"
export STUB_LOG MM_STATE

# Property values: file per unit+prop; absent file => "[not set]" (stub default)
echo 268435456   > "$MM_STATE/aitbc-good.service.MemoryCurrent"     # 256 MB
echo 536870912   > "$MM_STATE/aitbc-good.service.MemoryMax"         # 512 MB -> 50%
echo 67108864    > "$MM_STATE/aitbc-marked.service.MemoryCurrent"   # 64 MB
echo infinity    > "$MM_STATE/aitbc-marked.service.MemoryMax"       # unbounded
echo 1048576     > "$MM_STATE/aitbc-infinity.service.MemoryCurrent" # 1 MB
echo infinity    > "$MM_STATE/aitbc-infinity.service.MemoryMax"
echo "[not set]" > "$MM_STATE/aitbc-infinity.service.MemoryLimit"
# aitbc-noset.service: no files -> every property "[not set]"

echo "== memory-monitor.sh — ● marker and [not set] guards =="
set +e
PATH="$STUB_BIN:$PATH" AITBC_MEMMON_LOG="$SBX/memory-monitor.log" \
    bash "$REPO_ROOT/scripts/monitoring/memory-monitor.sh" > "$SBX/run.out" 2>&1
rc=$?
set -e

check "script exits 0 despite [not set] values"    [ "$rc" -eq 0 ]
check "● never reaches systemctl show"             bash -c "! grep -q 'show.*●' '$STUB_LOG'"
check "no Invalid unit name in output"             bash -c "! grep -q 'Invalid unit name' '$SBX/run.out'"
check "marked unit still processed by name"        bash -c "grep -q 'aitbc-marked.service - 64MB (no limit)' '$SBX/run.out'"
check "all-[not set] unit reported SKIPPED"        bash -c "grep -q 'SKIPPED: aitbc-noset.service' '$SBX/run.out'"
check "numeric limit reports computed percent"     bash -c "grep -q 'aitbc-good.service - 256MB/512MB (50%)' '$SBX/run.out'"
check "infinity limit reported as no limit"        bash -c "grep -q 'aitbc-infinity.service - 1MB (no limit)' '$SBX/run.out'"

echo ""
if [ "$FAILS" -gt 0 ]; then
    echo "$FAILS CHECK(S) FAILED"
    exit 1
fi
echo "ALL CHECKS PASSED"
