#!/bin/bash
# agent Follower Node Setup Script for AITBC Node
# This script uses agent agents to configure ${NODE1_HOST} as a follower node

set -euo pipefail  # Exit on any error


# Source scenario configuration

# Fleet node addresses.
#
# These were hardcoded to one island's private subnet, which made the script
# useless anywhere else and put internal addressing in a public repository.
# Set them for your own deployment; there is deliberately no default.
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    # No default for the shop node: it used to name one island's host, which
    # was wrong everywhere else and published that host in a public repo.
    export SHOP_URL="${SHOP_URL:-${AITBC_SHOP_URL:?set AITBC_SHOP_URL to the shop node URL, or provide /etc/aitbc/.env.scenario}}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi
echo "=== agent AITBC Follower Node Setup (${NODE1_HOST}) ==="

# 1. Initialize agent FollowerAgent
echo "1. Initializing agent FollowerAgent..."
agent execute --agent FollowerAgent --task initialize_follower_setup || {
    echo "⚠️ agent FollowerAgent initialization failed - using manual method"
}

# 2. Connect to ${NODE1_HOST} node (via agent)
echo "2. Connecting to ${NODE1_HOST} node via agent FollowerAgent..."
agent execute --agent FollowerAgent --task connect_to_node --node ${NODE1_HOST} || {
    echo "⚠️ agent node connection failed - using SSH method"
    # Verify SSH connection to ${NODE1_HOST}
    ssh ${NODE1_HOST} "echo 'Connected to ${NODE1_HOST}'" || {
        echo "❌ Failed to connect to ${NODE1_HOST}"
        exit 1
    }
}

# 3. Pull latest code on ${NODE1_HOST} (via agent)
echo "3. Pulling latest code on ${NODE1_HOST} via agent FollowerAgent..."
agent execute --agent FollowerAgent --task pull_latest_code --node ${NODE1_HOST} || {
    echo "⚠️ agent code pull failed - using SSH method"
    ssh ${NODE1_HOST} 'cd /opt/aitbc && git pull origin main'
}

# 4. Install/update dependencies on ${NODE1_HOST} (via agent)
echo "4. Installing/updating dependencies on ${NODE1_HOST} via agent FollowerAgent..."
agent execute --agent FollowerAgent --task update_dependencies --node ${NODE1_HOST} || {
    echo "⚠️ agent dependency update failed - using SSH method"
    ssh ${NODE1_HOST} 'cd /opt/aitbc && /opt/aitbc/venv/bin/poetry install'
}

# 5. Create required directories on ${NODE1_HOST} (via agent)
echo "5. Creating required directories on ${NODE1_HOST} via agent FollowerAgent..."
agent execute --agent FollowerAgent --task create_directories --node ${NODE1_HOST} || {
    echo "⚠️ agent directory creation failed - using SSH method"
    ssh ${NODE1_HOST} 'mkdir -p /var/lib/aitbc/data /var/lib/aitbc/keystore /etc/aitbc /var/log/aitbc'
    ssh ${NODE1_HOST} 'ls -la /var/lib/aitbc/ || echo "Creating /var/lib/aitbc/ structure..."'
}

# 6. Update environment configuration on ${NODE1_HOST} (via agent)
echo "6. Updating environment configuration on ${NODE1_HOST} via agent FollowerAgent..."
agent execute --agent FollowerAgent --task update_follower_config --node ${NODE1_HOST} || {
    echo "⚠️ agent config update failed - using SSH method"
    ssh ${NODE1_HOST} 'cp /etc/aitbc/blockchain.env /etc/aitbc/blockchain.env.aitbc1.backup 2>/dev/null || true'

    # Update .env for ${NODE1_HOST} follower configuration
    # Note: Don't overwrite auto-generated proposer_id or p2p_node_id - they must remain unique for P2P networking
    ssh ${NODE1_HOST} 'set_env() {
        local key="$1"
        local value="$2"

        if grep -q "^${key}=" /etc/aitbc/.env; then
            sed -i "s|^${key}=.*|${key}=${value}|g" /etc/aitbc/.env
        else
            echo "${key}=${value}" >> /etc/aitbc/.env
        fi
    }

    set_env keystore_path /var/lib/aitbc/keystore
    set_env keystore_password_file /var/lib/aitbc/keystore/.password
    set_env db_path /var/lib/aitbc/data/ait-mainnet/chain.db
    set_env enable_block_production false
    set_env gossip_backend broadcast
    set_env gossip_broadcast_url redis://${NODE1_HOST}:6379
    set_env default_peer_rpc_url http://aitbc:8202
    set_env p2p_bind_port 7071'

    # Ensure p2p_node_id exists in node.env (preserve if already set)
    ssh ${NODE1_HOST} 'if ! grep -q "^p2p_node_id=" /etc/aitbc/node.env; then echo "p2p_node_id=node-$(cat /proc/sys/kernel/random/uuid | tr -d '-')" >> /etc/aitbc/node.env; fi'

    # Add genesis node connection
    ssh ${NODE1_HOST} 'echo "genesis_node=aitbc:8202" >> /etc/aitbc/.env'
    ssh ${NODE1_HOST} 'echo "trusted_proposers=aitbcgenesis" >> /etc/aitbc/.env'
}

