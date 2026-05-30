# Hermes Agent Listener for AITBC Network - Working Solution

## Problem
The user wanted to implement a Hermes agent listener for the AITBC network that would:
1. Continuously poll for incoming messages
2. Parse messages for PING commands
3. Respond to PING messages with PONG responses

## Challenge
The `aitbc-cli agent message` and `aitbc-cli agent messages` commands were returning simulated responses rather than actually communicating with the backend services, making it impossible to build a functional listener using the CLI alone.

## Solution
We discovered that while the CLI commands were simulated, the underlying Coordinator API service was fully functional and provided real agent messaging capabilities. We implemented a direct API-based listener that:

1. Registers agents with the Coordinator API
2. Sends messages via the `/v1/hermes/messages/send` endpoint
3. Retrieves messages via the `/v1/hermes/messages/{agent_id}` endpoint
4. Processes incoming messages for PING commands
5. Responds with PONG messages

## Implementation Files
- `/opt/aitbc/hermes_listener_direct_api.sh` - The working listener script

## Verification
We successfully tested the system by:
1. Registering two agents: `hermes-agent` and `aitbc3-agent`
2. Sending a PING message from `aitbc3-agent` to `hermes-agent`
3. Observing the listener script detect the PING and send a PONG response
4. Verifying the message exchange in the Coordinator API

## Current Status
The Hermes agent listener is running in the background (process ID 155489) and is actively:
- Polling for messages every 5 seconds
- Detecting PING messages from any agent
- Responding with PONG messages to the original sender

## Usage
To send a test PING message to trigger the listener:
```bash
curl -s -X POST "http://localhost:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "aitbc3-agent",
    "recipient": "hermes-agent",
    "content": "PING",
    "message_type": "TEXT",
    "timestamp": "'$(date -Iseconds)'"
  }' | jq .
```

The listener will automatically respond with a PONG message.

## Notes
- This solution uses the Coordinator API directly rather than the simulated aitbc-cli commands
- The listener is designed to be lightweight and resilient, with error handling and retry logic
- All message exchanges are persisted and visible via the Coordinator API endpoints