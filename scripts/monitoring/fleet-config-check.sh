#!/bin/bash
# Fleet config-drift check: compares consensus-relevant env vars across hosts.
#
# Per-node env drift in consensus-facing variables is a silent-divergence
# vector: on 1-2 Sep node0 had no BOND_SLASH_AUTHORITY_ADDRESS and skipped
# five slashes the rest of the fleet applied — same blocks, different state.
# Run this after any env change and before relying on per-node gates.
#
# Usage: fleet-config-check.sh [host ...]
# Hosts come from the arguments, else from AITBC_FLEET_HOSTS. There is no
# built-in roster: a hardcoded one named the operator's hosts in a public
# repository and was wrong for every other site.
#
# Mirrors systemd EnvironmentFile ordering: later files win. The file list is
# read from the aitbc-blockchain-node unit itself rather than hardcoded, so a
# variable kept in a secrets EnvironmentFile (node0 carries
# ESCROW_RELEASE_ADDRESS in blockchain-secrets.env) is not flagged as unset.

set -euo pipefail


# Fleet node addresses.
#
# These were hardcoded to one island's private subnet, which made the check
# useless anywhere else and put internal addressing in a public repository.
# They are optional: each is only an extra candidate to try after the names
# below, so leaving them unset costs nothing wherever the names resolve.
HUB1_HOST="${AITBC_HUB1_HOST:-}"

# Deliberate per-unit overrides, as "unit:VAR" pairs. The shadow check below
# flags any variable whose value differs across a unit's EnvironmentFiles —
# but an *-override.env file exists precisely to differ, so those pairs are
# informational rather than failures. Keep this list short and commented.
# (hub's aitbc-blockchain-rpc-override.env stops the RPC service producing.)
# (GOSSIP_BACKEND differs by design since 2026-09-27: the node unit runs the
# validator mesh while the rpc unit is the local Redis bus bridge — the mesh
# doc says "only the node process should dial peers".)
SHADOW_CONFLICT_ALLOW="${SHADOW_CONFLICT_ALLOW:-aitbc-blockchain-rpc:ENABLE_BLOCK_PRODUCTION aitbc-blockchain-rpc:BLOCK_PRODUCTION_CHAINS aitbc-blockchain-rpc:GOSSIP_BACKEND}"

# The domain the fleet publishes under. It was hardcoded here, which named the
# operator in a public repo and made the check point at their hosts from anyone
# else's machine.
AITBC_FLEET_DOMAIN="${AITBC_FLEET_DOMAIN:?set AITBC_FLEET_DOMAIN to the domain your fleet publishes under}"
HUB_HOST="${AITBC_HUB_HOST:-}"
NODE0_HOST="${AITBC_NODE0_HOST:-}"
NODE1_HOST="${AITBC_NODE1_HOST:-}"
NODE2_HOST="${AITBC_NODE2_HOST:-}"

if [ "$#" -gt 0 ]; then
    HOSTS="$*"
else
    HOSTS="${AITBC_FLEET_HOSTS:?set AITBC_FLEET_HOSTS to the hosts to check, or pass them as arguments}"
fi

# Host names are site-dependent: a canonical host may answer to a bare name,
# to an ssh-config alias, or only to an FQDN, and no single scheme resolves
# everywhere. Auto-probe candidate addresses per canonical host so the check
# runs identically from a workstation and from any fleet node. Set the
# *_ALIAS/*_HOST variables for whatever your site needs; unset ones cost
# nothing, they are simply skipped as candidates.
declare -A HOST_CANDIDATES=(
    [node0]="node0 ${NODE0_HOST}"
    [node1]="node1 ${NODE1_HOST}"
    [node2]="node2 ${NODE2_HOST}"
    [hub]="${AITBC_HUB_ALIAS:-} hub.${AITBC_FLEET_DOMAIN} ${HUB_HOST}"
    [hub1]="${AITBC_HUB1_ALIAS:-} hub1.${AITBC_FLEET_DOMAIN} ${HUB1_HOST}"
)

