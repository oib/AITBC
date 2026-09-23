# WebSocket API Documentation

> **Important:** This document describes the WebSocket API endpoints. For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md).

The AITBC blockchain node exposes exactly **two** WebSocket endpoints, both mounted under `/rpc` on the blockchain node (default port `8202`):

| Endpoint | Purpose | Authentication |
|---|---|---|
| `WS /rpc/subscribe/ws` | Follower-node block subscription push channel | Prior lease from `POST /rpc/subscribe` (peer key) |
| `WS /rpc/gossip/ws?topic=<topic>` | Bidirectional gossip pub/sub bridged into the node's gossip broker | Signed validator challenge for restricted topics |

> The coordinator-api (port 8203) and the market service (port 8102) expose **no** WebSocket endpoints. Job status is polled over REST (`GET /v1/jobs/{job_id}`).
>
> There is no `?api_key=` query-parameter authentication on either WebSocket endpoint. `POST /rpc/subscribe` is authenticated with the `X-API-Key` header (peer key) and the gossip socket authenticates with an in-band signed challenge — see below.

## Connection URLs

- Development: `ws://localhost:8202/rpc/subscribe/ws` and `ws://localhost:8202/rpc/gossip/ws?topic=<topic>`
- Production (public hub, via nginx): `wss://hub.example.net/rpc/subscribe/ws` and `wss://hub.example.net/rpc/gossip/ws?topic=<topic>`

The raw `http://hub.example.net:8202` address is internal-only; external clients go through the nginx TLS endpoint.

## Block subscription — `WS /rpc/subscribe/ws`

This is the channel follower nodes use to receive pushed blocks. The WebSocket alone is **not** sufficient — the server validates that the connecting `node_id` holds a valid lease, which is created out-of-band over REST first.

### Step 1 — acquire a lease

```bash
curl -X POST https://hub.example.net/rpc/subscribe \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <PEER_KEY>" \
  -d '{"node_id": "<your-node-id>", "chain_id": "ait-hub.aitbc.bubuit.net", "transport": "websocket"}'
```

`X-API-Key` must be the node's own RPC key or one of the peer keys listed in the hub's `BLOCKCHAIN_RPC_API_KEY_PEERS` environment variable. Without a valid key the subscribe call returns `403`.

Leases are extended with `POST /rpc/heartbeat` (same peer-key auth). The current lease status can be checked with `GET /rpc/lease/{node_id}`.

### Step 2 — connect and identify

```python
import asyncio
import json
import websockets

async def follow_blocks(node_id: str, chain_id: str):
    uri = "wss://hub.example.net/rpc/subscribe/ws"

    async with websockets.connect(uri) as websocket:
        # First message MUST be the subscription handshake.
        await websocket.send(json.dumps({
            "node_id": node_id,
            "chain_id": chain_id,
            "transport": "websocket",
        }))

        async for message in websocket:
            data = json.loads(message)
            if data.get("status") == "subscribed":
                print("Subscribed:", data)
            elif data.get("type") == "ping":
                continue  # server heartbeat every ~20s
            elif "error" in data:
                print("Server error:", data["error"])
                break
            else:
                print("New block:", data.get("height", data))

asyncio.run(follow_blocks("my-node-1", "ait-hub.aitbc.bubuit.net"))
```

Protocol details (from `apps/blockchain-node/src/aitbc_chain/rpc/websocket.py`):

