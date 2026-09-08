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

echo "=== chain-head convergence (height + hash, two samples) ==="
# Forks look like: equal heights with different hashes. Poll skew looks like:
# heights differing by one with matching hashes. Flag ONLY hash mismatch at an
# equal height, or a host trailing the fleet max by >2 blocks in BOTH samples.
# A failed/empty probe prints UNREACHABLE — distinct from a real divergence.
conv_bad=0
sample_heads() {
    for h in $HOSTS; do
        out=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$h" \
            "sqlite3 /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
             'SELECT height || \"|\" || substr(hash,1,16) FROM block ORDER BY height DESC LIMIT 1' 2>/dev/null" \
            2>/dev/null || true)
        if [ -z "$out" ]; then
            echo "$h UNREACHABLE"
        else
            echo "$h $out"
        fi
    done
}
S1_OUT=$(sample_heads)
sleep 5
S2_OUT=$(sample_heads)

report_and_check() {
    local label="$1" data="$2" bad=0 max=0
    echo "  -- $label --"
    while read -r host rest; do
        [ -z "$host" ] && continue
        echo "  $host  $rest"
        if [ "$rest" != "UNREACHABLE" ]; then
            ht=${rest%%|*}
            [ "$ht" -gt "$max" ] 2>/dev/null && max=$ht
        fi
    done <<< "$data"
    # hash mismatch at equal height = fork
    while read -r ht; do
        [ -z "$ht" ] && continue
        hashes=$(echo "$data" | awk -v H="$ht" '$2 ~ "^"H"\\|" {print $2}' | cut -d'|' -f2 | sort -u | wc -l)
        if [ "$hashes" -gt 1 ]; then
            echo "  FORK: hosts at height $ht disagree on hash"
            bad=1
        fi
    done <<< "$(echo "$data" | grep -v UNREACHABLE | awk '{split($2,a,"|"); print a[1]}' | sort -un)"
    # unreachable is a distinct warning
    echo "$data" | grep -q UNREACHABLE && { echo "  WARNING: host probe(s) failed (UNREACHABLE above)"; bad=1; }
    echo "$bad $max"
}

R1=$(report_and_check "sample 1" "$S1_OUT")
echo "$R1" | head -n -1
R2=$(report_and_check "sample 2" "$S2_OUT")
echo "$R2" | head -n -1
b1=$(echo "$R1" | tail -1 | cut -d' ' -f1); m1=$(echo "$R1" | tail -1 | cut -d' ' -f2)
b2=$(echo "$R2" | tail -1 | cut -d' ' -f1); m2=$(echo "$R2" | tail -1 | cut -d' ' -f2)
if [ "${b1:-0}" = "1" ] || [ "${b2:-0}" = "1" ]; then conv_bad=1; fi
# lag check: trailing >2 blocks in BOTH samples
while read -r host rest; do
    [ "$rest" = "UNREACHABLE" ] && continue
    h1=$(echo "$S1_OUT" | awk -v H="$host" '$1==H {split($2,a,"|"); print a[1]}')
    h2=$(echo "$S2_OUT" | awk -v H="$host" '$1==H {split($2,a,"|"); print a[1]}')
    if [ -n "$h1" ] && [ -n "$h2" ]; then
        if [ "$h1" -lt $((m1 - 2)) ] && [ "$h2" -lt $((m2 - 2)) ]; then
            echo "  LAG: $host trails fleet by >2 blocks in both samples ($h1 vs $m1, $h2 vs $m2)"
            conv_bad=1
        fi
    fi
done <<< "$S2_OUT"

echo
if [ "$drift" -eq 0 ] && [ "$shape_bad" -eq 0 ] && [ "$conv_bad" -eq 0 ]; then
    echo "No drift across: $HOSTS"
    exit 0
else
    echo "DRIFT DETECTED — differing/malformed values or chain divergence above"
    exit 1
fi