declare -A RESOLVED=()
unresolved=""
for host in $HOSTS; do
    RESOLVED[$host]=""
    for cand in ${HOST_CANDIDATES[$host]:-$host}; do
        # A candidate must not only answer ssh — it must BE the host. From a
        # fleet node, hub.<domain> resolves to the edge jump box, which accepts
        # the connection and would happily serve its own env files as "hub's".
        got=$(ssh -o ConnectTimeout=4 -o BatchMode=yes "$cand" 'hostname -s' 2>/dev/null || true)
        if [ "$got" = "$host" ]; then
            RESOLVED[$host]=$cand
            break
        elif [ -n "$got" ]; then
            echo "  NOTE: $cand answers as '$got', not '$host' — ignored"
        fi
    done
    if [ -z "${RESOLVED[$host]}" ]; then
        RESOLVED[$host]=$host
        unresolved="$unresolved $host"
    fi
done
if [ -n "$unresolved" ]; then
    ssh_reach=0
    echo "NOTE: no verified ssh reach to:$unresolved — env sections SKIPPED"
    echo "(env reads are dev-tier; the convergence section below works anywhere)"
else
    ssh_reach=1
fi

# Resolve each host's EnvironmentFile list once: the node unit's own unit files
# are the authoritative answer to "what env does the process intend to get".
# Fallback keeps the old two-file read for hosts where systemctl cannot answer.
ENVFILE_CMD='systemctl show -p EnvironmentFiles --value aitbc-blockchain-node 2>/dev/null \
    | tr " " "\n" | sed "s/ (ignore_errors=.*)//; s/^-//" | grep "^/"'
ENVFILE_FALLBACK="/etc/aitbc/blockchain.env /etc/aitbc/node.env"

# Read VAR from the RUNNING process environment of UNIT on a host. Env files
# say what the next start will get; /proc/<MainPID>/environ is what is running
# (and paying out) now — comparing the two catches "edited but not restarted".
# Prints the value (empty when unset in the running env), NOTRUNNING, or
# UNREACHABLE. Pass " -i" as $4 when the service reads the var
# case-insensitively (blockchain-node's pydantic settings); agent-coordinator
# uses os.getenv and needs exact case.
running_env() {
    ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$1]:-$1}" \
        "pid=\$(systemctl show -p MainPID --value $2 2>/dev/null)
         if [ -z \"\$pid\" ] || [ \"\$pid\" = 0 ]; then echo NOTRUNNING; exit 0; fi
         if [ -r /proc/\$pid/environ ]; then tr '\0' '\n' < /proc/\$pid/environ; else sudo -n tr '\0' '\n' < /proc/\$pid/environ 2>/dev/null; fi | grep$4 \"^$3=\" | tail -1 | cut -d= -f2-" \
        2>/dev/null || echo "UNREACHABLE"
}

declare -A ENVFILES=()
if [ "$ssh_reach" -eq 1 ]; then
    for host in $HOSTS; do
        ENVFILES[$host]=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$host]}" "$ENVFILE_CMD" 2>/dev/null || true)
        if [ -z "${ENVFILES[$host]}" ]; then
            ENVFILES[$host]="$ENVFILE_FALLBACK"
        fi
    done
fi

VARS="BOND_SLASH_AUTHORITY_ADDRESS CHAIN_ID SUPPORTED_CHAINS \
STATE_TRANSITION_V2_HEIGHT STATE_TRANSITION_V3_HEIGHT \
STATE_TRANSITION_V4_HEIGHT STATE_TRANSITION_V5_HEIGHT STATE_TRANSITION_V6_HEIGHT STATE_TRANSITION_V7_HEIGHT \
STATE_TRANSITION_V8_HEIGHT \
ESCROW_RELEASE_ADDRESS ESCROW_SETTLEMENT_AUTHORITY BRIDGE_RELEASE_AUTHORITY \
SYNC_STATE_ROOT_VALIDATION_ENABLED BOND_ESCROW_ADDRESS BOND_BURN_ADDRESS"

drift=0
shape_bad=0
shadowed=0
eff_drift=0
faucet_bad=0
mesh_bad=0
if [ "$ssh_reach" -eq 0 ]; then
    echo "=== env sections skipped (no ssh reach) ==="
