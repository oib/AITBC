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

echo "=== *_ADDRESS value-shape check ==="
# systemd EnvironmentFile does not strip inline `#` comments: a comment on an
# assignment line becomes part of the value (measured 110 bytes instead of 42
# on 8 Sep). Assert every *_ADDRESS variable is exactly 0x + 40 hex.
shape_bad=0
for h in $HOSTS; do
    bad=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$h" \
        "grep -hE '^[A-Z_0-9]*ADDRESS=' /etc/aitbc/blockchain.env /etc/aitbc/node.env 2>/dev/null \
         | while IFS= read -r line; do \
             name=\${line%%=*}; val=\${line#*=}; val=\$(echo \"\$val\" | tr -d '[:space:]'); \
             echo \"\$val\" | grep -qE '^0x[0-9a-fA-F]{40}\$' || echo \"\$name\"; \
           done" 2>/dev/null || echo "UNREACHABLE")
    if [ -n "$bad" ]; then
        shape_bad=1
        for name in $bad; do printf "  %-14s %s <- malformed\n" "$h" "$name"; done
    fi
done
if [ "$shape_bad" -eq 0 ]; then
    echo "  all *_ADDRESS values well-formed on all hosts"
fi

echo
if [ "$drift" -eq 0 ] && [ "$shape_bad" -eq 0 ]; then
    echo "No drift across: $HOSTS"
    exit 0
else
    echo "DRIFT DETECTED — differing/malformed values above"
    exit 1
fi
