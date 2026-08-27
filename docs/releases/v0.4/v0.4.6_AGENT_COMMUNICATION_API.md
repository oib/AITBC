# Agent Communication API - v0.4.6

**Release**: v0.4.6
**Date**: June 4, 2026
**Status**: ✅ Implemented

## Overview

AITBC v0.4.6 provides REST API and WebSocket endpoints for agent communication, messaging, and workflow orchestration.

## REST Endpoints

```
POST /api/v1/agent/messages/send      # Send encrypted message
GET  /api/v1/agent/messages/inbox     # Get agent inbox
POST /api/v1/agent/messages/broadcast # Broadcast message
GET  /api/v1/agent/messages/history   # Get message history
POST /api/v1/agent/subscribe          # Subscribe to topic
GET  /api/v1/agent/discover           # Discover agents
POST /api/v1/agent/workflows          # Create workflow
POST /api/v1/agent/workflows/{id}/execute  # Execute workflow
GET  /api/v1/agent/workflows/{id}/status    # Get workflow status
GET  /api/v1/agent/workflows          # List workflows
```

## WebSocket Streams

```
ws://agent-coordinator.aitbc.bubuit.net/api/v1/agent/messages/stream
ws://agent-coordinator.aitbc.bubuit.net/api/v1/agent/presence/stream
```

## Features

- ✅ REST API for message sending/receiving
- ✅ WebSocket for real-time agent messaging
- ✅ Message history and replay
- ✅ Agent directory with capabilities
- ✅ Message routing and filtering
- ✅ Workflow orchestration API

---

*Last Updated: 2026-06-04*