- The first client message must be JSON with `node_id` (required), `chain_id` (defaults to the node's own `CHAIN_ID`), and `transport` (`"websocket"`).
- If no valid lease exists for `(node_id, chain_id)` the server sends `{"error": "No valid lease found. Register subscription first via POST /rpc/subscribe"}` and closes with code `1008`.
- On success the server replies `{"status": "subscribed", ...}` and forwards every message published on the `blocks.<chain_id>` gossip topic.
- The server sends `{"type": "ping", "timestamp": ...}` every 20 seconds; there is no required client pong message.

## Gossip — `WS /rpc/gossip/ws?topic=<topic>`

A bidirectional channel bridged into the node's internal gossip broker. Used by validators to exchange consensus traffic and available to anyone for subscribing.

### Topics

- **Restricted** (publish requires validator authentication): `blocks`, `pbft`, `consensus`, and any dotted sub-topic such as `blocks.ait-hub.aitbc.bubuit.net`.
- **Public** (anyone may publish, still rate-limited): `transactions`, `status`, `mempool`, and any dotted sub-topic.
- Any other topic: subscribing is possible, but publishing is rejected unless the connection is validator-authenticated.

### Validator authentication handshake

When `GOSSIP_AUTH_ENABLED=true` (default) and the topic is restricted, the server sends an auth challenge immediately after accepting the connection:

```json
{"type": "auth_challenge", "challenge": "<uuid>", "timestamp": 1720000000.0}
```

The client signs `{"challenge": ..., "address": ..., "timestamp": ...}` with its validator secp256k1 key (the consensus-signing scheme) and replies:

```json
{"type": "auth_response", "address": "0x...", "challenge": "<uuid>", "timestamp": 1720000000.0, "signature": "0x..."}
```

The server verifies that the address is in `VALIDATOR_SET`, that the challenge matches, that the timestamp is within `GOSSIP_AUTH_CHALLENGE_TTL` (default 60 s), and that the signature is valid. On success it answers `{"type": "auth_ok", "address": "0x..."}`; on failure it sends an `{"error": ...}` message and closes with code `1008`.

### Example (Python)

```python
import asyncio
import json
import websockets

async def watch_mempool():
    uri = "ws://localhost:8202/rpc/gossip/ws?topic=mempool"
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            print(data)

asyncio.run(watch_mempool())
```

### Limits (server-enforced, configurable via env)

| Env var | Default | Effect |
|---|---|---|
| `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP` | `32` | Excess connections from one source IP are closed with `1008` |
| `GOSSIP_MAX_MESSAGES_PER_MINUTE` | `2000` | Per `(client_ip, topic)` publish rate; excess messages get `{"error": "Rate limit exceeded"}` |
| `GOSSIP_MAX_MESSAGE_SIZE` | `1048576` (1 MiB) | Larger messages get `{"error": "Message too large"}` and close `1009` |
| `GOSSIP_AUTH_CHALLENGE_TTL` | `60.0` | Seconds a validator challenge stays valid |

Additionally, a client-to-server message is expected within each 60-second window; the server replies with a `{"type": "ping"}` keepalive on timeout rather than disconnecting.

## Connection management

The same general guidance applies: implement reconnection with exponential backoff, handle `websockets.exceptions.ConnectionClosed`, and log the connection lifecycle. For `/rpc/subscribe/ws`, remember to re-register (`POST /rpc/subscribe`) or heartbeat (`POST /rpc/heartbeat`) when the server reports an expired lease — reconnecting the socket without a valid lease is immediately rejected.

## Security considerations

- Use `wss://` in production. The public endpoint is `wss://hub.example.net/rpc/...` behind nginx TLS termination.
- Keep peer keys and validator private keys out of client-side code and out of the repo.
- A peer key only ever unlocks lease management (`/rpc/subscribe`, `/rpc/heartbeat`, lease revocation); it does not authorize governance, chain control, or settlement routes.

## Troubleshooting

- **`{"error": "No valid lease found..."}` on `/rpc/subscribe/ws`** — register first via `POST /rpc/subscribe` with a valid peer key, or renew via `POST /rpc/heartbeat`.
- **Closed with `1008` on `/rpc/gossip/ws`** — missing `?topic=` parameter, per-IP connection cap hit, or a failed/missing validator auth on a restricted topic.
- **Closed with `1009`** — message exceeded `GOSSIP_MAX_MESSAGE_SIZE` (default 1 MiB).
- **`{"error": "Not a validator"}`** — the `address` in `auth_response` is not in the node's `VALIDATOR_SET`.
- **Connection refused on `:8202`** — that port is internal-only; use the nginx `wss://hub.example.net/rpc/...` path.
