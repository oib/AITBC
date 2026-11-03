#!/bin/bash
# Update deployed AITBC systemd units to run as the unified aitbc user.
# Run after create_aitbc_user.sh.
#
# This used to sed-rewrite every *.service under /opt/aitbc/apps — the
# tracked repo files — dirtying the working tree and forcing User=aitbc
# onto units that deliberately run as someone else (#883):
#   aitbc-ops-signer.service  runs as root (signs ops transactions)
#   aitbc-hermes-agent.service runs as aitbc-hermes
#
# The repo files are already correct; they are what gets installed. What
# this script actually needs to fix is units already deployed under
# /etc/systemd/system — and only the ones on the allow-list.

set -euo pipefail

SYSTEMD_DIR="${AITBC_SYSTEMD_DIR:-/etc/systemd/system}"
LIB_DIR="${AITBC_LIB_DIR:-/var/lib/aitbc}"

# Units meant to run as aitbc — the set of apps/*.service whose tracked
# User= is already aitbc. Deliberate non-aitbc units are absent by design;
# tests/unit/test_unify_service_users.py keeps this list in sync.
AITBC_UNITS=(
    aitbc-agent-coordinator.service
    aitbc-ai.service
    aitbc-learning.service
    aitbc-modality-optimization.service
    aitbc-multimodal.service
    aitbc-api-gateway.service
    aitbc-blockchain-event-bridge.service
    aitbc-blockchain-explorer.service
    aitbc-blockchain-node.service
    aitbc-blockchain-p2p.service
    aitbc-blockchain-rpc.service
    aitbc-bridge-monitor.service
    aitbc-coordinator-api.service
    aitbc-edge.service
    aitbc-exchange.service
    aitbc-ffmpeg.service
    aitbc-governance.service
    aitbc-gpu.service
    aitbc-ipfs.service
    aitbc-island-ipfs.service
    aitbc-market.service
    aitbc-miner.service
    aitbc-monitoring.service
    aitbc-ollama-gate.service
    aitbc-pool-hub.service
    aitbc-trading.service
    aitbc-wallet.service
    aitbc-whisper.service
)

echo "Updating deployed AITBC units in $SYSTEMD_DIR to the unified aitbc user..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root"
    exit 1
fi

# Check if aitbc user exists
if ! id aitbc > /dev/null 2>&1; then
    echo "Error: aitbc user does not exist. Run create_aitbc_user.sh first."
    exit 1
fi

is_allowlisted() {
    local name="$1" unit
    for unit in "${AITBC_UNITS[@]}"; do
        [ "$unit" = "$name" ] && return 0
    done
    return 1
}

CHANGES=0
SKIPPED=0
LEFT=0

for service_file in "$SYSTEMD_DIR"/aitbc-*.service; do
    [ -e "$service_file" ] || continue
    name="$(basename "$service_file")"

    if ! is_allowlisted "$name"; then
        echo "  $name: not in the aitbc allow-list — leaving User= unchanged"
        LEFT=$((LEFT + 1))
        continue
    fi

    if grep -q "^User=aitbc" "$service_file"; then
        echo "  $name: already User=aitbc, skipping"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    if grep -q "^User=" "$service_file"; then
        sed -i 's/^User=.*/User=aitbc/' "$service_file"
    else
        sed -i '/^\[Service\]/a User=aitbc' "$service_file"
    fi
    if grep -q "^Group=" "$service_file"; then
        sed -i 's/^Group=.*/Group=aitbc/' "$service_file"
    else
        sed -i '/^User=/a Group=aitbc' "$service_file"
    fi
    echo "  $name: updated to User=aitbc"
    CHANGES=$((CHANGES + 1))
done

echo ""
echo "Fixing runtime file ownership..."

# Island credentials belong to the aitbc runtime user.
if [ -f "$LIB_DIR/island_credentials.json" ]; then
    chown aitbc:aitbc "$LIB_DIR/island_credentials.json" 2>/dev/null || true
    chmod 0600 "$LIB_DIR/island_credentials.json"
    echo "  Island credentials: aitbc:aitbc 0600"
fi

# /var/lib/aitbc must remain writable by aitbc for api_keys.json.lock.
# Non-recursive: existing data keeps its owner (#882).
chown root:aitbc "$LIB_DIR" 2>/dev/null || true
chmod 2775 "$LIB_DIR" 2>/dev/null || true

# Root-only secrets (e.g. /etc/aitbc/blockchain-secrets.env) are left root:600.
# The CLI now skips env files it cannot read instead of aborting.

echo "Summary:"
echo "  Updated: $CHANGES deployed units"
echo "  Skipped: $SKIPPED (already User=aitbc)"
echo "  Left unchanged: $LEFT (not allow-listed — deliberate non-aitbc units)"
echo ""
echo "Next steps:"
echo "1. Reload systemd: systemctl daemon-reload"
echo "2. Restart services: systemctl restart aitbc-*"
echo "3. Verify services are running: systemctl status aitbc-*"
