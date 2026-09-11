#!/bin/bash

# Deploy blockchain node inside incus container aitbc

set -e

# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
require_deploy_var AITBC_SSH_TARGET "Set it to the ssh alias or user@host of the deployment server."
require_deploy_var AITBC_PUBLIC_HOST "Set it to the public FQDN this deployment is reached on."

# Name of the incus container to deploy into.
AITBC_CONTAINER="${AITBC_CONTAINER:-aitbc}"


echo "🚀 AITBC Deployment in Incus Container"
echo "======================================"
echo "This will deploy inside container: ${AITBC_CONTAINER}"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check that this host can drive incus (see deploy-env.sh). This used to be a
# comparison against one island's hostname, which is an identity check standing
# in for a capability check.
require_container_host

# Check the target container is running.
if ! incus list --format csv -c ns | grep -qx "${AITBC_CONTAINER},RUNNING"; then
    print_warning "Container ${AITBC_CONTAINER} is not running"
    exit 1
fi

# Copy source to container
print_status "Copying source code to container..."
incus exec "${AITBC_CONTAINER}" -- rm -rf /opt/blockchain-node-src 2>/dev/null || true
incus exec "${AITBC_CONTAINER}" -- mkdir -p /opt/blockchain-node-src
# Use the source already on the server
incus file push -r /opt/blockchain-node-src/. "${AITBC_CONTAINER}/opt/blockchain-node-src/"
# Fix the nested directory issue - move everything up one level
incus exec "${AITBC_CONTAINER}" -- sh -c 'if [ -d /opt/blockchain-node-src/blockchain-node-src ]; then mv /opt/blockchain-node-src/blockchain-node-src/* /opt/blockchain-node-src/ && rmdir /opt/blockchain-node-src/blockchain-node-src; fi'

# Copy deployment script to container
print_status "Copying deployment script to container..."
incus file push /opt/deploy-in-container.sh "${AITBC_CONTAINER}/opt/"

# Execute deployment inside container
print_status "Deploying inside container..."
incus exec "${AITBC_CONTAINER}" -- bash /opt/deploy-in-container.sh

# Setup port forwarding on host
#
# The forwarding target used to be a hardcoded container address. It is
# AITBC_DNAT_TARGET now; if it is unset this host forwards nothing and says so,
# rather than installing rules that point at someone else's network.
print_status "Setting up port forwarding on host..."
if [ -n "${AITBC_DNAT_TARGET:-}" ]; then
    iptables -t nat -F PREROUTING 2>/dev/null || true
    iptables -t nat -F POSTROUTING 2>/dev/null || true
    setup_dnat 8202
    setup_dnat 3000
    mkdir -p /etc/iptables
    persist_dnat
else
    echo "NOTE: AITBC_DNAT_TARGET is not set -- the container's ports are NOT" >&2
    echo "      published from this host. Set it to the container's address on" >&2
    echo "      the bridge if they should be." >&2
fi

# Check services
print_status "Checking services in container..."
incus exec "${AITBC_CONTAINER}" -- systemctl status blockchain-node blockchain-rpc nginx --no-pager | grep -E 'Active:|Main PID:'

print_success "✅ Deployment complete!"
echo ""
echo "Services in container ${AITBC_CONTAINER}:"
if [ -n "${AITBC_DNAT_TARGET:-}" ]; then
    echo "  - Blockchain Node RPC: http://${AITBC_DNAT_TARGET}:8202"
    echo "  - Blockchain Explorer: http://${AITBC_DNAT_TARGET}:3000"
    echo ""
fi
echo "External access via this host:"
echo "  - Blockchain Node RPC: http://${AITBC_PUBLIC_HOST}:8202"
echo "  - Blockchain Explorer: http://${AITBC_PUBLIC_HOST}:3000"
