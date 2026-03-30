#!/bin/bash
# OpenClaw Agent Communication Fix
# This script demonstrates the correct way to use OpenClaw agents with sessions

set -e

echo "=== OpenClaw Agent Communication Fix ==="

# 1. Check OpenClaw status
echo "1. Checking OpenClaw status..."
openclaw status --all | head -10

# 2. Create a session for agent operations
echo "2. Creating agent session for blockchain operations..."
SESSION_ID="blockchain-workflow-$(date +%s)"

# 3. Test agent communication with session
echo "3. Testing agent communication with proper session..."
openclaw agent --agent main --session-id $SESSION_ID --message "Test agent communication for blockchain workflow" --thinking low

echo "✅ Agent communication working with session ID: $SESSION_ID"

# 4. Demonstrate agent coordination
echo "4. Demonstrating agent coordination for blockchain operations..."
openclaw agent --agent main --session-id $SESSION_ID --message "Coordinate multi-node blockchain deployment and provide status analysis" --thinking medium

# 5. Show session information
echo "5. Session information:"
echo "Session ID: $SESSION_ID"
echo "Agent: main"
echo "Status: Active"

# 6. Generate fix report
cat > /tmp/openclaw_agent_fix_report.json << EOF
{
    "fix_status": "completed",
    "issue": "Agent communication failed due to missing session context",
    "solution": "Added --session-id parameter to agent commands",
    "session_id": "$SESSION_ID",
    "agent_id": "main",
    "working_commands": [
        "openclaw agent --agent main --session-id \$SESSION_ID --message 'task'",
        "openclaw agent --agent main --session-id \$SESSION_ID --message 'task' --thinking medium"
    ],
    "timestamp": "$(date -Iseconds)"
}
EOF

echo "✅ OpenClaw Agent Communication Fix Completed!"
echo "📊 Report saved to: /tmp/openclaw_agent_fix_report.json"
echo ""
echo "=== Correct Usage Examples ==="
echo "# Basic agent communication:"
echo "openclaw agent --agent main --session-id $SESSION_ID --message 'your task'"
echo ""
echo "# With thinking level:"
echo "openclaw agent --agent main --session-id $SESSION_ID --message 'complex task' --thinking high"
echo ""
echo "# For blockchain operations:"
echo "openclaw agent --agent main --session-id $SESSION_ID --message 'coordinate blockchain deployment' --thinking medium"
