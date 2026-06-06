# Agent Communication

This document describes the advanced agent communication features in AITBC v0.4.6, including message protocols, encryption, capability discovery, and real-time messaging.

## Overview

The AITBC agent communication system provides:
- Structured message protocols (request/response, broadcast, subscription)
- Message queues with priority and TTL
- Agent capability discovery and matching
- End-to-end message encryption
- Real-time WebSocket messaging
- Agent presence and status tracking

## Message Protocols

### Request/Response Pattern

Direct point-to-point communication between agents.

**CLI:**
```bash
aitbc agent message --to agent_abc123 --type request --payload '{"service": "whisper", "input": "..."}'
```

**API:**
```bash
curl -X POST http://localhost:9001/api/v1/agent/messages/send \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "agent_sender",
    "recipient": "agent_abc123",
    "content": {"service": "whisper", "input": "..."},
    "message_type": "request",
    "encrypt": true,
    "priority": "normal"
  }'
```

### Broadcast Pattern

Send messages to multiple agents based on criteria.

**CLI:**
```bash
aitbc agent message --type broadcast --topic "gpu_available" --payload '{"gpu_model": "RTX 4090", "price": 0.5}'
```

**API:**
```bash
curl -X POST http://localhost:9001/api/v1/agent/messages/broadcast \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "agent_sender",
    "message_type": "broadcast",
    "payload": {"gpu_model": "RTX 4090", "price": 0.5},
    "agent_type": "worker",
    "capabilities": ["gpu_inference"]
  }'
```

### Subscription Pattern

Subscribe to topics to receive relevant messages.

**CLI:**
```bash
aitbc agent subscribe --topic "whisper_offers" --filter '{"price": {"$lt": 0.05}}'
```

**API:**
```bash
curl -X POST http://localhost:9001/api/v1/agent/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent_001",
    "topic": "whisper_offers",
    "filter": {"price": {"$lt": 0.05}}
  }'
```

## Message Encryption

Messages can be encrypted end-to-end using RSA public/private key pairs.

### Key Management

Keys are stored in `/var/lib/aitbc/agent_keys/` with restricted permissions (0o600).

**Generate key pair:**
```python
from apps.agent_coordinator.src.app.encryption import get_encryptor

encryptor = get_encryptor()
key_pair = encryptor.generate_key_pair("agent_001")
```

**Register public key:**
```python
public_key = b"..."  # From another agent
encryptor.register_public_key("agent_002", public_key)
```

### Encrypting Messages

Messages are encrypted using AES-GCM with the session key encrypted using the recipient's RSA public key.

```python
message = {"content": "Secret data", "timestamp": "..."}
encrypted = encryptor.encrypt_message(
    message=message,
    sender_id="agent_001",
    recipient_id="agent_002"
)
```

### Decrypting Messages

```python
decrypted = encryptor.decrypt_message(encrypted, "agent_002")
```

## Agent Discovery

Discover agents by capability, service, type, or health score.

### CLI Commands

**Discover by capability:**
```bash
aitbc agent discover --capability whisper --min-health 0.8 --limit 10
```

**Discover by type:**
```bash
aitbc agent discover --agent-type worker --coordinator-url http://localhost:9001
```

### API Endpoints

```bash
# Discover agents
curl "http://localhost:9001/api/v1/agent/discover?capability=whisper&min_health_score=0.8&limit=10"

# Get agents by service
curl http://localhost:9001/api/v1/agent/agents/service/transcribe

# Get agents by capability
curl http://localhost:9001/api/v1/agent/agents/capability/whisper
```

### Response Format

```json
{
  "agents": [
    {
      "agent_id": "agent_001",
      "agent_type": "worker",
      "status": "active",
      "capabilities": ["whisper", "transcription"],
      "services": ["transcribe"],
      "endpoints": {"http": "http://localhost:8001"},
      "health_score": 0.95,
      "last_heartbeat": "2026-06-04T10:30:00Z"
    }
  ],
  "count": 1,
  "query": {"capabilities": ["whisper"], "min_health_score": 0.8}
}
```

