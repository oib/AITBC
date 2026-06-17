# Cross-Node Agent Messaging System - v0.4.7

**Release**: v0.4.7
**Date**: June 5, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.7 introduces a cross-node agent messaging system, enabling agents on different AITBC nodes to communicate via the Coordinator API exposed through the API Gateway.

## Implementation Details

### Architecture
- Coordinator API (port 8203) exposed via API Gateway at `/v1/coordinator/v1/hermes/*`
- Host nginx proxy handles SSL termination and forwards requests to container
- Agent mailbox system for message storage and retrieval
- Polling-based message delivery for cross-node communication

### Key Components
- **API Gateway Configuration**: Added coordinator service routing to `/v1/coordinator/` prefix
- **Host Nginx Proxy**: Configured to forward `/ollama/` and `/api/` paths to container
- **Ollama Proxy**: Fixed Host header issue (override to "localhost" to avoid 403 errors)
- **Agent Messaging**: Send/receive messages between agents on different nodes

## Verified Test Results

All cross-node flows have been tested and verified working:

| Flow | Endpoint | Result |
|------|----------|--------|
| Marketplace Discovery | GET /api/v1/marketplace/offer | ✅ 200 — Returns offer |
| Ollama Model List | GET /ollama/api/tags | ✅ 200 — Returns nemotron-3-super:cloud |
| Ollama Inference | POST /ollama/api/generate | ✅ 200 — Returns generation |
| Agent Msg Send (hub→shop) | POST /api/v1/coordinator/v1/hermes/messages/send | ✅ 200 — Message sent |
| Agent Msg Recv (shop) | GET /api/v1/coordinator/v1/hermes/messages/owl-aitbc3 | ✅ 200 — Returns messages |
| Agent Msg Send (shop→hub) | POST /api/v1/coordinator/v1/hermes/messages/send | ✅ 200 — Response sent |
| Agent Msg Recv (hub) | GET /api/v1/coordinator/v1/hermes/messages/owl-hub | ✅ 200 — Returns shop response |

## End-to-End Customer Journey

1. **Discovery**: Customer discovers shop's offer via marketplace API
2. **Direct Inference**: Customer calls Ollama API directly for inference
3. **Agent Messaging**: Customer sends message to shop agent
4. **Message Processing**: Shop receives and processes message
5. **Response**: Shop sends response back to customer
6. **Payment**: Escrow-based payment with proof of work

## Configuration Changes

### API Gateway (`/opt/aitbc/apps/api-gateway/src/api_gateway/main.py`)
```python
"coordinator": {
    "base_url": os.getenv("COORDINATOR_API_URL", "http://localhost:8203"),
    "prefix": "/v1/coordinator",
},
```

### Container Nginx (`/etc/nginx/sites-enabled/aitbc`)
```nginx
location /ollama/ {
    proxy_pass http://127.0.0.1:11434/;
    proxy_set_header Host "localhost";  # Fixed 403 issue
    # ... WebSocket support
}
```

### Host Nginx Proxy
- Configured to forward `/ollama/` and `/api/` paths to container
- SSL termination handled by host reverse proxy
- WebSocket support for streaming responses

## Results

- ✅ Coordinator API exposed through API Gateway at `/v1/coordinator/v1/hermes/*`
- ✅ Agent mailbox system for cross-node communication
- ✅ Message sending between agents on different nodes
- ✅ Message polling and retrieval by agent ID
- ✅ Host nginx proxy configuration for external access
- ✅ Ollama cloud model inference via public endpoint
- ✅ Full customer journey: discovery → messaging → inference → payment
- ✅ End-to-end verified: hub ↔ aitbc3 agent communication

---

*Last Updated: 2026-06-05*