else
for var in $VARS; do
    echo "=== $var ==="
    seen=""
    for h in $HOSTS; do
        val=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
            "echo \"${ENVFILES[$h]}\" | tr ' ' '\n' | while IFS= read -r f; do if [ -r \"\$f\" ]; then grep -h '^${var}=' \"\$f\" 2>/dev/null; else sudo -n grep -h '^${var}=' \"\$f\" 2>/dev/null; fi; done | tail -1 | cut -d= -f2-" \
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

echo "=== signature-validation kill-switch check ==="
# SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL disables proposer-signature validation
# until a timestamp. It is a deliberate escape hatch for migrations, but a
# value left set on a node is silent consensus weakening: flag it whenever
# it is set at all, on any host.
skip_flagged=0
for h in $HOSTS; do
    val=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        "echo \"${ENVFILES[$h]}\" | tr ' ' '\n' | while IFS= read -r f; do if [ -r \"\$f\" ]; then grep -h '^SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL=' \"\$f\" 2>/dev/null; else sudo -n grep -h '^SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL=' \"\$f\" 2>/dev/null; fi; done | tail -1 | cut -d= -f2-" \
        2>/dev/null || echo "UNREACHABLE")
    # pydantic reads this setting case-insensitively, hence grep -i.
    run=$(running_env "$h" aitbc-blockchain-node SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL " -i")
    fset=""; rset=""
    [ -n "$val" ] && [ "$val" != "UNREACHABLE" ] && fset=1
    [ -n "$run" ] && [ "$run" != "UNREACHABLE" ] && [ "$run" != "NOTRUNNING" ] && rset=1
    if [ -n "$fset" ] || [ -n "$rset" ]; then
        skip_flagged=1
        printf "  %-14s SET: file=%s running=%s <- signature validation disabled until then\n" \
            "$h" "${val:-<unset>}" "${run:-<unset>}"
    fi
done
if [ "$skip_flagged" -eq 0 ]; then
    echo "  SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL unset on all hosts (files and running processes)"
fi

echo "=== faucet budget check (exactly one live agent-coordinator faucet) ==="
# hub and hub1 both run aitbc-agent-coordinator with their own coin_requests
# DB and both hold the genesis key; two live faucets double the fleet-wide
# automatic budget. hub1 carries COIN_REQUEST_AUTO_BUDGET_PER_HOUR=0 only in
# its env file, so a reprovision silently restores the doubling. Across hosts
# that have the unit, exactly one may have a non-zero — or unset, the default
# is non-zero — COIN_REQUEST_AUTO_BUDGET_PER_HOUR.
live=0
for h in $HOSTS; do
    val=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        'files=$(systemctl show -p EnvironmentFiles --value aitbc-agent-coordinator 2>/dev/null \
            | tr " " "\n" | sed "s/ (ignore_errors=.*)//; s/^-//" | grep "^/" || true)
         if [ -z "$files" ]; then echo NOUNIT; exit 0; fi
         echo "$files" | while IFS= read -r f; do
             if [ -r "$f" ]; then grep -h "^COIN_REQUEST_AUTO_BUDGET_PER_HOUR=" "$f" 2>/dev/null; else sudo -n grep -h "^COIN_REQUEST_AUTO_BUDGET_PER_HOUR=" "$f" 2>/dev/null; fi
         done | tail -1 | cut -d= -f2-' \
        2>/dev/null || echo "UNREACHABLE")
    if [ "$val" = "UNREACHABLE" ]; then
        faucet_bad=1
        printf "  %-14s UNREACHABLE\n" "$h"
        continue
    fi
    if [ "$val" = "NOUNIT" ]; then
        printf "  %-14s no agent-coordinator unit\n" "$h"
        continue
    fi
    val=$(echo "$val" | tr -d '[:space:]')
    # The running process decides what actually pays out; the file decides
    # what a restart will get. A mismatch is a pending flip — flag it.
    run=$(running_env "$h" aitbc-agent-coordinator COIN_REQUEST_AUTO_BUDGET_PER_HOUR "")
    if [ "$run" = "UNREACHABLE" ]; then
        faucet_bad=1
        printf "  %-14s UNREACHABLE (running env)\n" "$h"
        continue
    fi
    printf "  %-14s file=%s running=%s\n" "$h" "${val:-<unset>}" "${run:-<unset>}"
    if [ "$run" = "NOTRUNNING" ]; then
        echo "  WARN: $h agent-coordinator unit exists but is not running"
        continue
    fi
    if [ "${val:-<unset>}" != "${run:-<unset>}" ]; then
        faucet_bad=1
        echo "  WARN: $h agent-coordinator env edited but not restarted (file=${val:-<unset>} running=${run:-<unset>})"
    fi
    case "$run" in
        0|0.0) ;;
        *) live=$((live + 1)) ;;
    esac
