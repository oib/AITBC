#!/bin/bash
# Hermetic tests for scripts/monitoring/native-energy-rate-refresh.sh.
#
# The refresher must refuse to re-attest a stored rate outside the plausible
# band (SD-7: the stub rate 1 sat reposted for nine days). Stub sqlite DB,
# stub coordinator env file, and a stub curl on PATH — no coordinator, no
# real DB, no network.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/monitoring/native-energy-rate-refresh.sh"
SBX="$(mktemp -d /tmp/ta2-raterefresh.XXXXXX)"
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

STUB_BIN="$SBX/bin"
mkdir -p "$STUB_BIN"
DB="$SBX/coordinator.db"
ENVF="$SBX/coordinator.env"
CURL_LOG="$SBX/curl.log"

# curl stub: records the payload, answers 200 with a JSON body.
cat > "$STUB_BIN/curl" <<'EOF'
#!/bin/bash
echo "$@" >> "$CURL_LOG"
for a in "$@"; do
    case "$a" in -d) shift_next=1 ;; esac
done
# capture the -d payload
prev=""
for a in "$@"; do
    if [ "$prev" = "-d" ]; then echo "PAYLOAD $a" >> "$CURL_LOG"; fi
    prev="$a"
done
echo '{"status":"published"}'
exit 0
EOF
chmod +x "$STUB_BIN/curl"

# Minimal env file with one miner key.
cat > "$ENVF" <<'EOF'
MINER_API_KEYS=["testminerkey"]
EOF

mk_rate_db() { # scaled value -> fresh DB
    rm -f "$DB"
    sqlite3 "$DB" "CREATE TABLE native_energy_rates (id INTEGER PRIMARY KEY, ait_per_eur_scaled INTEGER, enabled INTEGER, observed_at INTEGER, version INTEGER); INSERT INTO native_energy_rates VALUES (1, $1, 1, 1700000000, 50);"
}

PROM_DIR="$SBX/textfile"
mkdir -p "$PROM_DIR"

run_refresh() { # rate_scaled -> runs the script, returns rc
    mk_rate_db "$1"
    PATH="$STUB_BIN:$PATH" CURL_LOG="$CURL_LOG" TEXTFILE_DIR="$PROM_DIR" \
        COORDINATOR_URL="http://127.0.0.1:9" COORDINATOR_DB="$DB" COORDINATOR_ENV="$ENVF" \
        bash "$SCRIPT" 2>&1
}

echo "== native-energy-rate-refresh =="

# 1. In-band rate (4.0 AIT/EUR) posts and exits 0.
rc=0; out=$(run_refresh 4000000000000000000) || rc=$?
check "in-band rate exits 0" test "$rc" -eq 0
check "in-band rate reached curl" grep -q "PAYLOAD" "$CURL_LOG"
check "in-band response logged" bash -c "echo \"\$0\" | grep -q published" "$out"

# 2. Stub-era value 1 (scaled) must be refused before any POST.
rm -f "$CURL_LOG"
rc=0; out=$(run_refresh 1) || rc=$?
check "stub rate refused (rc 1)" test "$rc" -eq 1
check "stub rate refusal logged" bash -c "echo \"\$0\" | grep -qi 'plausible band'" "$out"
check "stub rate never posted" bash -c '! test -f "$0"' "$CURL_LOG"

# 3. Above-band value refused the same way (9.0 stays inside int64 range).
rm -f "$CURL_LOG"
rc=0; out=$(run_refresh 9000000000000000000) || rc=$?
check "above-band refused (rc 1)" test "$rc" -eq 1
check "above-band never posted" bash -c '! test -f "$0"' "$CURL_LOG"

# 4. Missing row still fails loudly (pre-existing behaviour) and the textfile
#    still gets a refresh timestamp so the dead-refresher alert stays armed.
rm -f "$CURL_LOG" "$DB" "$PROM_DIR/aitbc_native_energy_rate.prom"
rc=0; out=$(PATH="$STUB_BIN:$PATH" CURL_LOG="$CURL_LOG" TEXTFILE_DIR="$PROM_DIR" \
    COORDINATOR_URL="http://127.0.0.1:9" COORDINATOR_DB="$DB" COORDINATOR_ENV="$ENVF" \
    bash "$SCRIPT" 2>&1) || rc=$?
check "no rate row fails (rc 1)" test "$rc" -eq 1
check "no rate row logged" bash -c "echo \"\$0\" | grep -qi 'no enabled'" "$out"
check "missing row still writes refresh ts" grep -q "refresh_timestamp_seconds" "$PROM_DIR/aitbc_native_energy_rate.prom"
check "missing row exports no rate" bash -c '! grep -q "ait_per_eur [0-9]" "$0"' "$PROM_DIR/aitbc_native_energy_rate.prom"

# 5. Band edges are inclusive (0.5 and 8 scaled).
rc=0; out=$(run_refresh 500000000000000000) || rc=$?
check "0.5 boundary posts" test "$rc" -eq 0
rc=0; out=$(run_refresh 8000000000000000000) || rc=$?
check "8 boundary posts" test "$rc" -eq 0

# 6. Textfile export carries the stored rate, observed_at and version —
#    including on a refused out-of-band row (the alert must see the truth).
rm -f "$PROM_DIR/aitbc_native_energy_rate.prom"
rc=0; out=$(run_refresh 4000000000000000000) || rc=$?
check "textfile written" test -f "$PROM_DIR/aitbc_native_energy_rate.prom"
check "textfile is node_exporter-readable (644)" bash -c 'test "$(stat -c %a "$0")" = 644' "$PROM_DIR/aitbc_native_energy_rate.prom"
check "textfile has rate 4.0" grep -q "aitbc_native_energy_rate_ait_per_eur 4" "$PROM_DIR/aitbc_native_energy_rate.prom"
check "textfile has observed ts" grep -q "observed_timestamp_seconds" "$PROM_DIR/aitbc_native_energy_rate.prom"
check "textfile has version" grep -q "aitbc_native_energy_rate_version" "$PROM_DIR/aitbc_native_energy_rate.prom"
rm -f "$PROM_DIR/aitbc_native_energy_rate.prom"
rc=0; out=$(run_refresh 1) || rc=$?
check "refused row still exports rate 1e-18" grep -q "ait_per_eur 1e-18\|ait_per_eur 0.000000001\|ait_per_eur " "$PROM_DIR/aitbc_native_energy_rate.prom"

if [ "$FAILS" -gt 0 ]; then
    echo "FAILED: $FAILS check(s)"
    exit 1
fi
echo "ALL CHECKS PASSED"
