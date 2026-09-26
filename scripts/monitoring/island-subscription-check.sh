#!/bin/bash
# Check that this node's island IPFS subscription is still active by calling
# the coordinator's swarm-key endpoint -- the same gate a fresh join would hit.
# A subscription that has expired returns "No active IPFS subscription".
#
# The response contains the swarm key, so stdout is captured and parsed but
# never logged.
#
# Exit 0 = active, 1 = expired/denied, 2 = check inconclusive (unreachable,
# auth, wallet problems -- transient, not a subscription state).

set -euo pipefail

TAG="aitbc-island-sub-check"
WALLET=${ISLAND_WALLET:-default}
ISLAND_ID=${ISLAND_ID:-ait-localnet-island}
COORD=${COORDINATOR_URL:-https://hub.aitbc.invalid/c}
AITBC_WALLET_DIR=${AITBC_WALLET_DIR:-/var/lib/aitbc/wallets}
export AITBC_WALLET_DIR

log() { logger -t "$TAG" -p "user.$1" -- "$2"; echo "[$1] $2"; }

out=$(aitbc ipfs island swarm-key \
    --wallet "$WALLET" \
    --island-id "$ISLAND_ID" \
    --coordinator-url "$COORD" \
    --password "" 2>&1) || true

if printf '%s' "$out" | grep -q '"success": true'; then
    log info "island subscription active ($ISLAND_ID, wallet $WALLET)"
    exit 0
fi

if printf '%s' "$out" | grep -qi "No active IPFS subscription"; then
    log err "island subscription EXPIRED or missing for $WALLET on $ISLAND_ID -- renew with: aitbc ipfs island subscribe"
    exit 1
fi

# Anything else (HTTP error, unreachable coordinator, wallet/auth issues) is
# not a subscription verdict -- warn but don't page.
short=$(printf '%s' "$out" | head -3 | tr '\n' ' ')
log warning "subscription check inconclusive: $short"
exit 2