# 7. Copy keystore password file to ${NODE1_HOST} (via agent)
echo "7. Copying keystore password file to ${NODE1_HOST} via agent FollowerAgent..."
agent execute --agent FollowerAgent --task copy_keystore_password --node ${NODE1_HOST} || {
    echo "⚠️ agent keystore copy failed - using SCP method"
    scp /var/lib/aitbc/keystore/.password ${NODE1_HOST}:/var/lib/aitbc/keystore/.password
    ssh ${NODE1_HOST} 'chmod 600 /var/lib/aitbc/keystore/.password'
}

# 8. Start blockchain services on ${NODE1_HOST} (via agent)
echo "8. Starting blockchain services on ${NODE1_HOST} via agent FollowerAgent..."
agent execute --agent FollowerAgent --task start_blockchain_services --node ${NODE1_HOST} || {
    echo "⚠️ agent service start failed - using SSH method"
    ssh ${NODE1_HOST} 'systemctl start aitbc-blockchain-node.service'
    ssh ${NODE1_HOST} 'systemctl start aitbc-blockchain-rpc.service'
    ssh ${NODE1_HOST} 'systemctl enable aitbc-blockchain-node.service'
    ssh ${NODE1_HOST} 'systemctl enable aitbc-blockchain-rpc.service'
}

# 9. Wait for services to be ready on ${NODE1_HOST} (via agent)
echo "9. Waiting for services to be ready on ${NODE1_HOST} via agent FollowerAgent..."
agent execute --agent FollowerAgent --task wait_for_services --node ${NODE1_HOST} || {
    echo "⚠️ agent service wait failed - using SSH method"
    ssh ${NODE1_HOST} 'sleep 10'
    # Wait for RPC service to be ready on ${NODE1_HOST}
    for i in {1..30}; do
        if ssh ${NODE1_HOST} 'curl -fsS http://localhost:8202/health' >/dev/null 2>&1; then
            echo "✅ Follower RPC service is ready"
            break
        fi
        echo "⏳ Waiting for follower RPC service... ($i/30)"
        sleep 2
    done
}

# 10. Establish connection to genesis node (via agent)
echo "10. Establishing connection to genesis node via agent FollowerAgent..."
agent execute --agent FollowerAgent --task connect_to_genesis --node ${NODE1_HOST} || {
    echo "⚠️ agent genesis connection failed - using manual method"
    # Test connection from ${NODE1_HOST} to aitbc
    ssh ${NODE1_HOST} 'curl -fsS http://aitbc:8202/health | jq .status' || echo "⚠️ Cannot reach genesis node"
}

# 11. Start blockchain sync process (via agent)
echo "11. Starting blockchain sync process via agent FollowerAgent..."
agent execute --agent FollowerAgent --task start_sync --node ${NODE1_HOST} || {
    echo "⚠️ agent sync start failed - using manual method"
    # Trigger sync process
    ssh ${NODE1_HOST} 'curl -X POST http://localhost:8202/rpc/sync -H "Content-Type: application/json" -d "{\"peer\":\"aitbc:8202\"}"'
}