done
if [ "$live" -ne 1 ]; then
    faucet_bad=1
    echo "  FAIL: $live agent-coordinator hosts have a live faucet budget; expected exactly 1"
else
    echo "  ok: exactly one live faucet"
fi

echo "=== gossip mesh check (every host on mesh, peer list complete and self-free) ==="
# 2026-09-27: the fleet had regressed to hub-and-spoke for 18 days without the
# earlier drift sections catching it — the env files said `websocket`/`redis`
# while `GOSSIP_MESH_PEER_URLS` lists sat ignored. What must be asserted is the
# RUNNING backend (files lied), plus the shadow bait that made the regression
# silent: no GOSSIP_BACKEND in aitbc-blockchain-node.env (its only job there is
# to clobber blockchain.env), GOSSIP_BACKEND=redis in aitbc-blockchain-rpc.env
# (the rpc process stays the local bus bridge), and no GOSSIP_WEBSOCKET_URL
# anywhere. Peers must list every other host and never the host itself.
mesh_bad=0
for h in $HOSTS; do
    run_backend=$(running_env "$h" aitbc-blockchain-node GOSSIP_BACKEND " -i")
    case "$run_backend" in
        UNREACHABLE) mesh_bad=1; printf "  %-14s UNREACHABLE (running env)\n" "$h"; continue ;;
        NOTRUNNING)  mesh_bad=1; printf "  %-14s aitbc-blockchain-node NOTRUNNING\n" "$h"; continue ;;
    esac
    run_peers=$(running_env "$h" aitbc-blockchain-node GOSSIP_MESH_PEER_URLS " -i")
    # The host's own identities — self-references in the peer list are a loop.
    selfinfo=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        'hostname -s; hostname; hostname -I' 2>/dev/null || echo "UNREACHABLE")
    if [ "$run_backend" != "mesh" ]; then
        mesh_bad=1
        printf "  %-14s running backend is '%s', expected 'mesh'\n" "$h" "${run_backend:-<unset>}"
        continue
    fi
    peers_trim=$(echo "$run_peers" | tr -d '[:space:]')
    n_peers=$(awk -F, 'NF {print NF}' <<<"$peers_trim")
    self_hit=0
    for ident in $selfinfo; do
        ident=$(echo "$ident" | tr -d '[:space:]')
        [ -z "$ident" ] && continue
        case ",$peers_trim," in *"://$ident."*|*"://$ident:"*|*"://$ident/"*) self_hit=1 ;; esac
    done
    problems=""
    [ "${n_peers:-0}" -lt 2 ] && problems="$problems only ${n_peers:-0} peers"
    [ "$self_hit" -eq 1 ] && problems="$problems peer list contains SELF"
    # File side: effective value across the node unit's files must be mesh
    # (case-insensitive — a lowercase `gossip_backend=` sets the same pydantic
    # field and invisible-to-uppercase-grep was part of the original miss).
    file_eff=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        "echo \"${ENVFILES[$h]}\" | tr ' ' '\n' | while IFS= read -r f; do if [ -r \"\$f\" ]; then grep -hiE '^gossip_backend=' \"\$f\" 2>/dev/null; else sudo -n grep -hiE '^gossip_backend=' \"\$f\" 2>/dev/null; fi; done | tail -1 | cut -d= -f2-; \
         grep -l -iE '^gossip_backend=' /etc/aitbc/aitbc-blockchain-node.env 2>/dev/null | xargs -r -n1 basename | while read f; do echo SHADOWNODE:\$f; done; \
         grep -hiE '^gossip_backend=' /etc/aitbc/aitbc-blockchain-rpc.env 2>/dev/null | tail -1 | sed 's/^/RPC:/;s/gossip_backend=/rpc=/I'; \
         for f in \$(echo \"${ENVFILES[$h]}\" | tr ' ' '\n'); do if [ -r \"\$f\" ]; then grep -Hi '^GOSSIP_WEBSOCKET_URL=' \"\$f\" 2>/dev/null; else sudo -n grep -Hi '^GOSSIP_WEBSOCKET_URL=' \"\$f\" 2>/dev/null; fi; done | sed 's/.*\///; s/:.*//' | xargs -r -n1 | while read f; do echo SPOKEURL:\$f; done" \
        2>/dev/null || echo "UNREACHABLE")
    [ "$file_eff" = "UNREACHABLE" ] && { mesh_bad=1; printf "  %-14s UNREACHABLE (env files)\n" "$h"; continue; }
    file_backend=$(echo "$file_eff" | grep -v "^\(SHADOWNODE\|RPC\|SPOKEURL\):" | head -1 | tr -d '[:space:]')
    [ "$file_backend" != "mesh" ] && problems="$problems node-unit files resolve to '$file_backend' not 'mesh'"
    echo "$file_eff" | grep -q "^SHADOWNODE:" && problems="$problems GOSSIP_BACKEND in aitbc-blockchain-node.env"
    rpc_backend=$(echo "$file_eff" | grep "^RPC:" | head -1 | cut -d: -f2 | cut -d= -f2 | tr -d '[:space:]')
    [ -n "$rpc_backend" ] && [ "$rpc_backend" != "redis" ] && problems="$problems rpc unit backend '$rpc_backend' not 'redis'"
    echo "$file_eff" | grep -q "^SPOKEURL:" && problems="$problems GOSSIP_WEBSOCKET_URL still set"
    if [ -n "$problems" ]; then
        mesh_bad=1
        printf "  %-14s mesh — FAIL:%s\n" "$h" "$problems"
    else
        printf "  %-14s mesh, %s peers, self-free, files clean\n" "$h" "$n_peers"
    fi
