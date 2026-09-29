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
# (Since 2026-09-27 the per-validator production flags live in node.env —
# which intentionally overrides the shared blockchain.env `false` — and each
# validator's signing key lives only in validator-secrets.env, the last file
# in the EnvironmentFiles list, so any VALIDATOR_KEYS/PROPOSER_KEY in earlier
# unit files is a dead shadow by design.)
SHADOW_CONFLICT_ALLOW="${SHADOW_CONFLICT_ALLOW:-aitbc-blockchain-rpc:ENABLE_BLOCK_PRODUCTION aitbc-blockchain-rpc:BLOCK_PRODUCTION_CHAINS aitbc-blockchain-rpc:GOSSIP_BACKEND aitbc-blockchain-node:ENABLE_BLOCK_PRODUCTION aitbc-blockchain-node:BLOCK_PRODUCTION_CHAINS aitbc-blockchain-node:VALIDATOR_KEYS aitbc-blockchain-node:PROPOSER_KEY aitbc-blockchain-rpc:VALIDATOR_KEYS aitbc-blockchain-rpc:PROPOSER_KEY}"

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
        # 8s, same as the env probes below: the jump-host candidates can take
        # ~2s to answer on a cold connection and a tighter timeout here would
        # silently skip every ssh section (including the digest monitor).
        got=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$cand" 'hostname -s' 2>/dev/null || true)
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
STATE_TRANSITION_V8_HEIGHT STATE_TRANSITION_V9_HEIGHT \
ESCROW_RELEASE_ADDRESS ESCROW_SETTLEMENT_AUTHORITY BRIDGE_RELEASE_AUTHORITY \
SYNC_STATE_ROOT_VALIDATION_ENABLED BOND_ESCROW_ADDRESS BOND_BURN_ADDRESS"

drift=0
shape_bad=0
shadowed=0
eff_drift=0
faucet_bad=0
mesh_bad=0
val_bad=0
dig_bad=0
wallet_bad=0
tag_bad=0
bridge_bad=0

# Fallback digest spec for control hosts without an importable repo
# checkout. Generated by scripts/monitoring/state-digest-spec.py; the
# blockchain-node test suite (test_fleet_digest_spec.py) asserts it stays
# in lockstep with aitbc_chain.state.block_deltas — never edit by hand.
DIGEST_SPEC_FALLBACK='{"addr_cols":["address","agent_wallet","allocated_by","buyer","claimed_by","client_id","creator_address","deployer","initiator","member_address","owner","participant","proposer","proposer_address","provider","recipient","registered_by","sender","staker_address","submitter_address","user_address","verified_by","voter_address","winner_address"],"dup_hard":["governance_vote"],"dupkeys":{"bond":{"addr":["provider"],"key":["bond_id"]},"bridge_validators":{"addr":["address"],"key":["address","epoch"]},"governance_vote":{"addr":["voter_address"],"key":["proposal_id","voter_address"]},"stake":{"addr":["address"],"key":["id"]}},"json_drop":{"envelope":["chain_id","tx_hash","value"]},"json_drop_falsy":{"envelope":["signature"]},"tables":{"account":{"allow":null,"class":"consensus"},"agent_identity":{"allow":null,"class":"service"},"agent_stake":{"allow":null,"class":"service"},"agent_stake_memo":{"allow":null,"class":"service"},"block":{"allow":null,"class":"consensus"},"block_state_delta":{"allow":null,"class":"service"},"bond":{"allow":null,"class":"consensus"},"bounty_contract":{"allow":null,"class":"service"},"bounty_submission":{"allow":null,"class":"service"},"bridge_block_header":{"allow":null,"class":"service"},"bridge_validators":{"allow":null,"class":"service"},"chain_parameter":{"allow":null,"class":"consensus"},"chain_parameter_history":{"allow":null,"class":"consensus"},"consensus_state":{"allow":null,"class":"service"},"cross_chain_escrows":{"allow":null,"class":"service"},"cross_chain_swap":{"allow":null,"class":"service"},"cross_chain_transfer":{"allow":["amount","asset","recipient","sender","source_chain","source_tx_hash","target_chain","transfer_id"],"class":"watch"},"edge_node_registration":{"allow":null,"class":"service"},"escrow":{"allow":null,"class":"service"},"escrow_proofs":{"allow":null,"class":"service"},"governance_proposal":{"allow":null,"class":"service"},"governance_vote":{"allow":null,"class":"service"},"gpu_allocation":{"allow":null,"class":"consensus"},"gpu_registration":{"allow":null,"class":"consensus"},"htlc_swaps":{"allow":null,"class":"service"},"ipfs_subscription":{"allow":null,"class":"consensus"},"liquidity_distribution":{"allow":null,"class":"consensus"},"liquidity_pool":{"allow":null,"class":"consensus"},"liquidity_stake":{"allow":null,"class":"consensus"},"mempool":{"allow":null,"class":"service"},"receipt":{"allow":null,"class":"consensus"},"smart_contract":{"allow":null,"class":"service"},"stake":{"allow":null,"class":"aux"},"transaction":{"allow":null,"class":"consensus"}},"volatile":["allocated_at","allocation_id","claimed_at","completed_at","confirm_time","confirmed_at","created_at","deployed_at","executed_at","id","last_distribution_at","lock_time","locked_at","locked_until","received_at","recorded_at","refunded_at","registered_at","released_at","settled_at","stake_id","timestamp","unbonding_at","updated","updated_at","verified_at"]}'
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

