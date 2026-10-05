#!/bin/bash
# Re-attest the native AIT/EUR energy rate so GPU-rental quotes stay fresh.
#
# The coordinator's NativeEnergyOracle refuses quotes when the rate's
# observed_at is older than ENERGY_MAX_RATE_AGE_SECONDS (86400s on hub).
# This job republishes the CURRENT operator-set value from
# coordinator.db:native_energy_rates — it refreshes observed_at only and
# never invents a price. If no rate row exists it fails loudly instead of
# picking a number.
#
# Env overrides: COORDINATOR_URL, COORDINATOR_DB, COORDINATOR_ENV,
# ENERGY_RATE_MIN_AIT_PER_EUR / ENERGY_RATE_MAX_AIT_PER_EUR (plausibility
# band, defaults 0.5 / 8 — must match the coordinator's POST bound; the max
# stays under ~9.22 because the scaled column is int64), TEXTFILE_DIR.
# Exit 0 = refreshed, 1 = failed (no rate row / out-of-band rate / bad key / coordinator down).
#
# Every run also writes <TEXTFILE_DIR>/aitbc_native_energy_rate.prom for the
# node_exporter textfile collector — including refused and missing rows — so
# Prometheus sees the real stored rate even when this script refuses to
# re-attest it (SD-7: the stub value sat unreported for nine days):
#   aitbc_native_energy_rate_ait_per_eur                 stored rate (AIT/EUR)
#   aitbc_native_energy_rate_observed_timestamp_seconds  observed_at column
#   aitbc_native_energy_rate_version                     row version
#   aitbc_native_energy_rate_refresh_timestamp_seconds   this run's time
# A write failure is logged and never aborts the refresh.

set -euo pipefail

TAG="aitbc-energy-rate"
COORDINATOR_URL="${COORDINATOR_URL:-http://127.0.0.1:8203}"
COORDINATOR_DB="${COORDINATOR_DB:-/var/lib/aitbc/data/coordinator.db}"
COORDINATOR_ENV="${COORDINATOR_ENV:-/etc/aitbc/aitbc-coordinator-api.env}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/var/lib/prometheus/node-exporter}"

log() { logger -t "$TAG" -p "user.$1" -- "$2"; echo "[$1] $2"; }

write_textfile() { # $1=rate_scaled $2=observed_at $3=version (all may be empty)
    local tmp
    tmp=$(mktemp "$TEXTFILE_DIR/.aitbc_native_energy_rate.XXXXXX.prom") || {
        log warning "cannot create textfile in $TEXTFILE_DIR — metrics not exported"
        return 0
    }
    {
        echo "# HELP aitbc_native_energy_rate_refresh_timestamp_seconds When the refresher last ran."
        echo "# TYPE aitbc_native_energy_rate_refresh_timestamp_seconds gauge"
        echo "aitbc_native_energy_rate_refresh_timestamp_seconds $(date +%s)"
        if [ -n "${1:-}" ]; then
            echo "# HELP aitbc_native_energy_rate_ait_per_eur Stored native AIT/EUR rate."
            echo "# TYPE aitbc_native_energy_rate_ait_per_eur gauge"
            awk -v v="$1" 'BEGIN { printf "aitbc_native_energy_rate_ait_per_eur %.9g\n", v / 1e18 }'
            echo "# HELP aitbc_native_energy_rate_observed_timestamp_seconds observed_at of the stored rate row."
            echo "# TYPE aitbc_native_energy_rate_observed_timestamp_seconds gauge"
            echo "aitbc_native_energy_rate_observed_timestamp_seconds $2"
            echo "# HELP aitbc_native_energy_rate_version Version column of the stored rate row."
            echo "# TYPE aitbc_native_energy_rate_version gauge"
            echo "aitbc_native_energy_rate_version $3"
        fi
    } > "$tmp"
    mv "$tmp" "$TEXTFILE_DIR/aitbc_native_energy_rate.prom" || \
        log warning "cannot install textfile in $TEXTFILE_DIR — metrics not exported"
}

ROW=$(sqlite3 -separator '|' "$COORDINATOR_DB" \
    "SELECT ait_per_eur_scaled, observed_at, version FROM native_energy_rates WHERE id=1 AND enabled=1;" \
    2>/dev/null || true)
RATE_SCALED="${ROW%%|*}"
OBSERVED_AT="$(echo "$ROW" | cut -d'|' -f2)"
RATE_VERSION="$(echo "$ROW" | cut -d'|' -f3)"
write_textfile "$RATE_SCALED" "$OBSERVED_AT" "$RATE_VERSION"
if [ -z "$RATE_SCALED" ]; then
    log err "no enabled native_energy_rates row in $COORDINATOR_DB — set the rate first"
    exit 1
fi

# SD-7 guard: refuse to re-attest a stored value outside the plausible band —
# the stub rate sat reposted for nine days because nothing checked it. The
# coordinator enforces the same band on POST, but checking here first fails
# with a clearer journal line and never touches the endpoint.
MIN_RATE="${ENERGY_RATE_MIN_AIT_PER_EUR:-0.5}"
MAX_RATE="${ENERGY_RATE_MAX_AIT_PER_EUR:-8}"
if ! awk -v v="$RATE_SCALED" -v lo="$MIN_RATE" -v hi="$MAX_RATE" \
    'BEGIN { exit !(v / 1e18 >= lo && v / 1e18 <= hi) }'; then
    log err "stored rate $RATE_SCALED (scaled) is outside the plausible band [$MIN_RATE, $MAX_RATE] AIT/EUR — refusing to re-attest; fix the native_energy_rates row first"
    exit 1
fi

# First entry of the JSON-array MINER_API_KEYS in the coordinator env file.
API_KEY=$(python3 -c '
import json, re, sys
for line in open(sys.argv[1]):
    m = re.match(r"MINER_API_KEYS\s*=\s*(.+)", line.strip())
    if not m:
        continue
    raw = m.group(1).strip().strip("\x27\"")
    try:
        keys = json.loads(raw)
    except json.JSONDecodeError:
        keys = [k.strip() for k in raw.strip("[]").split(",") if k.strip()]
    if keys:
        print(keys[0])
        break
' "$COORDINATOR_ENV" 2>/dev/null || true)
if [ -z "$API_KEY" ]; then
    log err "no MINER_API_KEYS entry parsed from $COORDINATOR_ENV"
    exit 1
fi

resp=$(curl -sf -X POST "$COORDINATOR_URL/v1/market/native-energy/rate" \
    -H "X-Api-Key: $API_KEY" -H "X-Miner-ID: rate-refresh" \
    -H "Content-Type: application/json" \
    -d "{\"ait_per_eur_scaled\": $RATE_SCALED}") || {
    log err "rate refresh POST failed (coordinator down or key rejected)"
    exit 1
}
log info "native energy rate re-attested: $resp"
