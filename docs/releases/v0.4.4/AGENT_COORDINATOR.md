# Agent Coordinator Integration - v0.4.4

**Release**: v0.4.4
**Date**: June 3, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.4 integrates the Agent Coordinator with the Hermes messaging service, standardizes the port, and updates CLI coin requests to use the Agent Coordinator.

## Changes

### Port Standardization

- Port standardized to 8107 (from 8011)

### Hermes Integration

#### Router Integration
- Agent messaging router added to coordinator routers list
- Main.py conditionally applies /v1 prefix based on router's existing prefix

#### Message Handling
- Hermes service handles message routing and delivery
- Agent Coordinator manages agent lifecycle and coordination
- Integration enables agent-to-agent communication via Hermes

### CLI Updates

#### Coin Requests
- CLI coin requests updated to use Agent Coordinator
- agent_coordinator_url added to CLI config

#### Configuration

```bash
# node.env
agent_coordinator_url=http://localhost:8107
```

## Breaking Changes

- Agent Coordinator port changed from 8011 to 8107

## Migration Commands

```bash
# Update service configuration
sed -i 's/:8011/:8107/g' /etc/aitbc/node.env

# Update CLI configuration
aitbc config set agent_coordinator_url http://localhost:8107

# Restart service
systemctl restart aitbc-agent-coordinator
```

## Testing Results

- ✅ Agent Coordinator accessible on port 8107
- ✅ Hermes integration working
- ✅ CLI coin requests using Agent Coordinator

## Documentation

- Microservices migration documentation updated

---

*Last Updated: 2026-06-03*
