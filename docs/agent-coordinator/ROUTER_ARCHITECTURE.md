# Agent Coordinator Router Architecture

## Overview

The Agent Coordinator API uses a split router architecture where functionality is distributed across multiple routers. This document explains the current organization and endpoint paths.

## Router Organization

### Main Router Inclusion Logic

From `apps/agent-coordinator/src/app/main.py`:

```python
for router in ROUTERS:
    # Check if router already has a prefix (like agent_messaging.router)
    if hasattr(router, 'prefix') and router.prefix.startswith('/api'):
        app.include_router(router)
    else:
        app.include_router(router, prefix="/v1")
```

**Rule:** Routers with explicit `/api` prefixes keep their prefix. Routers without prefixes get `/v1` added.

## Router Breakdown

### 1. Messages Router (`messages.py`)
**Prefix:** `/api/v1/agent/messages`
**Purpose:** Agent messaging, discovery, and related operations

**Endpoints:**
- `POST /send` - Send encrypted message
- `GET /inbox` - Get agent's inbox
- `GET /{agent_id}` - Get messages for agent (compatibility)
- `GET /discover` - Discover agents by criteria
- `POST /subscribe` - Subscribe to topic
- `POST /broadcast` - Broadcast message to multiple agents
- `GET /history` - Get message history with filters
- `GET /id/{message_id}` - Get specific message
- `GET /load-balancer/stats` - Get load balancer statistics
- `GET /registry/stats` - Get agent registry statistics
- `GET /agents/service/{service}` - Get agents by service
- `GET /agents/capability/{capability}` - Get agents by capability
- `PUT /load-balancer/strategy` - Set load balancing strategy
- `POST /peers/add` - Add peer connection
- `POST /peers/remove` - Remove peer connection
- `GET /peers/{agent_id}` - Get peers for agent
- `GET /peers` - List all peers

**Full Paths:**
- `/api/v1/agent/messages/send`
- `/api/v1/agent/messages/inbox`
- `/api/v1/agent/messages/{agent_id}`
- `/api/v1/agent/messages/discover`
- `/api/v1/agent/messages/subscribe`
- `/api/v1/agent/messages/broadcast`
- `/api/v1/agent/messages/history`
- `/api/v1/agent/messages/id/{message_id}`
- `/api/v1/agent/messages/load-balancer/stats`
- `/api/v1/agent/messages/registry/stats`
- `/api/v1/agent/messages/agents/service/{service}`
- `/api/v1/agent/messages/agents/capability/{capability}`
- `/api/v1/agent/messages/load-balancer/strategy`
- `/api/v1/agent/messages/peers/add`
- `/api/v1/agent/messages/peers/remove`
- `/api/v1/agent/messages/peers/{agent_id}`
- `/api/v1/agent/messages/peers`

### 2. Agents Router (`agents.py`)
**Prefix:** None (gets `/v1` from main.py)
**Purpose:** Core agent registration and status management

**Endpoints:**
- `POST /agents/register` - Register a new agent
- `POST /agents/discover` - Discover agents based on criteria
- `GET /agents/{agent_id}` - Get agent information by ID
- `PUT /agents/{agent_id}/status` - Update agent status
- `POST /agents/{agent_id}/heartbeat` - Receive heartbeat from agent

**Full Paths:**
- `/v1/agents/register`
- `/v1/agents/discover`
- `/v1/agents/{agent_id}`
- `/v1/agents/{agent_id}/status`
- `/v1/agents/{agent_id}/heartbeat`

### 3. Auth Router (`auth.py`)
**Prefix:** `/api/v1/auth`
**Purpose:** Authentication and authorization

**Endpoints:**
- `POST /login` - User login
- `POST /refresh` - Refresh access token
- `POST /validate` - Validate token
- `POST /api-key/generate` - Generate API key
- `POST /api-key/validate` - Validate API key
- `POST /logout` - User logout

**Full Paths:**
- `/api/v1/auth/login`
- `/api/v1/auth/refresh`
- `/api/v1/auth/validate`
- `/api/v1/auth/api-key/generate`
- `/api/v1/auth/api-key/validate`
- `/api/v1/auth/logout`

### 4. Other Routers

**Tasks Router (`tasks.py`)**
- Prefix: None → `/v1`
- Endpoints: Task submission, management

**Swarm Router (`swarm.py`)**
- Prefix: `/swarm`
- Endpoints: Swarm coordination

**WebSocket Router (`websocket.py`)**
- Prefix: `/api/v1/agent`
- Endpoints: WebSocket connections

**Workflow Router (`workflow.py`)**
- Prefix: `/api/v1/agent/workflows`
- Endpoints: Workflow management

## Architectural Notes

### Split Agent Functionality

Agent-related operations are split between two routers:

**Agents Router** (`agents.py` - `/v1/agents/*`):
- Core registration and lifecycle
- Status updates
- Heartbeat handling
- Direct agent queries by ID

**Messages Router** (`messages.py` - `/api/v1/agent/messages/*`):
- Agent discovery by service/capability
- Registry statistics
- Messaging operations
- Load balancing
- Peer management

**Rationale:** This split appears to separate:
- Core agent lifecycle management (agents.py)
- Agent discovery and communication (messages.py)

### Endpoint Path Patterns

**Pattern 1: Explicit `/api` prefix**
- Routers with `prefix='/api/...'` keep their full prefix
- Examples: messages, auth, websocket, workflow

**Pattern 2: No prefix → `/v1`**
- Routers without prefix get `/v1` added
- Examples: agents, tasks, alerts, ai, monitoring

**Pattern 3: Custom prefix**
- Some routers have custom prefixes like `/swarm`
- These are used as-is

## Integration Test Path Updates

The following path corrections were made to integration tests:

### Auth Endpoints
- `/v1/auth/*` → `/api/v1/auth/*`

### Messaging Endpoints
- `/v1/messages/send` → `/api/v1/agent/messages/send`
- `/v1/messages/broadcast` → `/api/v1/agent/messages/broadcast`
- `/v1/messages/history` → `/api/v1/agent/messages/history`

### Load Balancer Endpoints
- `/v1/load-balancer/stats` → `/api/v1/agent/messages/load-balancer/stats`
- `/v1/load-balancer/strategy` → `/api/v1/agent/messages/load-balancer/strategy`

### Registry Endpoints
- `/v1/registry/stats` → `/api/v1/agent/messages/registry/stats`

### Agent Discovery Endpoints
- `/v1/agents/service/{service}` → `/api/v1/agent/messages/agents/service/{service}`
- `/v1/agents/capability/{capability}` → `/api/v1/agent/messages/agents/capability/{capability}`

### Agent Core Endpoints (No Change)
- `/v1/agents/register` - Stays in agents router
- `/v1/agents/discover` - Stays in agents router
- `/v1/agents/{agent_id}` - Stays in agents router
- `/v1/agents/{agent_id}/status` - Stays in agents router

## Future Improvements

### Potential Consolidation

The split between agents.py and messages.py for agent discovery could be consolidated:

**Option 1:** Move all agent operations to agents router
- Move discovery endpoints from messages to agents
- Keep messaging in messages router

**Option 2:** Create dedicated discovery router
- Extract all discovery operations
- Clear separation of concerns

### Current Status

The current architecture works but requires careful attention to:
- Which router contains which endpoints
- Correct path prefixes in tests
- The split between core agent operations and discovery/messaging

## Test Status

As of v0.4.17:
- 188 passed, 4 failed, 12 skipped, 18 errors
- 93.8% pass rate
- Remaining failures are due to missing backend implementations, not path issues
