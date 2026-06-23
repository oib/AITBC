# Hermes Messaging Updates - v0.4.4

**Release**: v0.4.4
**Date**: June 3, 2026
**Status**: ✅ Released

## Overview

AITBC v0.4.4 updates the Hermes messaging service with port changes, endpoint updates, database path fixes, and Agent Coordinator integration.

## Changes

### Port and Endpoint Changes

#### Port Update
- Port updated from 8014 to 8103

#### Endpoint Changes
- Message endpoints updated from `/v1/hermes/messages` to `/api/v1/agent/messages`
- Polling daemon updated to use new endpoints
- Base handler updated for send and poll operations

### Database Path Fixes

#### Environment Configuration

```bash
# node.env
HERMES_DB_PATH=/var/lib/aitbc/data/hermes_coin_requests.db
```

#### Loading Order
1. HERMES_DB_PATH loaded from environment before storage imports
2. Fallback to DATA_DIR/hermes_coin_requests.db if not set
3. node.env loaded before environment variable setting
4. Dynamic getter functions for database URL generation
5. Explicit commit with logging for coin request storage

### Agent Coordinator Integration

#### Port Update
- Agent Coordinator port updated from 8011 to 8107

#### Router Integration
- agent_messaging router added to coordinator routers list
- Main.py conditionally applies /v1 prefix based on router's existing prefix
- CLI coin requests updated to use Agent Coordinator
- agent_coordinator_url added to CLI config

## Breaking Changes

- Hermes port changed from 8014 to 8103
- Hermes message endpoints changed from `/v1/hermes/messages` to `/api/v1/agent/messages`

## Migration Commands

```bash
# Update service configuration
sed -i 's/:8014/:8103/g' /etc/aitbc/node.env

# Update CLI configuration
aitbc config set agent_coordinator_url http://localhost:8107

# Restart services
systemctl restart aitbc-hermes
systemctl restart aitbc-agent-coordinator
```

## Testing Results

- ✅ Message send via /api/v1/agent/messages
- ✅ Message poll via /api/v1/agent/messages
- ✅ Database path configuration via HERMES_DB_PATH
- ✅ Agent Coordinator integration

## Documentation

- [AGENT_MESSAGING.md](../../../agents/AGENT_MESSAGING.md) — Updated endpoints

---

*Last Updated: 2026-06-03*
