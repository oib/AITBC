# AITBC Setup - Subscription System

**Last Updated**: 2026-06-30
**Version**: 1.0

## Lease-Based Subscription System

The blockchain node supports a lease-based push synchronization mechanism for efficient block propagation from hub to followers. Followers do **not** need the `aitbc-blockchain-p2p` service (port 7070) — that is a hub-only internal gossip relay. Followers receive blocks via the subscription system over the hub's RPC endpoint.

### Hub Configuration

Set `BLOCKCHAIN_MODE=hub` on hub nodes to enable:

- Block production and broadcasting
- Redis lease tracker for subscriber management
- Subscription RPC endpoints for follower registration
- WebSocket block push on `/rpc/subscribe/ws`

### Follower Configuration

Set `BLOCKCHAIN_MODE=follower` on follower nodes to enable:

- Subscription client connects to hub's RPC URL (`default_peer_rpc_url`)
- Registers a lease via `POST /rpc/subscribe`
- Receives blocks via WebSocket on `wss://hub.example.net/rpc/subscribe/ws`
- Automatic lease renewal via heartbeat (`POST /rpc/heartbeat`)
- Falls back to periodic pull sync if subscription fails

### Subscription Settings

Configure in `/etc/aitbc/blockchain.env`:

```bash
# Required: Hub RPC URL for follower subscription
default_peer_rpc_url=https://hub.example.net
# (bare base URL, no /rpc suffix — the client appends /rpc/subscribe etc. itself; https, not http)

# Lease-based subscription settings (followers)
subscription_enabled=true
subscription_transport=websocket
```

### Subscription RPC Endpoints

Hub nodes provide these endpoints (proxied through nginx):

**HTTP endpoints** (via `/rpc/` nginx proxy):

- `POST /rpc/subscribe` - Register for block subscription with lease
- `POST /rpc/heartbeat` - Extend subscription lease via heartbeat
- `GET /rpc/lease/{node_id}` - Get lease status for a subscriber
- `DELETE /rpc/lease/{node_id}` - Revoke subscription lease
- `GET /rpc/subscribers` - Get all valid subscribers

**WebSocket endpoints** (via nginx with upgrade headers):

- `wss://hub.example.net/rpc/subscribe/ws` - Real-time block push to subscribed followers
- `wss://hub.example.net/rpc/gossip/ws` - Gossip WebSocket (validators/peers)

(There are no `/rpc/blocks` or `/rpc/transactions` WebSocket routes — the
chain RPC exposes only `/rpc/subscribe/ws` and `/rpc/gossip/ws`.)

## Sync Modes

The blockchain node supports two synchronization modes for block propagation:

### Pull Sync (Periodic)

- **Default mode** for follower nodes
- Periodically polls the hub for new blocks
- Configurable interval (default: 30 seconds)
- Always available as fallback
- Settings in `/etc/aitbc/blockchain.env`:

  ```bash
  PERIODIC_SYNC_ENABLED=true
  PERIODIC_SYNC_INTERVAL=30
  ```

### Push Sync (Subscription)

- **Efficient mode** when subscription is enabled
- Hub pushes blocks to subscribed followers via WebSocket (`/rpc/subscribe/ws`)
- Requires valid lease (DHCP-style subscription)
- Automatic lease renewal via heartbeat
- Falls back to pull sync if subscription fails
- Settings in `/etc/aitbc/blockchain.env`:

  ```bash
  subscription_enabled=true
  subscription_transport=websocket
  default_peer_rpc_url=https://hub.example.net
# (bare base URL, no /rpc suffix — the client appends /rpc/subscribe etc. itself; https, not http)
  ```

### Sync Mode Selection

The node automatically selects the sync mode based on configuration:

- If `subscription_enabled=true` and hub is available → **Push sync** (WebSocket)
- If subscription fails or hub unavailable → **Pull sync (fallback)**
- If `subscription_enabled=false` → **Pull sync only**

The current sync mode is logged at startup and can be monitored via:

```bash
journalctl -u aitbc-blockchain-node -f | grep "Sync mode"
```

## Related Topics

- [Quick Start](./setup-quick-start.md) - Installation and profiles
- [Service Selection](./setup-service-selection.md) - Role-based service configuration
- [Configuration](./setup-configuration.md) - Runtime directories, secrets, and environment files
- [Security](./setup-security.md) - Service user security
- [Reference](./setup-reference.md) - Common commands, troubleshooting, and links
