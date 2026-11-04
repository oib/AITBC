#!/bin/bash
# Register Agent Agent with AITBC Agent Coordinator
set -euo pipefail

COORDINATOR_URL="${COORDINATOR_URL:-http://localhost:8107}"
AGENT_ID="${AGENT_ID:-agent-agent}"

# The coordinator requires an identity proof in enforce mode; supply it
# via AGENT_IDENTITY_ADDRESS / AGENT_IDENTITY_PROOF when the deployment
# enforces identity.
PAYLOAD=$(AGENT_ID="$AGENT_ID" python3 - <<'PY'
import json, os
body = {
    "agent_id": os.environ["AGENT_ID"],
    "agent_type": "worker",
    "capabilities": ["data-processing", "analysis", "general", "debugging", "planning"],
    "services": ["task-execution", "analysis", "coordination"],
    "endpoints": {"http": "http://localhost:9002", "callback": "http://localhost:9002/callback"},
    "metadata": {"version": "1.0.0", "owner": "aitbc",
                 "description": "Agent AI agent for task coordination and analysis"},
}
if os.environ.get("AGENT_IDENTITY_ADDRESS"):
    body["identity_address"] = os.environ["AGENT_IDENTITY_ADDRESS"]
    body["identity_proof"] = os.environ.get("AGENT_IDENTITY_PROOF", "")
print(json.dumps(body))
PY
)

echo "Registering Agent Agent ($AGENT_ID) with coordinator at $COORDINATOR_URL"

status=$(curl -sS -o /tmp/register-agent-resp.json -w "%{http_code}" -X POST "$COORDINATOR_URL/v1/agents/register" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

cat /tmp/register-agent-resp.json; echo
if [[ "$status" != 2* ]]; then
    echo "Agent registration FAILED (HTTP $status)" >&2
    exit 1
fi
echo "Agent Agent registration complete"