echo "=== validator key integrity (one own key per validator, disjoint across hosts) ==="
# 2026-09-27: the fleet had silently centralised block production — hub held
# all four validator keys in VALIDATOR_KEYS and signed every block in every
# validator's name while the followers' maps were {} and their production was
# disabled (regression introduced during the Sep 9-13 env consolidation, live
# since). Assert per validator: exactly one map entry, whose key derives to
# that host's own PROPOSER_ID, present in VALIDATOR_SET; production enabled on
# validators and off on node0; no validator address held by two hosts. The
# key never leaves its host — derivation runs there, only booleans return.
VALIDATORS="hub hub1 node1 node2"
val_bad=0
declare -A SEEN_ADDRS
# Non-secret checker script staged on each host; the process environ is piped
# straight through stdin — never written to a file (environ contains keys).
VCHECK=$(cat <<'PYEOF'
import sys, json
env = {}
for item in sys.stdin.buffer.read().decode("utf-8", "replace").split("\0"):
    if "=" in item:
        k, v = item.split("=", 1)
        env[k] = v
keys = json.loads(env.get("VALIDATOR_KEYS") or "{}")
propid = env.get("PROPOSER_ID", "")
vs = {v["address"] for v in json.loads(env.get("VALIDATOR_SET") or "[]")}
prod = env.get("ENABLE_BLOCK_PRODUCTION", "")
wins = env.get("CONSENSUS_PROPOSER_ROUND_SECONDS", "")
from eth_keys import keys as ek
derived = {}
for a, k in keys.items():
    try:
        derived[a] = (ek.PrivateKey(bytes.fromhex(k.removeprefix("0x"))).public_key.to_checksum_address() == a)
    except Exception:
        derived[a] = False
print("map_addrs=" + ",".join(sorted(keys)))
print("all_derive=" + str(all(derived.values())))
print("propid=" + propid)
print("propid_in_set=" + str(propid in vs))
print("keys_in_set=" + str(all(a in vs for a in keys)))
print("prod=" + prod)
print("window=" + wins)
PYEOF
)
VCHECK_B64=$(printf '%s' "$VCHECK" | base64 -w0)
for h in $VALIDATORS node0; do
    res=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        "pid=\$(systemctl show -p MainPID --value aitbc-blockchain-node 2>/dev/null); \
         if [ -z \"\$pid\" ] || [ \"\$pid\" = 0 ]; then echo NOTRUNNING; exit; fi; \
         cd /opt/aitbc && sudo cat /proc/\$pid/environ | venv/bin/python -c \"\$(echo '$VCHECK_B64' | base64 -d)\" 2>/dev/null; rc=\$?; [ \$rc -ne 0 ] && echo DERIVEFAIL; \
         grep -icE '^validator_keys=' /etc/aitbc/blockchain.env 2>/dev/null | sed 's/^/bcenv_keys=/'" 2>/dev/null || echo "UNREACHABLE")
    case "$res" in
        UNREACHABLE*|NOTRUNNING*|DERIVEFAIL*|"")
            val_bad=1; printf "  %-6s %s\n" "$h" "${res:-NO OUTPUT}"; continue ;;
    esac
    eval "$res"
    n_keys=$(echo "$map_addrs" | tr "," "\n" | grep -c . || true)
    problems=""
    case $h in
        node0)
            [ "$prod" = "false" ] || problems="$problems production=$prod (want false)"
            [ -z "$map_addrs" ] || problems="$problems holds validator keys"
            ;;
        *)
            [ "$prod" = "true" ] || problems="$problems production=$prod (want true)"
            [ "$n_keys" = 1 ] || problems="$problems holds $n_keys keys (want exactly 1)"
            [ "$all_derive" = "True" ] || problems="$problems key does not derive to its map address"
            [ "$map_addrs" = "$propid" ] || problems="$problems map addr $map_addrs != PROPOSER_ID $propid"
            [ "$propid_in_set" = "True" ] || problems="$problems PROPOSER_ID not in VALIDATOR_SET"
            [ "$keys_in_set" = "True" ] || problems="$problems key addr not in VALIDATOR_SET"
            ;;
    esac
    [ -n "$window" ] && problems="$problems CONSENSUS_PROPOSER_ROUND_SECONDS=$window (want unset/derived)"
    # pydantic also reads blockchain.env directly — a VALIDATOR_KEYS line there
    # would apply without appearing in the process environ.
    [ "${bcenv_keys:-0}" != "0" ] && problems="$problems VALIDATOR_KEYS present in blockchain.env"
    for a in ${map_addrs//,/ }; do
        if [ -n "${SEEN_ADDRS[$a]:-}" ]; then
            problems="$problems key $a ALSO HELD by ${SEEN_ADDRS[$a]}"
        else
            SEEN_ADDRS[$a]=$h
        fi
    done
    if [ -n "$problems" ]; then
        val_bad=1
        printf "  %-6s FAIL:%s\n" "$h" "$problems"
    elif [ "$h" = node0 ]; then
        printf "  %-6s ok: holds no validator keys, prod=%s\n" "$h" "$prod"
    else
        printf "  %-6s ok: own key only, in set, prod=%s\n" "$h" "$prod"
    fi
done
if [ "$val_bad" -eq 0 ]; then
    echo "  ok: each validator holds exactly its own key; no address duplicated"
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
EFF_VARS="$VARS GOSSIP_BACKEND GOSSIP_MESH_PEER_URLS \
MULTI_VALIDATOR_CONSENSUS_ENABLED ENABLE_BLOCK_PRODUCTION BLOCK_PRODUCTION_CHAINS \
CONSENSUS_PROPOSER_ROUND_SECONDS PROPOSER_ID VALIDATOR_SET"
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
            # These are legitimately per-host: peer lists omit the host itself,
            # PROPOSER_ID is the validator's own identity, and production flags
            # differ validators-vs-node0 by design. The validator-integrity
            # section asserts their actual correctness instead.
            case "$var" in
                GOSSIP_MESH_PEER_URLS|PROPOSER_ID|ENABLE_BLOCK_PRODUCTION|BLOCK_PRODUCTION_CHAINS) ;;
                *) eff_drift=1 ;;
            esac
        fi
    done
