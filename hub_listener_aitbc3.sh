#!/bin/bash
# Hub coordinator listener for aitbc3 node
# Polls hub coordinator for messages destined to owl-aitbc3

AGENT_ID="owl-aitbc3"
HUB_COORDINATOR_URL="http://hub.aitbc.bubuit.net:8011"
PROCESSED_IDS_FILE="/tmp/hub_listener_processed_ids.txt"

# Initialize processed IDs file if it doesn't exist
if [ ! -f "$PROCESSED_IDS_FILE" ]; then
  touch "$PROCESSED_IDS_FILE"
fi

echo "Starting hub coordinator listener for aitbc3..."
echo "Agent ID: $AGENT_ID"
echo "Hub Coordinator: $HUB_COORDINATOR_URL"
echo "Press Ctrl+C to stop"

while true; do
  # Fetch messages for our agent from hub coordinator
  RESPONSE=$(curl -s "${HUB_COORDINATOR_URL}/v1/hermes/messages/${AGENT_ID}" 2>/dev/null)
  
  # Check if we got a valid response
  if [ "$?" -ne 0 ] || [ -z "$RESPONSE" ] || [ "$RESPONSE" = "null" ]; then
    echo "[$(date -Iseconds)] Error fetching messages or no messages, retrying in 5 seconds..."
    sleep 5
    continue
  fi
  
  # Check if we have messages array and it's not empty
  MESSAGE_COUNT=$(echo "$RESPONSE" | jq '.count // 0')
  if [ "$MESSAGE_COUNT" -eq 0 ]; then
    sleep 5
    continue
  fi
  
  # Process all messages
  echo "$RESPONSE" | jq -c '.messages[]' | while read -r msg; do
    SENDER=$(echo "$msg" | jq -r '.sender')
    TIMESTAMP=$(echo "$msg" | jq -r '.timestamp')
    MSG_ID=$(echo "$msg" | jq -r '.id')
    CONTENT=$(echo "$msg" | jq -r '.content')
    MSG_TYPE=$(echo "$msg" | jq -r '.message_type')
    
    # Check if we've already processed this message
    if grep -q "^${MSG_ID}$" "$PROCESSED_IDS_FILE" 2>/dev/null; then
      continue
    fi
    
    # Mark this message as processed
    echo "$MSG_ID" >> "$PROCESSED_IDS_FILE"
    
    echo "[$(date -Iseconds)] New message from $SENDER (ID: $MSG_ID)"
    echo "  Type: $MSG_TYPE"
    echo "  Content: $CONTENT"
    echo "  Timestamp: $TIMESTAMP"
    
    # Check for PONG specifically
    if echo "$CONTENT" | grep -q "PONG"; then
      echo "  *** PONG DETECTED ***"
    fi
  done
  
  # Sleep before next poll
  sleep 5
done
