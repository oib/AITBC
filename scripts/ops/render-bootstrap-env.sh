#!/bin/bash
# Render the PUBLIC bootstrap env served at /agent/bootstrap.env.
#
# The file is an allowlist-rendered, sanitized copy of the chain config —
# it is NOT /etc/aitbc/blockchain.env. The real file carries live key
# material on a hub (PROPOSER_KEY, VALIDATOR_KEYS) and must never be
# served (V23-58). Only the keys listed in ALLOWED below are copied from
# the live env; everything else comes from the committed open-island
# template.
#
# Usage (on the hub, as root):
#   bash /opt/aitbc/scripts/ops/render-bootstrap-env.sh
#
# Re-run after rotating FOLLOWER_API_KEY or changing chain endpoints, then
# `systemctl reload nginx` is not needed — the file is read per request.

set -euo pipefail

TEMPLATE="${TEMPLATE:-/opt/aitbc/examples/blockchain.env.open-island}"
SOURCE_ENV="${SOURCE_ENV:-/etc/aitbc/blockchain.env}"
OUT="${OUT:-/etc/aitbc/bootstrap.env}"

# Allowlist: the ONLY keys copied from the live env. FOLLOWER_API_KEY is
# deliberately public (V23-68): it reaches /coin-requests /register and
# /execute only.
ALLOWED="CHAIN_ID ISLAND_ID SUPPORTED_CHAINS FOLLOWER_API_KEY HUB_DISCOVERY_URL DEFAULT_PEER_RPC_URL GOSSIP_WEBSOCKET_URL"

[ -f "$TEMPLATE" ] || { echo "Missing template: $TEMPLATE" >&2; exit 1; }
[ -f "$SOURCE_ENV" ] || { echo "Missing source env: $SOURCE_ENV" >&2; exit 1; }

value_of() {
    grep -E "^${1}=" "$SOURCE_ENV" | tail -1 | cut -d= -f2- | tr -d "'\""
}

# Keys the template may already set; live allowlisted values override them.
STRIP_RE="^($(echo "$ALLOWED" | tr ' ' '|'))="

tmp="$(mktemp)"
{
    echo "# AITBC public bootstrap — sanitized follower configuration."
    echo "# Safe to serve publicly. Do NOT append node or hub key material here;"
    echo "# this file is world-readable at /agent/bootstrap.env."
    echo "# Rendered $(date -u +%Y-%m-%dT%H:%M:%SZ) from $TEMPLATE + allowlisted live values."
    echo
    grep -vE "$STRIP_RE" "$TEMPLATE"
    echo
    for key in $ALLOWED; do
        v="$(value_of "$key")"
        [ -n "$v" ] && echo "${key}=${v}"
    done
} > "$tmp"

install -m 0644 -o root -g root "$tmp" "$OUT"
rm -f "$tmp"

# Safety gate: refuse to publish if key material slipped in.
if grep -qE 'PROPOSER_KEY|VALIDATOR_KEYS|SECRET_KEY|COORDINATOR_API_KEY|BLOCKCHAIN_RPC_API_KEY(_PEERS)?=' "$OUT"; then
    echo "ERROR: $OUT contains private key material — removing." >&2
    rm -f "$OUT"
    exit 1
fi

echo "Wrote $OUT (public, sanitized). Verify:"
grep -cE '^[A-Z_]+=' "$OUT" | xargs echo "  keys:"
