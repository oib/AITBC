#!/bin/bash
# Check that this node's island IPFS subscription is still active by calling
# the coordinator's swarm-key endpoint -- the same gate a fresh join would hit.
# A subscription that has expired returns "No active IPFS subscription".
#
# The response contains the swarm key, so stdout is captured and parsed but
# never logged verbatim; classification greps known substrings only.
#
# Exit 0 = active
#      1 = expired/denied (subscription state -- renew)
#      2 = coordinator down/unreachable (transient)
#      3 = no API key resolved -- AITBC_API_KEY unset and every CLI fallback
#          leg empty (see docs/ops/island-subscription-check.md)
#      4 = key configured but refused by the service (HTTP 401/403)
#      5 = check inconclusive for any other reason
#
# The unit sources /etc/aitbc/aitbc-island-subscription-check.env when it
# exists; that file is operator-created and never lives in the repo.

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

# No key resolved on any CLI leg (config api_key, AITBC_API_KEY, or the
# fallback env files). Names the variable and the file, never a value.
if printf '%s' "$out" | grep -qi "No API key"; then
    log err "subscription check cannot run: AITBC_API_KEY is not configured -- create /etc/aitbc/aitbc-island-subscription-check.env (mode 600, owner root) containing AITBC_API_KEY=<the node miner API key>; see docs/ops/island-subscription-check.md"
    exit 3
fi

# Key was configured but the service refused it.
if printf '%s' "$out" | grep -qEi "HTTP (401|403)|\b(401|403)\b|[Uu]nauthorized|[Ff]orbidden|[Ii]nvalid (API )?key|[Aa]uthentication (failed|required)"; then
    log err "subscription check refused: the configured AITBC_API_KEY was rejected by the coordinator (HTTP 401/403) -- rotate or repair the key in /etc/aitbc/aitbc-island-subscription-check.env"
    exit 4
fi

# Transport-level failure: coordinator down, DNS, timeout.
if printf '%s' "$out" | grep -qEi "refused|timed? ?out|unreachable|resolve|connect|network"; then
    short=$(printf '%s' "$out" | head -3 | tr '\n' ' ')
    log warning "subscription check inconclusive: coordinator unreachable ($COORD): $short"
    exit 2
fi

# Anything else is not a subscription verdict -- warn but don't page.
short=$(printf '%s' "$out" | head -3 | tr '\n' ' ')
log warning "subscription check inconclusive: $short"
exit 5
