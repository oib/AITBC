#!/bin/bash
# Direct API-based Hermes agent message listener for AITBC network
# Uses the working Coordinator API endpoints instead of simulated CLI

AGENT_ID="hermes-agent"
COORDINATOR_URL="http://localhost:8011"

echo "Starting Hermes agent listener via direct API..."
echo "Agent ID: $AGENT_ID"
echo "Coordinator: $COORDINATOR_URL"
echo "Press Ctrl+C to stop"

while true; do
  # Fetch messages for our agent via direct API
  RESPONSE=$(curl -s "${COORDINATOR_URL}/v1/hermes/messages/${AGENT_ID}" 2>/dev/null)
  
  # Check if we got a valid response
  if [ "$?" -ne 0 ] || [ -z "$RESPONSE" ] || [ "$RESPONSE" = "null" ]; then
    echo "Error fetching messages or no messages, retrying in 5 seconds..."
    sleep 5
    continue
  fi
  
  # Check if we have messages array and it's not empty
  MESSAGE_COUNT=$(echo "$RESPONSE" | jq '.count // 0')
  if [ "$MESSAGE_COUNT" -eq 0 ]; then
    sleep 5
    continue
  fi
  
  # Process each message looking for PING commands
  echo "$RESPONSE" | jq -c '.messages[] | select(.content | contains("PING"))' | while read -r msg; do
    # Extract sender ID and timestamp
    SENDER=$(echo "$msg" | jq -r '.sender')
    TIMESTAMP=$(echo "$msg" | jq -r '.timestamp')
    MSG_ID=$(echo "$msg" | jq -r '.id')
    
    echo "[$(date -Iseconds)] Received PING from $SENDER at $TIMESTAMP (ID: $MSG_ID)"
    
    # Send PONG response via direct API
    PONG_RESPONSE=$(curl -s -X POST "${COORDINATOR_URL}/v1/hermes/messages/send" \
      -H "Content-Type: application/json" \
      -d "{
        \"sender\": \"${AGENT_ID}\",
        \"recipient\": \"${SENDER}\",
        \"content\": \"PONG response from Hermes\",
        \"message_type\": \"TEXT\",
        \"timestamp\": \"$(date -Iseconds)\"
      }")
    
    # Check if PONG was sent successfully
    if echo "$PONG_RESPONSE" | jq -e '.success' >/dev/null 2>&1; then
      PONG_ID=$(echo "$PONG_RESPONSE" | jq -r '.message.id // "unknown"')
      echo "[$(date -Iseconds)] Sent PONG response to $SENDER (ID: $PONG_ID)"
    else
      echo "[$(date -Iseconds)] Failed to send PONG to $SENDER"
      echo "Response: $PONG_RESPONSE"
    fi
  done
  
  # Sleep before next poll
  sleep 5
done