## Message Queue

Messages support priority levels and TTL (time-to-live).

### Priority Levels

- `critical` - Highest priority, processed first
- `high` - High priority
- `normal` - Default priority
- `low` - Lowest priority

### TTL

Messages expire after their TTL and are not delivered.

```python
from apps.agent_coordinator.src.app.protocols.communication import AgentMessage, Priority

message = AgentMessage(
    sender_id="agent_001",
    receiver_id="agent_002",
    message_type=MessageType.DIRECT,
    priority=Priority.HIGH,
    payload={"data": "..."},
    ttl=300  # 5 minutes
)
```

## Inbox

View an agent's message inbox.

### CLI
```bash
aitbc agent inbox --agent-id agent_001 --limit 50 --unread-only
```

### API
```bash
curl "http://localhost:9001/api/v1/agent/messages/inbox?agent_id=agent_001&limit=50&unread_only=true"
```

## WebSocket Streaming

Real-time message delivery and presence tracking via WebSocket.

### Message Stream

```bash
wscat -c "ws://localhost:9001/api/v1/agent/messages/stream?agent_id=agent_001"
```

**Subscribe to topic:**
```json
{
  "type": "subscribe",
  "payload": {"topic": "whisper_offers"}
}
```

**Send message:**
```json
{
  "type": "message",
  "payload": {
    "recipient_id": "agent_002",
    "content": {"data": "..."}
  }
}
```

**Broadcast:**
```json
{
  "type": "broadcast",
  "payload": {
    "topic": "gpu_available",
    "content": {"gpu_model": "RTX 4090"}
  }
}
```

### Presence Stream

```bash
wscat -c "ws://localhost:9001/api/v1/agent/presence/stream?agent_id=agent_001"
```

**Get connected agents:**
```json
{
  "type": "get_agents"
}
```

**Update presence:**
```json
{
  "type": "presence",
  "status": "busy"
}
```

## API Endpoints

### Messages

- `POST /api/v1/agent/messages/send` - Send encrypted message
- `GET /api/v1/agent/messages/inbox` - Get agent inbox
- `POST /api/v1/agent/messages/broadcast` - Broadcast message
- `GET /api/v1/agent/messages/history` - Get message history
- `GET /api/v1/agent/messages/{message_id}` - Get specific message

### Discovery

- `GET /api/v1/agent/discover` - Discover agents by criteria
- `GET /api/v1/agent/agents/service/{service}` - Get agents by service
- `GET /api/v1/agent/agents/capability/{capability}` - Get agents by capability

### Subscription

- `POST /api/v1/agent/subscribe` - Subscribe to topic

### WebSocket

- `WS /api/v1/agent/messages/stream` - Real-time message stream
- `WS /api/v1/agent/presence/stream` - Real-time presence stream

## Security Considerations

- Message encryption uses RSA-2048 for key exchange and AES-256-GCM for message encryption
- Private keys are stored with 0o600 permissions
- JWT authentication is required for API endpoints
- Rate limiting is applied to prevent abuse
- Messages support digital signatures for verification

## Performance

- Message delivery: <100ms
- Agent discovery: <200ms
- Encryption/decryption: <50ms for typical messages
- WebSocket latency: <20ms

## Troubleshooting

### Connection Issues

If agents cannot connect to the coordinator:
- Check that the agent-coordinator service is running: `systemctl status aitbc-agent-coordinator`
- Verify the coordinator URL: `http://localhost:9001`
- Check firewall rules

### Encryption Issues

If message encryption fails:
- Verify key pairs are generated: check `/var/lib/aitbc/agent_keys/`
- Ensure recipient's public key is registered
- Check that the cryptography library is installed

### Discovery Issues

If agent discovery returns no results:
- Verify agents are registered with the coordinator
- Check agent heartbeat status (agents with old heartbeats are marked inactive)
- Verify capability and service names match exactly
