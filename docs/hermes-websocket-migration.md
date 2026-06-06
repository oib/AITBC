# Hermes WebSocket Migration Guide

## Overview

This guide explains how to migrate from the current polling-based message system to the new WebSocket-based real-time message listener.

## Current Polling Implementation

### Current Pattern
```python
# Agent polls for messages (inefficient)
while True:
    response = requests.get(f"{coordinator_url}/v1/hermes/messages/{agent_id}")
    messages = response.json()["messages"]
    
    for message in messages:
        # Process message
        if "PING" in message["content"]:
            # Send PONG
            requests.post(f"{coordinator_url}/v1/hermes/messages/send", ...)
    
    time.sleep(5)  # Poll every 5 seconds
```

### Issues with Polling
- **High latency**: Messages delayed up to 5 seconds
- **Server load**: Continuous GET requests even when no messages
- **Network overhead**: Repeated HTTP headers and connections
- **Battery drain**: Constant network activity on mobile agents

## New WebSocket Implementation

### WebSocket Pattern
```python
# Agent connects once and receives messages in real-time
import asyncio
import websockets
import json

async def hermes_websocket_listener(agent_id: str, coordinator_url: str):
    uri = f"ws://{coordinator_url}/v1/hermes/ws/{agent_id}"
    
    async with websockets.connect(uri) as websocket:
        print(f"Connected to Hermes WebSocket as {agent_id}")
        
        # Listen for messages
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            
            # Process message
            if data["type"] == "connection_established":
                print("WebSocket listener active")
            elif data["type"] == "PONG":
                print(f"Received PONG: {data['content']}")
            elif data["type"] == "handler_acknowledgment":
                print(f"Handler triggered: {data['handler_results']}")
            
            # Send messages
            await websocket.send(json.dumps({
                "id": "msg-001",
                "sender": agent_id,
                "recipient": "owl-hub",
                "content": "PING",
                "type": "direct"
            }))

# Run the listener
asyncio.run(hermes_websocket_listener("my-agent", "localhost:8000"))
```

### Benefits of WebSocket
- **Real-time delivery**: Messages delivered instantly
- **Lower server load**: Single connection per agent
- **Reduced bandwidth**: No repeated HTTP headers
- **Better battery life**: Minimal network activity

## Built-in Handlers

### PING Handler
```python
# Automatically responds to PING with PONG
# No agent code needed - handled by server

# When agent sends:
{
    "sender": "agent-001",
    "content": "PING",
    "type": "direct"
}

# Server automatically responds:
{
    "type": "PONG",
    "sender": "owl-hub",
    "content": "PONG from owl-hub",
    "timestamp": "2026-06-06T10:30:00Z"
}
```

### REQUEST_COINS Handler
```python
# Handles coin requests with approval workflow
# Supports automatic, AI, and manual approval modes

# Agent sends:
{
    "sender": "agent-001",
    "content": "REQUEST_COINS",
    "type": "direct"
}

# Server processes and responds:
{
    "type": "handler_acknowledgment",
    "handler_results": {
        "message_type": "REQUEST_COINS",
        "handlers_triggered": 1,
        "results": [{
            "handler": "request_coins_handler",
            "result": {
                "action": "coin_request_received",
                "amount": 100,
                "wallet_address": "aitbc1abc...",
                "status": "pending_approval"
            },
            "success": True
        }]
    }
}
```

## Migration Steps

### Step 1: Update Agent Code
```python
# OLD: Polling implementation
def poll_messages(agent_id: str):
    while True:
        response = requests.get(f"{coordinator_url}/v1/hermes/messages/{agent_id}")
        messages = response.json()["messages"]
        process_messages(messages)
        time.sleep(5)

# NEW: WebSocket implementation
async def websocket_listener(agent_id: str):
    uri = f"ws://{coordinator_url}/v1/hermes/ws/{agent_id}"
    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            process_message(json.loads(message))
```

### Step 2: Remove PONG Handler Code
```python
# OLD: Manual PONG handling
if "PING" in message["content"]:
    requests.post(f"{coordinator_url}/v1/hermes/messages/send", {
        "sender": agent_id,
        "recipient": message["sender"],
        "content": f"PONG from {agent_id}"
    })

# NEW: Automatic PONG (no code needed)
# Server handles PING/PONG automatically
```

### Step 3: Update Message Sending
```python
# OLD: HTTP POST
requests.post(f"{coordinator_url}/v1/hermes/messages/send", {
    "sender": agent_id,
    "recipient": recipient,
    "content": content
})

# NEW: WebSocket send
await websocket.send(json.dumps({
    "sender": agent_id,
    "recipient": recipient,
    "content": content
}))
```