done
if [ "$eff_drift" -eq 0 ]; then
    echo "  no effective-env drift in consensus variables"
fi

echo "=== wallet daemon URL (loopback or unset — the daemon is a signing surface) ==="
# The hub /w/ edge route is removed by design; wallet daemons are local-only.
# The CLI reads wallet_daemon_url from ~/.aitbc.yaml, scripts read
# WALLET_DAEMON_URL from /etc/aitbc/*.env — every effective value on every
# host must be loopback. node0 drifted onto a stale remote /w/ URL once and
# the failure went unnoticed; this makes the rule checkable.
for h in $HOSTS; do
    vals=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        "grep -hoE '^[[:space:]]*wallet_daemon_url:[[:space:]]*[^ #]+' /root/.aitbc.yaml /home/*/.aitbc.yaml 2>/dev/null | sed 's/^[^:]*:[[:space:]]*//'; \
         grep -hoE '^WALLET_DAEMON_URL=[^ #]+' /etc/aitbc/*.env 2>/dev/null | cut -d= -f2-" \
        2>/dev/null || echo "UNREACHABLE")
    if [ "$vals" = "UNREACHABLE" ]; then
        wallet_bad=1
        printf "  %-14s UNREACHABLE\n" "$h"
        continue
    fi
    badvals=""
    while IFS= read -r v; do
        [ -z "$v" ] && continue
        case "$v" in
            http://127.0.0.1*|http://localhost*|http://\[::1\]*|https://127.0.0.1*|https://localhost*|https://\[::1\]*) ;;
            *) badvals="$badvals $v" ;;
        esac
    done <<< "$vals"
    if [ -n "$badvals" ]; then
        wallet_bad=1
        printf "  %-14s FAIL: non-loopback wallet daemon URL(s):%s\n" "$h" "$badvals"
    else
        printf "  %-14s ok (loopback or unset)\n" "$h"
    fi
