#!/bin/bash
# Fleet config-drift check: compares consensus-relevant env vars across hosts.
#
# Per-node env drift in consensus-facing variables is a silent-divergence
# vector: on 1-2 Sep node0 had no BOND_SLASH_AUTHORITY_ADDRESS and skipped
# five slashes the rest of the fleet applied — same blocks, different state.
# Run this after any env change and before relying on per-node gates.
#
# Usage: fleet-config-check.sh [host ...]
# Default hosts come from AITBC_FLEET_HOSTS or the standard fleet.
#
# Mirrors systemd EnvironmentFile ordering: later files win, so the effective
# value is the last match across blockchain.env then node.env.

set -euo pipefail

if [ "$#" -gt 0 ]; then
    HOSTS="$*"
else
    HOSTS="${AITBC_FLEET_HOSTS:-node0 node1 node2 hub.aitbc hub2.aitbc}"
fi

VARS="BOND_SLASH_AUTHORITY_ADDRESS CHAIN_ID SUPPORTED_CHAINS \
STATE_TRANSITION_V2_HEIGHT STATE_TRANSITION_V3_HEIGHT \
SYNC_STATE_ROOT_VALIDATION_ENABLED BOND_ESCROW_ADDRESS BOND_BURN_ADDRESS"

drift=0
for var in $VARS; do
    echo "=== $var ==="
    seen=""
    for h in $HOSTS; do
        val=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$h" \
            "grep -h '^${var}=' /etc/aitbc/blockchain.env /etc/aitbc/node.env 2>/dev/null | tail -1 | cut -d= -f2-" \
            2>/dev/null || echo "UNREACHABLE")
        if [ -z "$val" ]; then
            val="<unset>"
        fi
        printf "  %-14s %s\n" "$h" "$val"
        if [ -z "$seen" ]; then
            seen="$val"
        elif [ "$seen" != "$val" ]; then
            drift=1
        fi
    done
done

echo
if [ "$drift" -eq 0 ]; then
    echo "No drift across: $HOSTS"
    exit 0
else
    echo "DRIFT DETECTED — differing values above"
    exit 1
fi
