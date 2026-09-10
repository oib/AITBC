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
    HOSTS="${AITBC_FLEET_HOSTS:-node0 node1 node2 hub hub1}"
fi

# Host names are site-dependent: the IDE reaches hub/hub1 via ssh-config
# aliases (hub.aitbc), fleet nodes via FQDNs, and neither scheme resolves
# everywhere. Auto-probe candidate addresses per canonical host so the check
# runs identically on the IDE and on any fleet node.
declare -A HOST_CANDIDATES=(
    [node0]="node0 10.1.223.93"
    [node1]="node1 10.1.223.40"
    [node2]="node2 10.1.223.136"
    [hub]="hub.aitbc hub.aitbc.bubuit.net 192.168.100.10"
    [hub1]="hub1.aitbc hub1.aitbc.bubuit.net 10.177.61.28"
)

declare -A RESOLVED=()
ssh_reach=0
for host in $HOSTS; do
    RESOLVED[$host]=""
    for cand in ${HOST_CANDIDATES[$host]:-$host}; do
        if ssh -o ConnectTimeout=4 -o BatchMode=yes "$cand" true 2>/dev/null; then
            RESOLVED[$host]=$cand
            ssh_reach=1
            break
        fi
    done
    if [ -z "${RESOLVED[$host]}" ]; then
        RESOLVED[$host]=$host
    fi
done
if [ "$ssh_reach" -eq 0 ]; then
    echo "NOTE: no ssh reach to any fleet host from here — env sections SKIPPED"
    echo "(env reads are dev-tier; the convergence section below works anywhere)"
fi

VARS="BOND_SLASH_AUTHORITY_ADDRESS CHAIN_ID SUPPORTED_CHAINS \
STATE_TRANSITION_V2_HEIGHT STATE_TRANSITION_V3_HEIGHT \
SYNC_STATE_ROOT_VALIDATION_ENABLED BOND_ESCROW_ADDRESS BOND_BURN_ADDRESS"

drift=0
shape_bad=0
shadowed=0
eff_drift=0
if [ "$ssh_reach" -eq 0 ]; then
    echo "=== env sections skipped (no ssh reach) ==="
