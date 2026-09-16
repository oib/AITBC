# Networking Configuration

**Last Updated:** 2026-09-16

Configure networking for your blockchain node.

## Network Model

AITBC's live topology is **hub-and-followers over HTTPS**, not a peer-mesh of
inbound P2P connections:

- **Followers make outbound connections only.** A follower dials the hub's
  public endpoint (443) for the lease subscription (`POST /rpc/subscribe` →
  `WS /rpc/subscribe/ws`, heartbeats via `POST /rpc/heartbeat`) and pulls bulk
  catch-up over the hub's RPC. Followers need **no inbound ports** open.
- **Port 7070 is hub-internal.** It runs the `aitbc-blockchain-p2p` gossip
  relay on the hub only. Followers must not open or forward it.
- **Service ports stay behind nginx on the hub.** The API gateway (8201),
  blockchain RPC (8202), coordinator (8203), marketplace (8102), exchange
  (8106), agent-coordinator (8107), and explorer (8100) bind on the hub and
  are proxied — only **80/443 is public**.
- The node's `p2p_bind_port` setting (code default **8200**) only matters on
  the hub, where the relay wrapper binds 7070.

## Firewall Configuration

### Follower nodes

```bash
# No inbound rules needed for the blockchain — outbound HTTPS only.
# Keep SSH restricted as usual:
ufw allow from <operator-net> to any port 22
```

### Hub node

```bash
# Public surface is just the reverse proxy
ufw allow 80/tcp
ufw allow 443/tcp

# Everything else binds on the hub host behind nginx.
# Do NOT publish 7070, 8202, 8203, 8102, 8106, 8107, 8100 publicly.
# If a lab peer must reach the RPC directly, scope it:
ufw allow from <peer-ip> to any port 8202
```

### Port Forwarding

Only the hub needs forwarding, and only for the proxy:

- External 443 → hub:443 (nginx → internal service ports)

No NAT mapping is needed for 7070 or the service ports; followers never accept
inbound blockchain connections.

## Federated Mesh Architecture

AITBC supports a federated mesh network architecture with independent mesh islands, node hubs, and optional island bridging.

### Overview

- **Islands**: Independent P2P networks with UUID-based IDs and separate blockchains
- **Hubs**: Operator-controlled nodes (`is_hub=true` + the p2p relay + the
  public RPC/subscription endpoints) that provide peer lists and push blocks
- **Multi-Chain**: Nodes can run parallel bilateral/micro-chains
- **Bridging**: Optional connections between islands (requires mutual approval)

### Island Configuration

Configure island membership in `/etc/aitbc/blockchain.env` (shared) and
`/etc/aitbc/node.env` (per-node):

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
- `IS_HUB`: Set to `true` on the designated hub node (operator decision — see below)
- `ISLAND_CHAIN_ID`: Separate chain ID for this island
- `HUB_DISCOVERY_URL`: DNS endpoint for hub discovery
- `BRIDGE_ISLANDS`: Comma-separated list of islands to bridge (optional)

### Creating a New Island

```bash
aitbc node island create --island-name "eu-west" --chain-id "ait-island-eu-west"
```

This generates a new UUID and chain ID client-side. Actually standing up the
island is operator work: set `ISLAND_ID`/`ISLAND_CHAIN_ID` in the env files,
give the island its own `genesis.json` under `data/<chain_id>/`, and restart
the services.

### Joining an Existing Island

```bash
aitbc node island join --island-id <island-id> --island-name <island-name> --chain-id <chain-id> [--is-hub] [--hub hub.aitbc.bubuit.net]
```

The join call posts to the hub's `/rpc/islands/join` and requires the node's
`blockchain_rpc_api_key` to be accepted by the hub.

### Hub Registration

Hub status is **operator-controlled**, not self-serve: a node becomes a hub
when the operator sets `IS_HUB=true`, runs `aitbc-blockchain-p2p`, and fronts
the RPC/subscription endpoints with nginx. The hub registry is a discovery
directory for that arrangement, not a promotion mechanism:

