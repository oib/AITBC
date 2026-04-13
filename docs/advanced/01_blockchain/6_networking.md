# Networking Configuration
Configure P2P networking for your blockchain node.

## Network Settings

### Firewall Configuration

```bash
# Allow P2P port
sudo ufw allow 7070/tcp

# Allow RPC port
sudo ufw allow 8080/tcp

# Allow from specific IPs
sudo ufw allow from 10.0.0.0/8 to any port 8080
```

### Port Forwarding

If behind a NAT, configure port forwarding:
- External port 7070 → Internal IP:7070
- External port 8080 → Internal IP:8080

## Federated Mesh Architecture

AITBC supports a federated mesh network architecture with independent mesh islands, node hubs, and optional island bridging.

### Overview

- **Islands**: Independent P2P networks with UUID-based IDs and separate blockchains
- **Hubs**: Any node can volunteer as a hub to provide peer lists
- **Multi-Chain**: Nodes can run parallel bilateral/micro-chains
- **Bridging**: Optional connections between islands (requires mutual approval)

### Island Configuration

Configure your node's island membership in `/etc/aitbc/.env`:

```bash
# Island Configuration
ISLAND_ID=550e8400-e29b-41d4-a716-446655440000
ISLAND_NAME=default
IS_HUB=false
ISLAND_CHAIN_ID=ait-island-default
HUB_DISCOVERY_URL=hub.aitbc.bubuit.net
BRIDGE_ISLANDS=
```

**Configuration Fields**:
- `ISLAND_ID`: UUID-based island identifier (auto-generated if not set)
- `ISLAND_NAME`: Human-readable island name
- `IS_HUB`: Set to `true` if this node acts as a hub
- `ISLAND_CHAIN_ID`: Separate chain ID for this island
- `HUB_DISCOVERY_URL`: DNS endpoint for hub discovery
- `BRIDGE_ISLANDS`: Comma-separated list of islands to bridge (optional)

### Creating a New Island

```bash
aitbc node island create --island-name "eu-west" --chain-id "ait-island-eu-west"
```

This generates a new UUID for the island and sets up a separate blockchain.

### Joining an Existing Island

```bash
aitbc node island join <island-id> <island-name> <chain-id> [--is-hub]
```

### Hub Registration

Any node can register as a hub to provide peer lists:

```bash
aitbc node hub register --public-address <public-ip> --public-port 7070
```

To unregister as a hub:

```bash
aitbc node hub unregister
```

### Island Bridging

Bridging allows optional connections between islands (requires mutual approval):

```bash
# Request bridge to another island
aitbc node bridge request <target-island-id>

# Approve a bridge request
aitbc node bridge approve <request-id> <approving-node-id>

# Reject a bridge request
aitbc node bridge reject <request-id> --reason "<reason>"

# List active bridges
aitbc node bridge list
```

### Multi-Chain Support

Nodes can run parallel bilateral/micro-chains alongside the default chain:

```bash
# Start a new parallel chain
aitbc node chain start <chain-id> --chain-type micro

# Stop a parallel chain
aitbc node chain stop <chain-id>

# List active chains
aitbc node chain list
```

Chain types:
- `bilateral`: Chain between two parties
- `micro`: Small chain for specific use case

## Bootstrap Nodes

### Default Bootstrap Nodes

```yaml
p2p:
  bootstrap_nodes:
    - /dns4/node-1.aitbc.com/tcp/7070/p2p/12D3KooW...
    - /dns4/node-2.aitbc.com/tcp/7070/p2p/12D3KooW...
    - /dns4/node-3.aitbc.com/tcp/7070/p2p/12D3KooW...
```

### Adding Custom Bootstrap Nodes

```bash
aitbc-chain p2p add-bootstrap /dns4/my-node.example.com/tcp/7070/p2p/...
```

## Peer Management

### Connection Limits

```yaml
p2p:
  max_peers: 50
  min_peers: 5
  outbound_peers: 10
  inbound_peers: 40
```

### Peer Scoring

Nodes are scored based on:
- Latency
- Availability
- Protocol compliance
- Block propagation speed

## NAT Traversal

### Supported Methods

| Method | Description |
|--------|-------------|
| STUN | Public IP discovery via STUN servers |
| AutoNAT | Automatic NAT detection |
| Hole Punching | UDP hole punching (future) |
| Relay | TURN relay fallback (future) |

### Configuration

```bash
# STUN Servers (comma-separated)
STUN_SERVERS=stun.l.google.com:19302,jitsi.bubuit.net:3478

# TURN Server (future)
TURN_SERVER=jitsi.bubuit.net:3478
```

### STUN Discovery

Nodes automatically discover their public endpoint via STUN servers configured in the environment. This enables nodes behind NAT to participate in the mesh network.

## Troubleshooting

### Check Connectivity

```bash
aitbc-chain p2p check-connectivity
```

### List Active Connections

```bash
aitbc-chain p2p connections
```

### List Known Islands

```bash
aitbc node island list
```

### List Known Hubs

```bash
aitbc node hub list
```

### Debug Mode

```bash
aitbc-chain start --log-level debug
```

## DNS Configuration for Hub Discovery

Add A records for hub discovery:

```
# hub.aitbc.bubuit.net
hub1.aitbc.bubuit.net A 10.1.1.1
hub2.aitbc.bubuit.net A 10.1.1.2
hub3.aitbc.bubuit.net A 10.1.1.3
```

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
