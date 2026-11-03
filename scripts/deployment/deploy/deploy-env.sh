#!/bin/bash
# Shared deployment target configuration.
# Sourced by the deploy/*.sh callers; set -euo pipefail here carries to the
# sourcing shell — every caller already runs set -e, this adds -u/-o pipefail.
set -euo pipefail
#
# These scripts used to hardcode one server's ssh alias and public hostname.
# That tied them to a single deployment and put infrastructure identifiers in a
# public repository. Set them in the environment instead:
#
#   export AITBC_SSH_TARGET=my-host-root       # ssh/scp destination
#   export AITBC_PUBLIC_HOST=aitbc.example.net # public FQDN, for TLS and URLs
#
# Optional:
#
#   export AITBC_DNAT_TARGET=10.0.0.5   # container address to forward ports to,
#                                       # when this host publishes them. Unset
#                                       # means "publish nothing", and the
#                                       # scripts say so rather than going quiet.
#   export AITBC_CONTAINER=aitbc        # incus container name (default: aitbc)
#
# Source this file, then call require_deploy_var for whatever the script needs.

require_deploy_var() {
    local name="$1" hint="$2"
    if [ -z "${!name:-}" ]; then
        echo "ERROR: $name is not set." >&2
        echo "       $hint" >&2
        echo "       See scripts/deployment/deploy/deploy-env.sh" >&2
        exit 1
    fi
}

# Abort unless this host can actually carry out a deployment.
#
# These scripts used to compare `hostname` against the literal names of one
# island's machines. That is an identity check standing in for a capability
# check: it refused to run on any other operator's deployment server, and it
# trusted any host that happened to share the name. Test for what the deploy
# needs instead -- root, and a live systemd to install units into.
require_deploy_capabilities() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: this script installs systemd units and must run as root." >&2
        exit 1
    fi
    if ! command -v systemctl >/dev/null 2>&1 || [ ! -d /run/systemd/system ]; then
        echo "ERROR: no running systemd here -- this is not a deployment server." >&2
        echo "       Run it on the target host, not on a workstation." >&2
        exit 1
    fi
}

# Abort unless this host can drive the container runtime.
require_container_host() {
    if ! command -v incus >/dev/null 2>&1; then
        echo "ERROR: incus is not installed -- this is not the container host." >&2
        exit 1
    fi
    if ! incus list >/dev/null 2>&1; then
        echo "ERROR: cannot talk to incus. Run this on the container host, as a" >&2
        echo "       user that is allowed to drive it." >&2
        exit 1
    fi
}

# Publish a container port from this host with a DNAT rule.
#
# This used to be gated on `hostname = aitbc` and, on every other host, did
# nothing whatsoever -- without a word. The deploy then reported success while
# no traffic was being forwarded at all, which is the worst of the two ways a
# check like this can be wrong. It is explicit now: set AITBC_DNAT_TARGET to the
# address traffic should be forwarded to, and the rules are installed; leave it
# unset and the script says plainly that it is not publishing anything.
#
# Returns non-zero when it forwards nothing, so callers can skip persisting.
setup_dnat() {
    local port="$1"
    local target="${AITBC_DNAT_TARGET:-}"

    if [ -z "$target" ]; then
        echo "NOTE: AITBC_DNAT_TARGET is not set -- port $port is NOT published from" >&2
        echo "      this host. Set it to the container's address if this host is" >&2
        echo "      meant to forward to it." >&2
        return 1
    fi
    if ! command -v iptables >/dev/null 2>&1; then
        echo "ERROR: AITBC_DNAT_TARGET is set but iptables is not installed." >&2
        exit 1
    fi

    # Idempotent -C check / -A add (#885): never flush the table — other
    # deployments' forwarding rules live in it too.
    iptables -t nat -C PREROUTING -p tcp --dport "$port" -j DNAT \
        --to-destination "$target:$port" 2>/dev/null || \
    iptables -t nat -A PREROUTING -p tcp --dport "$port" -j DNAT \
        --to-destination "$target:$port"
    iptables -t nat -C POSTROUTING -p tcp -d "$target" --dport "$port" -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -p tcp -d "$target" --dport "$port" -j MASQUERADE
}

# Persist the nat table, if this host has somewhere to persist it to.
persist_dnat() {
    if [ -d /etc/iptables ]; then
        iptables-save > /etc/iptables/rules.v4
    else
        echo "NOTE: /etc/iptables is absent -- DNAT rules will not survive a reboot." >&2
    fi
}

# #886: five deploy scripts call print_success after a run completes; it was
# defined nowhere, so `set -e` killed each script with exit 127 after a good
# deploy. Defined once here and sourced everywhere it is used.
print_success() {
    GREEN='\033[0;32m'; NC='\033[0m'
    echo -e "${GREEN}[OK]${NC} $1"
}

# #888: the legacy node scripts used to write a working-directory `.env`
# the node never reads — the node reads /etc/aitbc/blockchain.env (or
# AITBC_CHAIN_ENV_FILE). Write the real file with real variables; a node
# meant to produce blocks needs the operator-supplied proposer identity,
# never a clock-derived placeholder.
write_blockchain_env() {
    local db_path="$1" rpc_bind="$2" rpc_port="$3" p2p_bind="$4" p2p_port="$5" gossip="${6:-memory}" gossip_url="${7:-}"
    local chain_id="${AITBC_CHAIN_ID:-ait-devnet}"
    local enable="${AITBC_ENABLE_BLOCK_PRODUCTION:-false}"
    local out="${AITBC_CHAIN_ENV_FILE:-/etc/aitbc/blockchain.env}"
    if [ "${enable}" = "true" ]; then
        : "${AITBC_PROPOSER_ID:?set AITBC_PROPOSER_ID (a 0x validator address) when AITBC_ENABLE_BLOCK_PRODUCTION=true}"
        : "${AITBC_PROPOSER_KEY:?set AITBC_PROPOSER_KEY (the 64-hex private key) when AITBC_ENABLE_BLOCK_PRODUCTION=true}"
    fi
    mkdir -p "$(dirname "$out")"
    {
        echo "CHAIN_ID=${chain_id}"
        echo "DB_PATH=${db_path}"
        echo "RPC_BIND_HOST=${rpc_bind}"
        echo "RPC_BIND_PORT=${rpc_port}"
        echo "P2P_BIND_HOST=${p2p_bind}"
        echo "P2P_BIND_PORT=${p2p_port}"
        echo "ENABLE_BLOCK_PRODUCTION=${enable}"
        echo "MINT_PER_UNIT=1000"
        echo "COORDINATOR_RATIO=0.05"
        echo "GOSSIP_BACKEND=${gossip}"
        if [ -n "${gossip_url}" ]; then
            echo "GOSSIP_BROADCAST_URL=${gossip_url}"
        fi
        if [ "${enable}" = "true" ]; then
            echo "PROPOSER_ID=${AITBC_PROPOSER_ID}"
            echo "PROPOSER_KEY=${AITBC_PROPOSER_KEY}"
        fi
    } > "${out}"
    chmod 0600 "${out}"
    echo "[deploy-env] wrote ${out} (ENABLE_BLOCK_PRODUCTION=${enable})"
}
