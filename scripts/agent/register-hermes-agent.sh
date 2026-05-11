#!/bin/bash
# Register Hermes Agent with AITBC Agent Coordinator

COORDINATOR_URL="http://localhost:9001"
AGENT_ID="hermes-agent"
AGENT_TYPE="worker"
CAPABILITIES='["data-processing", "analysis", "general", "debugging", "planning"]'
SERVICES='["task-execution", "analysis", "coordination"]'
ENDPOINTS='{"http": "http://localhost:9002", "callback": "http://localhost:9002/callback"}'

echo "Registering Hermes Agent with coordinator at $COORDINATOR_URL"

curl -X POST "$COORDINATOR_URL/agents/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"agent_id\": \"$AGENT_ID\",
    \"agent_type\": \"$AGENT_TYPE\",
    \"capabilities\": $CAPABILITIES,
    \"services\": $SERVICES,
    \"endpoints\": $ENDPOINTS,
    \"metadata\": {
      \"version\": \"1.0.0\",
      \"owner\": \"aitbc\",
      \"description\": \"Hermes AI agent for task coordination and analysis\"
    }
  }"

echo ""
echo "Hermes Agent registration complete"
