# Blockchain Event Bridge

Bridge between AITBC blockchain events and OpenClaw agent triggers using a hybrid event-driven and polling approach.

## Overview

This service connects AITBC blockchain events (blocks, transactions, smart contract events) to OpenClaw agent actions through:
- **Event-driven**: Subscribe to gossip broker topics for real-time critical triggers
- **Polling**: Periodic checks for batch operations and conditions
- **Smart Contract Events**: Monitor contract events via blockchain RPC (Phase 2)

## Features

- Subscribes to blockchain block events via gossip broker
- Subscribes to transaction events (when available)
- Monitors smart contract events via blockchain RPC:
  - AgentStaking (stake creation, rewards, tier updates)
  - PerformanceVerifier (performance verification, penalties, rewards)
  - AgentServiceMarketplace (service listings, purchases)
  - BountyIntegration (bounty creation, completion)
  - CrossChainBridge (bridge initiation, completion)
- Triggers coordinator API actions based on blockchain events
- Triggers agent daemon actions for agent wallet transactions
- Triggers marketplace state updates
- Configurable action handlers (enable/disable per type)
- Prometheus metrics for monitoring
- Health check endpoint

## Installation

```bash
cd apps/blockchain-event-bridge
poetry install
```

## Configuration

Environment variables:

- `BLOCKCHAIN_RPC_URL` - Blockchain RPC endpoint (default: `http://localhost:8006`)
- `GOSSIP_BACKEND` - Gossip broker backend: `memory`, `broadcast`, or `redis` (default: `memory`)
- `GOSSIP_BROADCAST_URL` - Broadcast URL for Redis backend (optional)
- `COORDINATOR_API_URL` - Coordinator API endpoint (default: `http://localhost:8011`)
- `COORDINATOR_API_KEY` - Coordinator API key (optional)
- `SUBSCRIBE_BLOCKS` - Subscribe to block events (default: `true`)
- `SUBSCRIBE_TRANSACTIONS` - Subscribe to transaction events (default: `true`)
- `ENABLE_AGENT_DAEMON_TRIGGER` - Enable agent daemon triggers (default: `true`)
- `ENABLE_COORDINATOR_API_TRIGGER` - Enable coordinator API triggers (default: `true`)
- `ENABLE_MARKETPLACE_TRIGGER` - Enable marketplace triggers (default: `true`)
- `ENABLE_POLLING` - Enable polling layer (default: `false`)
- `POLLING_INTERVAL_SECONDS` - Polling interval in seconds (default: `60`)

## Running

### Development

```bash
poetry run uvicorn blockchain_event_bridge.main:app --reload --host 127.0.0.1 --port 8204
```

### Production (Systemd)

```bash
sudo systemctl start aitbc-blockchain-event-bridge
sudo systemctl enable aitbc-blockchain-event-bridge
```

## API Endpoints

- `GET /` - Service information
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics

## Architecture

```
blockchain-event-bridge/
├── src/blockchain_event_bridge/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Settings
│   ├── bridge.py            # Core bridge logic
│   ├── metrics.py           # Prometheus metrics
│   ├── event_subscribers/   # Event subscription modules
│   ├── action_handlers/     # Action handler modules
│   └── polling/             # Polling modules
└── tests/
```

## Event Flow

1. Blockchain publishes block event to gossip broker (topic: "blocks")
2. Block event subscriber receives event
3. Bridge parses block data and extracts transactions
4. Bridge triggers appropriate action handlers:
   - Coordinator API handler for AI jobs, agent messages
   - Agent daemon handler for agent wallet transactions
   - Marketplace handler for marketplace listings
5. Action handlers make HTTP calls to respective services
6. Metrics are recorded for monitoring

## CLI Commands

The blockchain event bridge service includes CLI commands for management and monitoring:

```bash
# Health check
aitbc-cli bridge health

# Get Prometheus metrics
aitbc-cli bridge metrics

# Get detailed service status
aitbc-cli bridge status

# Show current configuration
aitbc-cli bridge config

# Restart the service (via systemd)
aitbc-cli bridge restart
```

All commands support `--test-mode` flag for testing without connecting to the service.

## Testing

```bash
poetry run pytest
```

## Future Enhancements

- Phase 2: Smart contract event subscription
- Phase 3: Enhanced polling layer for batch operations
- WebSocket support for real-time event streaming
- Event replay for missed events
