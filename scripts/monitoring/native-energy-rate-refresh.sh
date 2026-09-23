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
# Env overrides: COORDINATOR_URL, COORDINATOR_DB, COORDINATOR_ENV.
# Exit 0 = refreshed, 1 = failed (no rate row / bad key / coordinator down).

set -euo pipefail

TAG="aitbc-energy-rate"
COORDINATOR_URL="${COORDINATOR_URL:-http://127.0.0.1:8203}"
COORDINATOR_DB="${COORDINATOR_DB:-/var/lib/aitbc/data/coordinator.db}"
COORDINATOR_ENV="${COORDINATOR_ENV:-/etc/aitbc/aitbc-coordinator-api.env}"

log() { logger -t "$TAG" -p "user.$1" -- "$2"; echo "[$1] $2"; }

RATE_SCALED=$(sqlite3 "$COORDINATOR_DB" \
    "SELECT ait_per_eur_scaled FROM native_energy_rates WHERE id=1 AND enabled=1;" \
    2>/dev/null || true)
if [ -z "$RATE_SCALED" ]; then
    log err "no enabled native_energy_rates row in $COORDINATOR_DB — set the rate first"
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