done
if [ "$mesh_bad" -eq 0 ]; then
    echo "  ok: every host on mesh with a complete, self-free peer list"
fi

echo "=== *_ADDRESS value-shape check ==="
# systemd EnvironmentFile does not strip inline `#` comments: a comment on an
# assignment line becomes part of the value (measured 110 bytes instead of 42
# on 8 Sep). Assert every *_ADDRESS variable is exactly 0x + 40 hex.
for h in $HOSTS; do
    bad=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        "echo \"${ENVFILES[$h]}\" | tr ' ' '\n' | while IFS= read -r f; do if [ -r \"\$f\" ]; then grep -hE '^[A-Z_0-9]*ADDRESS=' \"\$f\" 2>/dev/null; else sudo -n grep -hE '^[A-Z_0-9]*ADDRESS=' \"\$f\" 2>/dev/null; fi; done \
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
#
# The fleet's env files turn out to share a copied baseline blob, so most
# shadowed variables carry the *same* value in every file — latent precedence
# debt, not a live divergence. What must fail the run is a variable whose
# values DISAGREE across files. Values are hashed (sha256, 8 chars) rather
# than echoed: these files hold keys.
shadowed=0
for h in $HOSTS; do
    out=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        'for unit in aitbc-blockchain-node aitbc-blockchain-rpc; do
            files=$(systemctl show -p EnvironmentFiles --value "$unit" 2>/dev/null \
                    | tr " " "\n" | sed "s/ (ignore_errors=.*)//; s/^-//" | grep "^/" || true)
            [ -z "$files" ] && continue
            echo "$files" | while IFS= read -r f; do
                if [ -r "$f" ]; then
                    grep -hE "^[A-Za-z_][A-Za-z0-9_]*=" "$f" 2>/dev/null
                else
                    sudo -n grep -hE "^[A-Za-z_][A-Za-z0-9_]*=" "$f" 2>/dev/null
                fi | while IFS="=" read -r name val; do
                    [ -n "$name" ] || continue
                    h=$(printf "%s" "$val" | sha256sum | cut -c1-8)
                    printf "%s %s %s\n" "$name" "$h" "$f"
                done
            done | sort | awk -v U="$unit" "
                {name=\$1; hash=\$2; file=\$3
                 if (name==prev) { if (!(hash in seen)) {seen[hash]=1; nh++}; n++; flist=flist \" \" file }
                 else { if (n>1) print U, prev, (nh>1 ? \"CONFLICT\" : \"redundant\"), flist
                        split(\"\", seen); seen[hash]=1; nh=1; n=1; flist=file; prev=name }}
                END { if (n>1) print U, prev, (nh>1 ? \"CONFLICT\" : \"redundant\"), flist }"
        done' 2>/dev/null || echo "UNREACHABLE")
    if [ -n "$out" ] && [ "$out" != "UNREACHABLE" ]; then
        real_conflicts=$(echo "$out" | while read -r unit name kind files; do
            [ "$kind" = "CONFLICT" ] || continue
            case " $SHADOW_CONFLICT_ALLOW " in *" $unit:$name "*) continue ;; esac
            echo x
        done)
        [ -n "$real_conflicts" ] && shadowed=1
        echo "$out" | while read -r unit name kind files; do
            case "$kind" in
                CONFLICT)
                    case " $SHADOW_CONFLICT_ALLOW " in
                        *" $unit:$name "*) printf "  %-14s %s: %s (deliberate override, allowlisted) in:%s\n" "$h" "$unit" "$name" "$files" ;;
                        *) printf "  %-14s %s: %s CONFLICTING values across:%s\n" "$h" "$unit" "$name" "$files" ;;
                    esac ;;
                redundant) printf "  %-14s %s: %s (same value) in:%s\n" "$h" "$unit" "$name" "$files" ;;
            esac
        done | awk -v host="$h" '{ if ($0 ~ /CONFLICTING/) conflicts[++c]=$0; else redundant++ }
                    END { for (i=1;i<=c;i++) print conflicts[i]
                          if (redundant) printf "  %-14s %d same-value duplicate assignment(s) (informational)\n", host, redundant }'
    fi
done
if [ "$shadowed" -eq 0 ]; then
    echo "  no variable is set with differing values across EnvironmentFiles"
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
# The fleet nodes have no DNS of their own, so without AITBC_NODE*_HOST set
# these fall back to the bare names and will read UNREACHABLE. That is the
# honest outcome -- better than a hardcoded address that is wrong elsewhere.
declare -A RPC_ENDPOINTS=(
    [node0]="http://${NODE0_HOST:-node0}:8202/rpc/status"
    [node1]="http://${NODE1_HOST:-node1}:8202/rpc/status"
    [node2]="http://${NODE2_HOST:-node2}:8202/rpc/status"
    [hub]="https://hub.${AITBC_FLEET_DOMAIN}/rpc/status"
    [hub1]="https://hub1.${AITBC_FLEET_DOMAIN}/rpc/status"
    [${AITBC_HUB_ALIAS:-_unset_hub_alias}]="https://hub.${AITBC_FLEET_DOMAIN}/rpc/status"
    [${AITBC_HUB1_ALIAS:-_unset_hub1_alias}]="https://hub1.${AITBC_FLEET_DOMAIN}/rpc/status"
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
   && [ "$shadowed" -eq 0 ] && [ "$eff_drift" -eq 0 ] && [ "$faucet_bad" -eq 0 ] \
   && [ "$mesh_bad" -eq 0 ]; then
    echo "No drift across: $HOSTS"
    exit 0
else
    echo "DRIFT DETECTED — differing/malformed values or chain divergence above"
    exit 1
fi