```bash
# Record an already-operational hub in the Redis-backed discovery directory
aitbc node hub register --public-address <public-ip> --public-port 8202

# Remove the directory entry
aitbc node hub unregister

# List registered hubs
aitbc node hub list-hubs
```

Followers whitelist which hub they trust via `DEFAULT_PEER_RPC_URL` and
`trusted_proposers`; a registry entry alone does not make a node authoritative.

### Island Bridging

Bridging allows optional connections between islands (requires mutual approval):

```bash
# Request bridge to another island
aitbc node bridge request --target-island-id <target-island-id>

# Approve a bridge request
aitbc node bridge approve --request-id <request-id> --approving-node-id <approving-node-id>

# Reject a bridge request
aitbc node bridge reject --request-id <request-id> --reason "<reason>"

# List active bridges
aitbc node bridge list
```

### Multi-Chain Support

Nodes can run parallel bilateral/micro-chains alongside the default chain.
These are *secondary chain instances* on a running node — driven through
`POST /rpc/chains/start|stop` (X-API-Key gated):

```bash
# Start a new parallel chain (secondary chain instance on a running node)
aitbc blockchain start --chain-id <chain-id> --type micro

# Stop a parallel chain
aitbc blockchain stop --chain-id <chain-id>

# List chain instances
aitbc blockchain instances
```

Chain types:

- `bilateral`: Chain between two parties
- `micro`: Small chain for specific use case

> The `aitbc node chain start|stop|list-chains` commands are CLI stubs that
> print canned output without contacting the node — use the
> `aitbc blockchain` equivalents above.

## Sync and Peer Connectivity

There is no libp2p-style bootstrap list and no `peers add` command. Follower
connectivity is configured entirely through the environment:

```bash
# node.env (follower)
DEFAULT_PEER_RPC_URL=https://hub.aitbc.bubuit.net   # hub base URL, no /rpc
SUBSCRIPTION_ENABLED=true
SUBSCRIPTION_TRANSPORT=websocket
BLOCKCHAIN_RPC_API_KEY=<key>   # must be present in the hub's
                             # BLOCKCHAIN_RPC_API_KEY_PEERS
TRUSTED_PROPOSERS=0x<proposer>,...   # optional extra proposer filter
```

The hub accepts the subscription only when the presented `X-API-Key` is listed
in its `BLOCKCHAIN_RPC_API_KEY_PEERS`. After that the follower holds
`wss://<hub>/rpc/subscribe/ws` open and renews the lease with heartbeats;
missed ranges are filled by automatic bulk pull-sync.

## NAT Traversal

Because followers only dial out, NAT traversal is mostly a non-issue. STUN is
supported for nodes that do need to discover or advertise a public endpoint
(e.g. hub candidates):

```bash
# Comma-separated STUN servers
STUN_SERVERS=stun.l.google.com:19302,jitsi.bubuit.net:3478

# TURN relay (future support)
TURN_SERVER=jitsi.bubuit.net:3478
```

## Troubleshooting

### Check connectivity to the hub

```bash
# From a follower — the subscribe flow uses plain HTTPS
curl -s https://hub.aitbc.bubuit.net/rpc/status
curl -s https://hub.aitbc.bubuit.net/rpc/network-info

# Follow the subscribe/heartbeat loop in the node log
journalctl -u aitbc-blockchain-node -f | grep -iE "subscri|heartbeat|lease"
```

### List known islands and hubs

```bash
aitbc node island list
aitbc node hub list-hubs
```

### Inspect sync state

```bash
aitbc blockchain sync-status
aitbc blockchain height
```

### Debug logging

Raise the log level in the environment and restart the unit:

```bash
# /etc/aitbc/blockchain.env
LOG_LEVEL=DEBUG
```

```bash
systemctl restart aitbc-blockchain-node
journalctl -u aitbc-blockchain-node -f
```

## DNS Configuration for Hub Discovery

Add A records for hub discovery:

```
# hub.example.net
hub1.example.net A 10.1.1.1
hub2.example.net A 10.1.1.2
hub3.example.net A 10.1.1.3
```

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
- [Multi-Chain Architecture](./7_multichain.md) - Multi-chain management