done

echo "=== running commit vs latest tag (every fleet deploy gets a tag) ==="
# Releases are tagged at the deploy commit. A host whose HEAD does not
# contain the latest tag's commit missed the rollout.
latest_tag=$(git -C "$(dirname "$0")/../.." tag --sort=-v:refname 2>/dev/null | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1)
if [ -z "$latest_tag" ]; then
    echo "  NOTE: no version tags in this clone — section skipped"
else
    latest_tag_commit=$(git -C "$(dirname "$0")/../.." rev-list -n1 "$latest_tag")
    printf "  latest tag: %s (%.10s)\n" "$latest_tag" "$latest_tag_commit"
    for h in $HOSTS; do
        res=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
            "cd /opt/aitbc 2>/dev/null && head=\$(git rev-parse HEAD 2>/dev/null) && \
             if git merge-base --is-ancestor '$latest_tag_commit' \"\$head\" 2>/dev/null; then echo \"\$head ON\"; else echo \"\$head BEHIND\"; fi" \
            2>/dev/null || echo "UNREACHABLE")
        case "$res" in
            UNREACHABLE|"") tag_bad=1; printf "  %-14s UNREACHABLE\n" "$h" ;;
            *" ON")   printf "  %-14s %.10s on %s\n" "$h" "${res%% *}" "$latest_tag" ;;
            *" BEHIND") tag_bad=1; printf "  %-14s %.10s BEHIND %s — missed rollout\n" "$h" "${res%% *}" "$latest_tag" ;;
            *) tag_bad=1; printf "  %-14s %s\n" "$h" "$res" ;;
        esac
    done
fi