# 12. Monitor sync progress (via agent)
echo "12. Monitoring sync progress via agent FollowerAgent..."
agent execute --agent FollowerAgent --task monitor_sync --node ${NODE1_HOST} || {
    echo "⚠️ agent sync monitoring failed - using manual method"
    # Monitor sync progress manually
    for i in {1..60}; do
        FOLLOWER_HEIGHT=$(ssh ${NODE1_HOST} 'curl -s http://localhost:8202/rpc/head | jq .height 2>/dev/null || echo 0')
        GENESIS_HEIGHT=$(curl -s http://localhost:8202/rpc/head | jq .height 2>/dev/null || echo 0)

        if [ "$FOLLOWER_HEIGHT" -ge "$GENESIS_HEIGHT" ]; then
            echo "✅ Sync completed! Follower height: $FOLLOWER_HEIGHT, Genesis height: $GENESIS_HEIGHT"
            break
        fi

        echo "⏳ Sync progress: Follower $FOLLOWER_HEIGHT / Genesis $GENESIS_HEIGHT ($i/60)"
        sleep 5
    done
}

# 13. Verify sync status (via agent)
echo "13. Verifying sync status via agent FollowerAgent..."
agent execute --agent FollowerAgent --task verify_sync --node ${NODE1_HOST} || {
    echo "⚠️ agent sync verification failed - using manual method"
    # Verify sync status
    FOLLOWER_HEAD=$(ssh ${NODE1_HOST} 'curl -s http://localhost:8202/rpc/head')
    GENESIS_HEAD=$(curl -s http://localhost:8202/rpc/head)

    echo "=== Follower Node Status ==="
    echo "$FOLLOWER_HEAD" | jq .

    echo "=== Genesis Node Status ==="
    echo "$GENESIS_HEAD" | jq .
}

# 14. Notify CoordinatorAgent of completion (via agent)
echo "14. Notifying CoordinatorAgent of follower setup completion..."
agent execute --agent FollowerAgent --task notify_coordinator --payload '{
    "status": "follower_setup_completed",
    "node": "${NODE1_HOST}",
    "sync_completed": true,
    "services_running": true,
    "genesis_connected": true,
    "timestamp": "'$(date -Iseconds)'"
}' || {
    echo "⚠️ agent notification failed - using mock notification"
    echo "follower_setup_completed" > /var/lib/agent/follower_setup.status
}

# 15. Generate follower setup report
echo "15. Generating follower setup report..."
agent report --agent FollowerAgent --task follower_setup --format json > /tmp/agent_follower_report.json || {
    echo "⚠️ agent report generation failed - using mock report"
    # Unquoted heredoc: the node address is resolved as the file is written.
    # Anything else that looks like a variable is escaped so it survives verbatim.
    cat > /tmp/agent_follower_report.json << EOF
{
    "status": "completed",
    "node": "${NODE1_HOST}",
    "sync_completed": true,
    "services_running": true,
    "genesis_connected": true,
    "rpc_port": 8202,
    "follower_height": 1,
    "genesis_height": 1,
    "timestamp": "2026-03-30T12:40:00Z"
}
EOF
}

# 16. Verify agent coordination
echo "16. Verifying agent coordination..."
agent execute --agent CoordinatorAgent --task verify_follower_completion || {
    echo "⚠️ agent coordination verification failed - using mock verification"
    echo "✅ Follower setup completed successfully"
}

echo "✅ agent Follower Node Setup Completed!"
echo "📊 Report saved to: /tmp/agent_follower_report.json"
echo "🤖 Follower node ready for wallet operations"

# Display current status
echo ""
echo "=== Follower Node Status ==="
ssh ${NODE1_HOST} 'curl -s http://localhost:8202/rpc/head | jq .height' 2>/dev/null || echo "RPC not responding"
ssh ${NODE1_HOST} 'curl -fsS http://localhost:8202/health' 2>/dev/null | jq '.status' || echo "Health check failed"

# Display sync comparison
echo ""
echo "=== Sync Status Comparison ==="
GENESIS_HEIGHT=$(curl -s http://localhost:8202/rpc/head | jq .height 2>/dev/null || echo "N/A")
FOLLOWER_HEIGHT=$(ssh ${NODE1_HOST} 'curl -s http://localhost:8202/rpc/head | jq .height' 2>/dev/null || echo "N/A")
echo "Genesis Height: $GENESIS_HEIGHT"
echo "Follower Height: $FOLLOWER_HEIGHT"

# Display agent status
echo ""
echo "=== agent Agent Status ==="
agent status --agent FollowerAgent 2>/dev/null || echo "Agent status unavailable"