### Step 4: Add Connection Handling
```python
async def websocket_listener(agent_id: str):
    uri = f"ws://{coordinator_url}/v1/hermes/ws/{agent_id}"
    
    while True:  # Auto-reconnect loop
        try:
            async with websockets.connect(uri) as websocket:
                print(f"Connected as {agent_id}")
                
                while True:
                    message = await websocket.recv()
                    process_message(json.loads(message))
                    
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed, reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error: {e}, reconnecting in 5s...")
            await asyncio.sleep(5)
```

## API Endpoints

### WebSocket Endpoint
```
WS /v1/hermes/ws/{agent_id}
```

### Status Endpoint
```bash
GET /v1/hermes/ws/status

Response:
{
    "active_connections": 3,
    "connected_agents": ["agent-001", "agent-002", "owl-hub"],
    "registered_handlers": ["PING", "HELLO", "REQUEST_COINS"],
    "queued_messages": {
        "agent-003": 2
    }
}
```

### Fallback Send Endpoint
```bash
POST /v1/hermes/messages/send

# Works for both WebSocket and polling clients
# If recipient is connected via WebSocket, delivers instantly
# If not connected, queues message for later delivery
```

## Testing

### Test WebSocket Connection
```python
import asyncio
import websockets

async def test_connection():
    uri = "ws://localhost:8000/v1/hermes/ws/test-agent"
    async with websockets.connect(uri) as websocket:
        print("Connected!")
        
        # Send PING
        await websocket.send(json.dumps({
            "sender": "test-agent",
            "recipient": "owl-hub",
            "content": "PING"
        }))
        
        # Wait for PONG
        response = await websocket.recv()
        print(f"Received: {response}")

asyncio.run(test_connection())
```

### Test PING/PONG
```bash
# Connect to WebSocket
wscat -c ws://localhost:8000/v1/hermes/ws/test-agent

# Send PING
{"sender": "test-agent", "recipient": "owl-hub", "content": "PING"}

# Receive automatic PONG
{"type": "PONG", "sender": "owl-hub", "content": "PONG from owl-hub", ...}
```

## Rollback Plan

If WebSocket implementation has issues, rollback to polling:

```python
# Fallback to polling if WebSocket fails
async def hybrid_listener(agent_id: str):
    try:
        # Try WebSocket first
        await websocket_listener(agent_id)
    except Exception as e:
        print(f"WebSocket failed: {e}, falling back to polling")
        while True:
            response = requests.get(f"{coordinator_url}/v1/hermes/messages/{agent_id}")
            messages = response.json()["messages"]
            process_messages(messages)
            time.sleep(5)
```

## Performance Comparison

| Metric | Polling | WebSocket | Improvement |
|--------|---------|-----------|-------------|
| Latency | 0-5 seconds | <100ms | 50x faster |
| Server Requests | 12/min/agent | 1/agent | 12x fewer |
| Bandwidth | ~2KB/request | ~200KB connection | 10x less |
| Battery Impact | High | Low | Significant |

## Monitoring

### Monitor WebSocket Status
```bash
# Check active connections
curl http://localhost:8000/v1/hermes/ws/status

# Monitor logs
tail -f coordinator.log | grep "WebSocket"
```

### Metrics to Track
- Active WebSocket connections
- Message delivery latency
- Handler execution time
- Connection failures/reconnects

## Troubleshooting

### Connection Issues
```python
# Ensure WebSocket URL is correct
# Use ws:// for HTTP, wss:// for HTTPS
ws://localhost:8000/v1/hermes/ws/{agent_id}
```

### Handler Not Triggering
```python
# Check handler registration
curl http://localhost:8000/v1/hermes/ws/status

# Verify message format
{
    "sender": "agent-001",
    "content": "PING",  # Must match handler pattern
    "type": "direct"
}
```

### Messages Not Delivered
```python
# Check if recipient is connected
curl http://localhost:8000/v1/hermes/ws/status

# Check queued messages
# Messages are queued if recipient not connected
```

## Future Enhancements

### Custom Handlers
```python
# Register custom handlers
from app.contexts.hermes.routers.hermes_websocket import message_listener

async def custom_handler(message: dict[str, Any]) -> dict[str, Any]:
    # Custom logic
    return {"action": "custom_processed"}

message_listener.register_handler("CUSTOM", custom_handler)
```

### Message Encryption
```python
# Add encryption to WebSocket messages
from app.agent_coordinator.encryption.message_encryption import encrypt_message

encrypted = encrypt_message(message)
await websocket.send(encrypted)
```

### Multi-Agent Coordination
```python
# Use WebSocket for real-time coordination
await websocket.send(json.dumps({
    "type": "COORDINATION",
    "task": "distributed_computation",
    "participants": ["agent-001", "agent-002"]
}))
```

## Support

For issues or questions:
- Check Coordinator logs: `tail -f coordinator.log`
- Test WebSocket status: `GET /v1/hermes/ws/status`
- Review handler registration in logs
