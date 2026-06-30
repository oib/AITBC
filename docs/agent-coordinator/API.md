# AITBC Agent Coordinator - API Reference

**Last Updated:** 2026-06-30
**Version:** 2.0 (Split into topic-focused files)

> **Important:** This document describes the Agent Coordinator API. The Agent Coordinator service runs on port 9001. For the Coordinator API (job submission), use port 8203. For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).
>
> **🟢 Service Status**: Coordinator API is operational on port 8203 with all Agent endpoints functioning.

## Documentation Structure

This API reference has been split into topic-focused files for easier navigation:

### API Endpoints

- **[Agent Management API](./api-agent-management.md)** - Register, discover, and manage agents
- **[Task Management API](./api-task-management.md)** - Submit tasks and monitor distribution
- **[Message Management API](./api-message-management.md)** - Send, broadcast, and retrieve messages
- **[Peer Management API](./api-peer-management.md)** - Manage peer connections between agents
- **[API Reference](./api-reference.md)** - Health checks, error codes, rate limiting, and OpenAPI

## Quick Navigation

**For Agent Registration:**
1. Start with [Agent Management API](./api-agent-management.md)
2. Register your agent using the `/agents/register` endpoint
3. Discover other agents using `/agents/discover`

**For Task Distribution:**
1. Review [Task Management API](./api-task-management.md)
2. Submit tasks using `/tasks/submit`
3. Monitor task status using `/tasks/status`

**For Agent Communication:**
1. See [Message Management API](./api-message-management.md)
2. Send direct messages using `/messages/send`
3. Broadcast to multiple agents using `/messages/broadcast`

**For Peer Connections:**
1. Check [Peer Management API](./api-peer-management.md)
2. Add peer connections using `/peers/add`
3. Query peer networks using `/peers`

## Base URL

```
http://localhost:9001
```

## Authentication

Currently, the API does not require authentication. Future versions may support API key authentication and JWT tokens.

---

**Note**: This file has been split into topic-focused files for easier navigation. See the [Documentation Structure](#documentation-structure) section above for links to the individual API endpoint files.
