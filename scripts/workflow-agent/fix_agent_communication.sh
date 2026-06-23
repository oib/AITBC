#!/bin/bash
# Agent Agent Communication Fix
# This script demonstrates the correct way to use Agent agents with sessions

set -e


# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    export SHOP_URL="${SHOP_URL:-https://aitbc3.aitbc.bubuit.net}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi
echo "=== Agent Agent Communication Fix ==="

# 1. Check Agent status
echo "1. Checking Agent status..."
agent status --all | head -10

# 2. Create a session for agent operations
echo "2. Creating agent session for blockchain operations..."
SESSION_ID="blockchain-workflow-$(date +%s)"

# 3. Test agent communication with session
echo "3. Testing agent communication with proper session..."
agent agent --agent main --session-id $SESSION_ID --message "Test agent communication for blockchain workflow" --thinking low

echo "✅ Agent communication working with session ID: $SESSION_ID"

# 4. Demonstrate agent coordination
echo "4. Demonstrating agent coordination for blockchain operations..."
agent agent --agent main --session-id $SESSION_ID --message "Coordinate multi-node blockchain deployment and provide status analysis" --thinking medium

# 5. Show session information
echo "5. Session information:"
echo "Session ID: $SESSION_ID"
echo "Agent: main"
echo "Status: Active"

# 6. Generate fix report
cat > /tmp/agent_agent_fix_report.json << EOF
{
    "fix_status": "completed",
    "issue": "Agent communication failed due to missing session context",
    "solution": "Added --session-id parameter to agent commands",
    "session_id": "$SESSION_ID",
    "agent_id": "main",
    "working_commands": [
        "agent agent --agent main --session-id \$SESSION_ID --message 'task'",
        "agent agent --agent main --session-id \$SESSION_ID --message 'task' --thinking medium"
    ],
    "timestamp": "$(date -Iseconds)"
}
EOF

echo "✅ Agent Agent Communication Fix Completed!"
echo "📊 Report saved to: /tmp/agent_agent_fix_report.json"
echo ""
echo "=== Correct Usage Examples ==="
echo "# Basic agent communication:"
echo "agent agent --agent main --session-id $SESSION_ID --message 'your task'"
echo ""
echo "# With thinking level:"
echo "agent agent --agent main --session-id $SESSION_ID --message 'complex task' --thinking high"
echo ""
echo "# For blockchain operations:"
echo "agent agent --agent main --session-id $SESSION_ID --message 'coordinate blockchain deployment' --thinking medium"