else
for var in $VARS; do
    echo "=== $var ==="
    seen=""
    for h in $HOSTS; do
        val=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
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
for h in $HOSTS; do
    bad=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
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
echo "=== EnvironmentFile shadow check ==="
# The 8 Sep outage and the mesh-peer defect found on 9 Sep were the same bug:
# a variable set in two EnvironmentFile entries of one unit, where the later
# file silently wins. Neither was visible in the file the operator was reading.
# Flag any variable assigned in more than one EnvironmentFile of a unit.
shadowed=0
for h in $HOSTS; do
    out=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        'for unit in aitbc-blockchain-node aitbc-blockchain-rpc; do
            files=$(systemctl show -p EnvironmentFiles --value "$unit" 2>/dev/null \
                    | tr " " "\n" | sed "s/ (ignore_errors=.*)//; s/^-//" | grep "^/" || true)
            [ -z "$files" ] && continue
            for f in $files; do
                [ -r "$f" ] || continue
                sudo grep -hoE "^[A-Za-z_][A-Za-z0-9_]*=" "$f" | tr -d "=" | sed "s|$| $f|"
            done | sort | awk -v U="$unit" "
                {name=\$1; file=\$2; if (name==prev) {n++; list=list \" \" file}
                 else {if (n>1) print U \" \" prev \" \" list; prev=name; n=1; list=file}}
                END {if (n>1) print U \" \" prev \" \" list}"
        done' 2>/dev/null || echo "UNREACHABLE")
    if [ -n "$out" ] && [ "$out" != "UNREACHABLE" ]; then
        shadowed=1
        echo "$out" | while read -r unit name files; do
            printf "  %-14s %s: %s set in >1 file: %s\n" "$h" "$unit" "$name" "$files"
        done
    fi
done
if [ "$shadowed" -eq 0 ]; then
    echo "  no variable is set by more than one EnvironmentFile on any host"
fi

echo "=== effective env (from the running process, not the files) ==="
# Files are what we intend; /proc/<pid>/environ is what the node actually got.
# Reading the files reproduces our own precedence assumptions and so cannot
# catch a mistake in them; this section reads ground truth instead.
eff_drift=0
EFF_VARS="$VARS GOSSIP_BACKEND GOSSIP_MESH_PEER_URLS"
for var in $EFF_VARS; do
    seen=""
    first=1
    for h in $HOSTS; do
        val=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
            "pid=\$(systemctl show -p MainPID --value aitbc-blockchain-node 2>/dev/null); \
             if [ -n \"\$pid\" ] && [ \"\$pid\" != 0 ]; then \
                 sudo tr '\\0' '\\n' < /proc/\$pid/environ | grep '^${var}=' | cut -d= -f2- | tail -1; \
             else echo NOTRUNNING; fi" 2>/dev/null || echo "UNREACHABLE")
        [ -z "$val" ] && val="<unset>"
        if [ "$first" -eq 1 ]; then
            echo "=== $var (effective) ==="
            first=0
        fi
        printf "  %-14s %s\n" "$h" "$val"
        if [ -z "$seen" ]; then
            seen="$val"
        elif [ "$seen" != "$val" ]; then
            # peer lists are legitimately per-host: each node omits itself.
            case "$var" in
                GOSSIP_MESH_PEER_URLS) ;;
                *) eff_drift=1 ;;
            esac
        fi
    done
done
if [ "$eff_drift" -eq 0 ]; then
    echo "  no effective-env drift in consensus variables"
fi

fi  # ssh_reach

echo "=== chain-head convergence (height + hash, two samples) ==="
# Forks look like: equal heights with different hashes. Poll skew looks like:
# heights differing by one with matching hashes. Flag ONLY hash mismatch at an
# equal height, or a host trailing the fleet max by >2 blocks in BOTH samples.
# A failed/empty probe prints UNREACHABLE — distinct from a real divergence.
#
# Head state is pulled from each node's own RPC surface (/rpc/status) — the
# surface peers already use — so this section runs from ANY host, fleet node
# or IDE alike, with no ssh. (The env sections above stay ssh-based: reading
# a host's env is dev-tier and fleet nodes have no inter-node ssh by design.)
declare -A RPC_ENDPOINTS=(
    [node0]="http://10.1.223.93:8202/rpc/status"
    [node1]="http://10.1.223.40:8202/rpc/status"
    [node2]="http://10.1.223.136:8202/rpc/status"
    [hub]="https://hub.aitbc.bubuit.net/rpc/status"
    [hub1]="https://hub1.aitbc.bubuit.net/rpc/status"
    [hub.aitbc]="https://hub.aitbc.bubuit.net/rpc/status"
    [hub1.aitbc]="https://hub1.aitbc.bubuit.net/rpc/status"
)
conv_bad=0
sample_heads() {
    for h in $HOSTS; do
        out=""
        url="${RPC_ENDPOINTS[$h]:-}"
        if [ -n "$url" ]; then
            out=$(curl -s -m 6 -k "$url" 2>/dev/null | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(str(d["height"]) + "|" + d["last_block_hash"][:16])
except Exception:
    pass' 2>/dev/null)
        fi
        if [ -z "$out" ]; then
            echo "$h UNREACHABLE"
        else
            echo "$h $out"
        fi
    done
}
S1_OUT=$(sample_heads)
sleep 90
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
# liveness check: the fleet must make progress between the two samples; five
# hosts agreeing on a dead chain is a perfect convergence result.
if [ -n "$m1" ] && [ -n "$m2" ] && [ "$m2" -le "$m1" ]; then
    echo "  HALT: fleet max height did not increase between samples ($m1 -> $m2)"
    conv_bad=1
fi
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
if [ "$drift" -eq 0 ] && [ "$shape_bad" -eq 0 ] && [ "$conv_bad" -eq 0 ] \
   && [ "$shadowed" -eq 0 ] && [ "$eff_drift" -eq 0 ]; then
    echo "No drift across: $HOSTS"
    exit 0
else
    echo "DRIFT DETECTED — differing/malformed values or chain divergence above"
    exit 1
fi
