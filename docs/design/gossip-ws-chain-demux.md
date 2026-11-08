# Gossip WS chain demux — `?chain=<id>` on `/rpc/gossip/ws`

Status: **phase 1 implemented** (RPC-GOSSIP-CHAIN-DEMUX-1 / #1159) —
`?chain=<id>` + per-chain broker registry + `(ip,chain)` accounting +
chain-bound auth scope (rollout flag off) + client `?chain=` dialer.
Consensus-adjacent transport change — Phase B (client chain-bound signing,
mesh peer-URL migration, `:8302` retirement) remains gated on megaplan
sign-off and `GOSSIP_AUTH_REQUIRE_CHAIN_SCOPE` flip.

## Problem

Today one gossip WebSocket route serves exactly one chain per process:

- `gossip_websocket` (`apps/blockchain-node/src/aitbc_chain/rpc/websocket.py`)
  binds to the process-wide singleton `gossip_broker`, which wraps a single
  `GossipBackend` created once at startup from `settings.chain_id` /
  `GOSSIP_BACKENDS` / `GOSSIP_MESH_PEER_URLS`.
- Multi-island fleets therefore run **one process (and one port) per island** —
  e.g. node1 exposes `/island/` → `:8302` in nginx while the default chain
  lives on the main port. Peer URLs are per-port
  (`wss://host:8302/rpc/gossip/ws`), nginx needs per-island location blocks,
  and every additional island adds a unit + port + proxy stanza.

Goal: `wss://peer/rpc/gossip/ws?chain=<id>` — one route per host serves every
chain the process supports, with a chain→broker registry inside one process.

## Current state (verified at `eea3927e0`)

| Piece | Location | Notes |
|---|---|---|
| WS endpoint | `rpc/websocket.py::gossip_websocket` | `?topic=` only; no chain param |
| Broker | `gossip/broker.py::GossipBroker` | single backend, dedup, priority queue |
| Backend factory | `gossip/broker.py::create_backend` | broadcast / websocket / mesh / in-memory |
| Per-chain backends config | `config.py` `GOSSIP_BACKENDS` | already accepts `chain_id:redis://url` entries — the config grammar for multi-chain exists |
| Mesh peers | `GOSSIP_MESH_PEER_URLS` → `settings.mesh_peer_url_list()` | plain URL list, no chain dimension |
| Per-island unit | `:8302` + nginx `/island/` map | deployment workaround this design removes |
| Per-IP counter | `_gossip_ip_connections` | keyed on IP only — must become `(ip, chain)` |
| Topic naming | dotted topics (`transactions.{chain_id}`) already used by publishers | chain scoping partially exists at topic level, NOT enforced |

## Design

### 1. Chain parameter and resolution

- `gossip_websocket` accepts `chain` (alias `chain_id`) query param.
- Resolution order: explicit `?chain=` → `settings.chain_id` (single-chain
  processes unchanged) → reject 4400/close 1008 when the chain is not in the
  process's supported set. Supported set = `settings.supported_chains`
  (CSV) ∪ `chain_id`, intersected with configured backends.
- **No guessing**: absent param on a multi-chain process is an error, not a
  default — silent default-chain routing is how cross-chain leaks start.

### 2. Broker registry

- Replace the module-global `gossip_broker` usage inside `gossip_websocket`
  with `GossipBrokerRegistry`:
  - `registry.get(chain_id) -> GossipBroker` — lazily constructs a
    `GossipBroker` per chain from that chain's backend spec.
  - Backend spec resolution per chain:
    1. `GOSSIP_BACKENDS` entry `chain_id:<url>` (existing grammar) →
       `create_backend` on that URL.
    2. `GOSSIP_MESH_PEER_URLS` filtered to URLs carrying `?chain=<id>` or a
       `chain_id:` prefix → mesh backend for that chain.
    3. Fallback: the process default backend ONLY when the chain equals
       `settings.chain_id` (preserves today's single-chain behavior).
  - Each `GossipBroker` keeps its own dedup cache, priority queue and drain
    task — isolation is per-chain by construction.
- Registry lifecycle: started/stopped with the app; `shutdown()` iterates all
  brokers. Metrics get a `chain_id` label on broker-level series.

### 3. Topic isolation (the "can't cross" invariant)

- On subscribe AND publish inside `gossip_websocket`, enforce:
  `topic_chain(topic) == connection.chain` where `topic_chain` extracts the
  dotted suffix (`transactions.bc-2` → `bc-2`); bare topics are allowed only
  when they are in a per-chain allowlist reviewed for that chain's role
  (e.g. legacy bare `transactions` stays bound to the connection's chain —
  it can never reach another chain's broker because the broker object itself
  is per-chain).
- The isolation guarantee is **structural**: a connection bound to chain A
  holds a `TopicSubscription` from chain A's broker only. There is no code
  path that hands it chain B's subscription. Pins assert this.

### 4. Peer URL format

- Uniform: `wss://<host>/rpc/gossip/ws?chain=<chain_id>` (path unchanged,
  chain in query — survives existing nginx `location /rpc/gossip/ws` blocks).
- `GOSSIP_MESH_PEER_URLS` entries gain an optional chain selector:
  `wss://host/rpc/gossip/ws?chain=bc-2` or legacy `chain_id:wss://...` prefix
  (mirrors `GOSSIP_BACKENDS` grammar). Mesh backend appends `&topic=` as
  today; the chain param rides along untouched.
- Peer URL validation at startup: reject entries whose `chain=` names a
  chain this process does not serve (fail-fast, same style as
  `validate_gossip_backends`).

### 5. Connection accounting — `(ip, chain)` keying

- `_gossip_ip_connections` becomes `dict[tuple[str, str], int]` keyed
  `(client_ip, chain_id)`. Limits (`gossip_max_concurrent_connections_per_ip`)
  apply per (ip, chain): one host may hold N connections per chain it
  legitimately serves, and a single chain can't be starved by another.
- `gossip_open_connections` / `gossip_authenticated_connections` gain a
  `chain_id` label. Auth (`gossip_auth`) challenge/verify stays per
  connection; `channel_scope(topic)` already namespaces by topic — extend
  it to include chain so a validator signature for chain A cannot authorize
  publishes on chain B.

**Metrics and aggregate ceilings (#1257).**
`blockchain_gossip_ws_rejected_total{chain,topic_class,reason}` counts refusals
(`unknown_chain`, `cross_chain_topic`, `no_backend`, `conn_cap`,
`conn_cap_total`, `rate`, `rate_total`, `auth`) and
`blockchain_gossip_ws_open_connections{chain}` the live connections. `chain` is
a served chain id or the literal `unknown`; an unserved chain string is never
echoed as a label. The per-chain limits multiply with the number of served
chains (K): per source IP, up to K x `GOSSIP_MAX_CONCURRENT_CONNECTIONS_PER_IP`
connections and K x 5 x `GOSSIP_MAX_MESSAGES_PER_MINUTE` messages/min.
`GOSSIP_MAX_CONNECTIONS_PER_IP_TOTAL` and `GOSSIP_MAX_MESSAGES_PER_MINUTE_TOTAL`
cap the sum across chains; both default to 0 (off), so K = 1 is unchanged.
All of these counters are process-local and `aitbc-blockchain-rpc` runs two uvicorn
workers, so every ceiling here (and the challenge-mint rate) is effectively doubled
per source IP; accepted as the real bound by the operator (#1249), see
`docs/api/websocket.md`.
Rate-bucket headroom: `RateLimiter` tracks at most 100 000 keys and evicts the
stalest at the cap (the owner gets a fresh window, never a lockout). Each
source IP holds at most 5 x K bucket keys, so the cap is reached at about
20 000 distinct active IPs for K = 1 and about 6 600 for K = 3; the aggregate
message ceiling adds one key per IP in a separate limiter.

### 6. Migration story (per-island `:8302` units)

Phase A (additive, no behavior change):
1. Ship `?chain=` support; processes serving one chain keep working with or
   without the param (param optional iff `supported_chains` has exactly one
   entry).
2. Update `GOSSIP_MESH_PEER_URLS` on each node to the `?chain=` form.
3. nginx: keep `/island/` → `:8302` working; add `?chain=` passthrough (query
   strings pass through proxy_pass unchanged — verify per-location).

Phase B (consolidation, per island, reversible):
4. Point the island's peer URLs at the main port with `?chain=<island-chain>`.
5. Confirm mesh subscription/publish flows on the new route (pins + live
   journal: `Mesh gossip peer ... subscribed`).
6. Stop the `:8302` unit; remove its nginx stanza after a soak window.
7. Delete per-island unit files only after all peers show the new URLs.

Rollback at every phase = revert env + restart; the old route keeps working
because `?chain=` is additive.

### 7. Pins / tests (required before implementation sign-off)

- `test_gossip_ws_chain_demux`: two chains configured; connect
  `?chain=A&topic=transactions` and `?chain=B&topic=transactions`; publish on
  A → only A's subscriber receives; B sees nothing (cross-chain leak pin).
- `test_gossip_ws_chain_required`: multi-chain process, missing `chain` →
  close 1008; unknown chain → close 1008.
- `test_gossip_ws_ip_chain_counter`: same IP, two chains → independent
  counters; exceeding per-(ip,chain) limit on A doesn't affect B.
- `test_gossip_ws_bare_topic_binding`: bare `transactions` on `?chain=B`
  reaches only B's broker.
- `test_mesh_peer_url_chain_param`: peer URL with `?chain=` round-trips into
  the right broker; mismatched chain rejected at config validation.
- Regression: existing `test_websocket.py`, `test_gossip_ws_reconnect.py`,
  `test_gossip_auth.py` unchanged and green (single-chain default path).

## Risks / open questions

- **Consensus-adjacent:** pbft/consensus topics are restricted-auth;
  channel_scope must include chain or a validator key could cross-authorize.
  This is the highest-risk item — needs explicit review.
- Priority queue/drain is per-broker → per-chain CPU isolation is free, but
  total drain tasks grow with chain count (bounded by supported_chains).
- `GOSSIP_BACKENDS` currently only documents redis URLs; mesh/websocket
  per-chain specs need grammar extension (proposal above).
- Bare-topic publishers (`transactions` with no chain suffix) exist in the
  wild (CE-009 context) — demux must not widen their reach; binding rule in
  §3 covers it.
- Per-island ports may still be wanted for network segmentation; demux makes
  them optional, not mandatory to remove.

## Out of scope

- Implementation, nginx changes, unit-file changes, env migration — all
  follow a separate approved implementation row after this design is
  ratified.