echo "=== bridge deposit monitor check (exactly one inbound watcher fleet-wide) ==="
# Two independent watchers paid the same deposit twice once a second key
# existed (2026-09-29): the standalone aitbc-bridge-monitor on hub is the
# canonical inbound leg; the wallet's embedded watcher is gated by
# BRIDGE_DEPOSIT_MONITOR_ENABLED (default off) and must never hold a payout
# key. Count live monitors across the fleet; expect exactly one.
live=0
for h in $HOSTS; do
    res=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        'sa=$(systemctl is-active aitbc-bridge-monitor 2>/dev/null || echo missing)
         flag=""
         pid=$(systemctl show -p MainPID --value aitbc-wallet 2>/dev/null)
         if [ -n "$pid" ] && [ "$pid" != "0" ]; then
             flag=$(tr "\0" "\n" < /proc/$pid/environ 2>/dev/null | sed -n "s/^BRIDGE_DEPOSIT_MONITOR_ENABLED=//p" | tail -1)
         fi
         printf "%s %s\n" "$sa" "${flag:-unset}"' \
        2>/dev/null || echo "UNREACHABLE")
    if [ "$res" = "UNREACHABLE" ] || [ -z "$res" ]; then
        bridge_bad=1
        printf "  %-14s UNREACHABLE\n" "$h"
        continue
    fi
    sa=${res%% *}
    flag=${res##* }
    cnt=0
    [ "$sa" = "active" ] && cnt=1
    [ "$flag" = "true" ] && cnt=$((cnt + 1))
    live=$((live + cnt))
    printf "  %-14s aitbc-bridge-monitor=%s wallet-flag=%s\n" "$h" "$sa" "$flag"
done
if [ "$live" -ne 1 ]; then
    bridge_bad=1
    echo "  FAIL: $live live deposit monitors; expected exactly 1 (the standalone service)"
else
    echo "  ok: exactly one live deposit monitor"
fi

echo "=== bridge monitor payout config (hub — payout vars that set AIT amounts) ==="
# AIT_USD_FIXED_PRICE directly sizes payouts; the payout address, minimums,
# confirmation depth and float floor are shown so a config drift is visible
# in the report instead of only surfacing as a bad payment.
for var in BRIDGE_PAYOUT_ADDRESS AIT_USD_FIXED_PRICE BRIDGE_CONFIRMATIONS BRIDGE_LOW_FLOAT_AIT MIN_ETH_DEPOSIT BRIDGE_MIN_DEPOSIT_AIT; do
    val=$(running_env "${AITBC_HUB_ALIAS:-hub}" aitbc-bridge-monitor "$var" "")
    printf "  %-28s %s\n" "$var" "${val:-<unset>}"
done

echo "=== ETH_WALLET_PRIVATE_KEY carriers (should be the withdrawal payer only) ==="
# The key controls the bridge wallet's ETH: a holder other than
# aitbc-wallet (the withdrawal payer) is exposure. Print carrier unit names
# only — never key material.
for h in $HOSTS; do
    carriers=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "${RESOLVED[$h]:-$h}" \
        'for p in /proc/[0-9]*; do
             tr "\0" "\n" < "$p/environ" 2>/dev/null | grep -q "^ETH_WALLET_PRIVATE_KEY=" || continue
             pid=${p#/proc/}
             unit=$(systemctl status "$pid" 2>/dev/null | sed -n "s/^.*● //;s/ - .*//p" | head -1)
             [ -z "$unit" ] && unit=$(cat "$p/comm" 2>/dev/null)
             echo "$unit"
         done | sort -u' \
        2>/dev/null || echo "UNREACHABLE")
    if [ "$carriers" = "UNREACHABLE" ]; then
        bridge_bad=1
        printf "  %-14s UNREACHABLE\n" "$h"
        continue
    fi
    printf "  %-14s %s\n" "$h" "$(echo "${carriers:-<none>}" | paste -sd, -)"
    echo "$carriers" | grep -v "^$" | grep -qv "^aitbc-wallet" && {
        bridge_bad=1
        echo "  FAIL: $h has ETH key carriers beyond the withdrawal payer"
    }
done

echo "=== chain state digests (consensus tables must match, aux must converge) ==="
# v0.25.8: semantic per-table digests across the fleet. The classification
# lives in aitbc_chain.state.block_deltas (CONSENSUS_STATE_TABLES,
# SERVICE_STATE_TABLES, AUX_SHIPPED_TABLES, CONSENSUS_SENSITIVE_WATCH,
# VOLATILE_DIGEST_COLUMNS, DIGEST_ADDRESS_COLUMNS, DIGEST_COLUMN_ALLOWLIST)
# — consensus and aux-shipped tables must produce identical digests on every
# host; a diff means state drift, not opinion. Service tables and the
# consensus-bound watch member (cross_chain_transfer, which feeds
# block.bridge_state_root from service-local rows) are digested but their
# divergence is legitimate and prints informational/WARN only.
#
# Mechanics: state-digest-spec.py generates the spec JSON once here (same
# spec on all hosts even mid-deploy when checkouts differ — else the
# comparison itself drifts); the sibling state-digest-remote.py is piped to
# each host and hashes its chain.db read-only. Rows compare as sorted hash
# multisets — immune to row order, autoincrement ids, wall-clock stamps and
# address casing. The aux natural-key case-dup scan (the governance-vote
# twin pattern) runs in the same pass.
#
# This section never writes to any table and never touches sync settings.
dig_bad=0
DIGEST_DIR="$(cd "$(dirname "$0")" && pwd)"
DIGEST_SPEC=""

# Spec resolution order: fresh-generate from a checkout that has the
# classification constants (correct even when the embedded copy is stale),
# else the embedded fallback kept in parity by test_fleet_digest_spec.py.
if [ -f "$DIGEST_DIR/state-digest-spec.py" ]; then
    for py in "${AITBC_REPO:-$(dirname "$(dirname "$DIGEST_DIR")")}/venv/bin/python" python3; do
        [ -x "$py" ] || command -v "$py" >/dev/null 2>&1 || continue
        cand=$("$py" "$DIGEST_DIR/state-digest-spec.py" 2>/dev/null || true)
        case "$cand" in
            "{"*) DIGEST_SPEC="$cand"; break ;;
        esac
    done
fi
if [ -z "$DIGEST_SPEC" ]; then
    DIGEST_SPEC="$DIGEST_SPEC_FALLBACK"
fi

if [ ! -f "$DIGEST_DIR/state-digest-remote.py" ]; then
    echo "  SKIPPED: state-digest-remote.py not found next to this script"
elif [ -z "$DIGEST_SPEC" ]; then
    echo "  SKIPPED: no digest spec (generator failed and fallback empty)"
else
    DIGEST_WORK=$(mktemp -d)
    trap 'rm -rf "$DIGEST_WORK"' EXIT
    SPEC_B64=$(printf '%s' "$DIGEST_SPEC" | base64 -w0)
    # Empty spec = height probe only (cheap): the remote still resolves its
    # production chain.db and answers its sealed height, so the fleet-common
    # bound can be computed before the real digest pass. The proposer is
    # routinely one block ahead when the probe lands — without the bound its
    # block/transaction digests flap on timing, not drift.
    EMPTY_SPEC_B64=$(printf '%s' '{"tables":{},"volatile":[],"addr_cols":[],"dupkeys":{}}' | base64 -w0)
    REMOTE_B64=$(base64 -w0 "$DIGEST_DIR/state-digest-remote.py")

    # digest_probe <host> <spec_b64> <max_height> — one remote run.
    digest_probe() {
        ssh -o ConnectTimeout=10 -o BatchMode=yes "${RESOLVED[$1]:-$1}" \
            "pid=\$(systemctl show -p MainPID --value aitbc-blockchain-node 2>/dev/null)
             chain=''
             if [ -n \"\$pid\" ] && [ \"\$pid\" != 0 ]; then
                 if [ -r /proc/\$pid/environ ]; then tr '\0' '\n' < /proc/\$pid/environ; else sudo -n tr '\0' '\n' < /proc/\$pid/environ 2>/dev/null; fi \
                     | grep -i '^chain_id=' | tail -1 | cut -d= -f2- > /tmp/.digest-chain.\$\$
                 chain=\$(cat /tmp/.digest-chain.\$\$ 2>/dev/null); rm -f /tmp/.digest-chain.\$\$
             fi
             db=''
             [ -n \"\$chain\" ] && [ -f \"/var/lib/aitbc/data/\$chain/chain.db\" ] && db=\"/var/lib/aitbc/data/\$chain/chain.db\"
             if [ -z \"\$db\" ]; then
                 dbs=\$(ls /var/lib/aitbc/data/*/chain.db 2>/dev/null)
                 [ \"\$(echo \"\$dbs\" | grep -c .)\" = 1 ] && db=\$dbs
             fi
             [ -n \"\$db\" ] || { echo NODB; exit 0; }
             chain=\${chain:-\$(basename \$(dirname \"\$db\"))}
             echo '$2' | base64 -d > /tmp/.digest-spec.\$\$
             spec=\$(cat /tmp/.digest-spec.\$\$); rm -f /tmp/.digest-spec.\$\$
             base64 -d <<'PYEOF' | python3 - \"\$db\" \"\$chain\" \"\$spec\" \"$3\"
$REMOTE_B64
PYEOF" \
            2>/dev/null || echo "UNREACHABLE"
    }

    dig_hosts=0
    min_height=""
    for h in $HOSTS; do
        out=$(digest_probe "$h" "$EMPTY_SPEC_B64" -1)
        case "$out" in
            '{"max_height"'*)
                # No .json suffix: the compare step globs "$DIGEST_WORK/*.json"
                # and would treat a probe file as an eleventh host.
                printf '%s' "$out" > "$DIGEST_WORK/$h.height"
                mh=$(printf '%s' "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["max_height"])' 2>/dev/null || echo "")
                if [ -n "$mh" ] && { [ -z "$min_height" ] || [ "$mh" -lt "$min_height" ]; }; then
                    min_height=$mh
                fi ;;
            NODB) printf '  %-14s no chain.db under /var/lib/aitbc/data\n' "$h" ;;
            *)    printf '  %-14s height probe failed (%s)\n' "$h" "$(echo "$out" | head -c 120)" ;;
        esac
    done
    if [ -n "$min_height" ]; then
        echo "  digest bound: common prefix height $min_height"
    fi
    for h in $HOSTS; do
        out=$(digest_probe "$h" "$SPEC_B64" "${min_height:--1}")
        case "$out" in
            *'"tables"'*) printf '%s' "$out" > "$DIGEST_WORK/$h.json"; dig_hosts=$((dig_hosts + 1)) ;;
            NODB) : ;;  # already reported in the height pass
            *)    printf '  %-14s digest probe failed (%s)\n' "$h" "$(echo "$out" | head -c 120)" ;;
        esac
    done
    if [ "$dig_hosts" -lt 2 ]; then
        echo "  SKIPPED: fewer than 2 hosts produced a digest"
    else
        DIGEST_SPEC="$DIGEST_SPEC" python3 - "$DIGEST_WORK" <<'CMPEOF' || dig_bad=1
import json, sys, os
dup_hard = set(json.loads(os.environ.get("DIGEST_SPEC", "{}")).get("dup_hard", []))
work = sys.argv[1]
data = {}
for f in sorted(os.listdir(work)):
    if f.endswith(".json"):
        data[f[:-5]] = json.load(open(os.path.join(work, f)))
hosts = sorted(data)
tables = sorted({t for h in hosts for t in data[h]["tables"]})
fails, warns = [], []
hdr = "  " + "table".ljust(26) + "class".ljust(10) + "  ".join(h.center(18) for h in hosts)
print(hdr)
for t in tables:
    cls = ""
    cells, digs = [], set()
    for h in hosts:
        e = data[h]["tables"].get(t, {})
        cls = e.get("class", "?")
        if "digest" in e:
            cells.append(("%s:%s" % (e["digest"][:8], e.get("rows", "?"))))
            digs.add(e["digest"])
        else:
            cells.append("-" + ",".join(k for k in e if k != "class"))
            digs.add(None)
    differing = len(digs) > 1
    if cls in ("consensus", "aux") and differing:
        fails.append(t)
    elif cls == "watch" and differing:
        warns.append(t)
    show = differing or cls in ("consensus", "aux", "watch")
    if show:
        flag = "  <-- DIFFERS" if differing else ""
        print("  " + t.ljust(26) + cls.ljust(10) + "  ".join(c.center(18) for c in cells) + flag)
for t in fails:
    print("  FAIL: %s (%s) digests differ" % (t, data[hosts[0]]["tables"][t]["class"]))
for t in warns:
    print("  WARN: %s watch-table drift (service-local rows bound to bridge root)" % t)
for h in hosts:
    for t, groups in (data[h].get("dupes") or {}).items():
        sev = "FAIL" if (data[h]["tables"].get(t, {}).get("class") in ("consensus", "aux") or t in dup_hard) else "WARN"
        (fails if sev == "FAIL" else warns).append(t)
        for g in groups:
            print("  %s: %s case-duplicate natural key on %s: %s" % (sev, t, h, g))
if fails:
    sys.exit(1)
CMPEOF
        if [ "$dig_bad" -eq 0 ]; then
            echo "  ok: consensus + aux tables identical on $dig_hosts hosts"
        fi
    fi
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
# Each host gets a list of endpoints tried in order: the LAN RPC when
# AITBC_NODE*_HOST names a reachable address, and always the public
# https://<host>.<domain> edge endpoint (which a node cannot use to reach
# *itself* — the edge has no hairpin NAT — hence the LAN first).
declare -A RPC_ENDPOINTS=(
    [node0]="${NODE0_HOST:+http://${NODE0_HOST}:8202/rpc/status} https://node0.${AITBC_FLEET_DOMAIN}/rpc/status"  # check-ports: ignore — 8202 is the LAN blockchain RPC, not the edge service
    [node1]="${NODE1_HOST:+http://${NODE1_HOST}:8202/rpc/status} https://node1.${AITBC_FLEET_DOMAIN}/rpc/status"  # check-ports: ignore — 8202 is the LAN blockchain RPC, not the edge service
    [node2]="${NODE2_HOST:+http://${NODE2_HOST}:8202/rpc/status} https://node2.${AITBC_FLEET_DOMAIN}/rpc/status"  # check-ports: ignore — 8202 is the LAN blockchain RPC, not the edge service
    [hub]="https://hub.${AITBC_FLEET_DOMAIN}/rpc/status"
    [hub1]="https://hub1.${AITBC_FLEET_DOMAIN}/rpc/status"
    [${AITBC_HUB_ALIAS:-_unset_hub_alias}]="https://hub.${AITBC_FLEET_DOMAIN}/rpc/status"
    [${AITBC_HUB1_ALIAS:-_unset_hub1_alias}]="https://hub1.${AITBC_FLEET_DOMAIN}/rpc/status"
)
conv_bad=0
sample_heads() {
    for h in $HOSTS; do
        out=""
        for url in ${RPC_ENDPOINTS[$h]:-}; do
            [ -n "$out" ] && break
            out=$(curl -s -m 6 -k "$url" 2>/dev/null | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(str(d["height"]) + "|" + d["last_block_hash"][:16])
except Exception:
    pass' 2>/dev/null)
        done
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
   && [ "$mesh_bad" -eq 0 ] && [ "$val_bad" -eq 0 ] && [ "$dig_bad" -eq 0 ] \
   && [ "$wallet_bad" -eq 0 ] && [ "${tag_bad:-0}" -eq 0 ] && [ "$bridge_bad" -eq 0 ]; then
    echo "No drift across: $HOSTS"
    exit 0
else
    echo "DRIFT DETECTED — differing/malformed values or chain divergence above"
    exit 1
fi
