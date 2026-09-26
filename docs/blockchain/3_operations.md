# Node Operations

**Last Updated:** 2026-09-16

Day-to-day operations for blockchain nodes.

Node lifecycle is managed by **systemd**, not the CLI. The `aitbc blockchain`
command group queries the node's RPC API and manages chains — it does not
start or stop the node itself.

## Services

Three systemd units run the blockchain stack:

| Unit | Runs on | Purpose |
|------|---------|---------|
| `aitbc-blockchain-node.service` | all nodes | Consensus, block production, sync (SyncManager), mempool |
| `aitbc-blockchain-rpc.service` | all nodes | RPC API on `rpc_bind_port` (8202) — uvicorn serving `aitbc_chain.app` |
| `aitbc-blockchain-p2p.service` | **hub only** | Internal gossip relay on port 7070 — followers do not run or expose it |

```bash
# Start / stop / restart
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc
systemctl stop aitbc-blockchain-node aitbc-blockchain-rpc
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc

# Status and enablement
systemctl status aitbc-blockchain-node aitbc-blockchain-rpc
systemctl enable aitbc-blockchain-node aitbc-blockchain-rpc

# Hub additionally runs the gossip relay
systemctl status aitbc-blockchain-p2p
```

> `aitbc blockchain start` / `stop` do **not** control these services — they
> start and stop a *secondary chain instance* on a running node (see below).

## Logs

All three units log to the journal:

```bash
journalctl -u aitbc-blockchain-node -f
journalctl -u aitbc-blockchain-rpc -f
journalctl -u aitbc-blockchain-p2p -f          # hub only

# Filter by time or priority
journalctl -u aitbc-blockchain-node --since "1 hour ago" -p err
```

## `aitbc blockchain` Commands

The `aitbc` CLI (wrapper at `/usr/local/bin/aitbc`) talks to the node over its
RPC API — pass `--node-url http://<host>:8202` to target a remote node.

### Status and Inspection

```bash
# Chain status (all chains, or one with --chain-id)
aitbc blockchain status
aitbc blockchain status --chain-id ait-localnet --detailed

# Detailed chain info and metrics
aitbc blockchain info --chain-id ait-localnet --detailed --metrics

# Current height and a specific block
aitbc blockchain height
aitbc blockchain block 1000

# List chains on the node
aitbc blockchain list

# Per-chain sync status (head height, hash, sync source)
aitbc blockchain sync-status
aitbc blockchain sync-status --all-chains --node-url http://node2:8202
```

### Chain Instances

`start`/`stop` operate on **secondary chain instances** hosted by a running
node (`POST /rpc/chains/start|stop`), not on the node service:

```bash
aitbc blockchain start --chain-id my-micro-chain --type micro
aitbc blockchain stop --chain-id my-micro-chain
aitbc blockchain instances            # list chain instances
```

### Consensus Inspection

```bash
aitbc blockchain consensus status --chain-id ait-localnet
aitbc blockchain consensus validators --chain-id ait-localnet
aitbc blockchain consensus slashing-history --chain-id ait-localnet
```

### Chain Lifecycle (operator)

```bash
aitbc blockchain create --config-file chain.json
aitbc blockchain delete --chain-id <id> --confirm
aitbc blockchain add --chain-id <id> --node-id <node>
aitbc blockchain remove --chain-id <id> --node-id <node> --migrate
aitbc blockchain migrate --chain-id <id> --from-node <a> --to-node <b> --verify
```

### Monitoring Snapshot

```bash
aitbc blockchain monitor --chain-id ait-localnet
aitbc blockchain monitor --chain-id ait-localnet --realtime --interval 10
```

## How Sync Actually Works

Followers stay in sync without any inbound ports:

1. **Subscription (real-time):** the follower's `SubscriptionClient` calls
   `POST {default_peer_rpc_url}/rpc/subscribe` with the node's
   `BLOCKCHAIN_RPC_API_KEY` (the key must be in the hub's
   `BLOCKCHAIN_RPC_API_KEY_PEERS`), then holds
   `WS {hub}/rpc/subscribe/ws` open for pushed blocks. `POST /rpc/heartbeat`
   extends the lease.
2. **Bulk catch-up (automatic):** when a gap larger than
   `auto_sync_threshold` (default 10) is detected, the node pulls missing
   blocks over the peer's RPC (`/rpc/head` for the target,
   `/rpc/blocks-range` for batches).
3. **Force sync (operator, last resort):** `POST /rpc/force-sync` on the local
   node with an admin-signed body `{peer_url, admin_address, admin_signature}`
   pulls the peer's full export and reorgs to it. See
   [operational-features.md](./operational-features.md).

Check sync state with `aitbc blockchain sync-status`, `aitbc blockchain
height`, and `journalctl -u aitbc-blockchain-node -f` — there is no
`peers`/`sync --watch`/`diagnose` subcommand.

## Backup & Restore

```bash
# Back up a chain to a directory (compressed, verified)
aitbc blockchain backup --chain-id ait-localnet --path /backup --compress --verify

# Restore a chain from a backup file
aitbc blockchain restore --backup-file /backup/<file>.tar.gz --verify
```

Manual alternatives that go through the RPC API:

- `GET /rpc/export-chain?chain_id=<id>` — full JSON export
- `POST /rpc/import-chain` — admin-signed import
- `POST /rpc/importBlock` — single-block import (`X-API-Key` gated)

## Common Recipes

### Restart after a config change

```bash
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
journalctl -u aitbc-blockchain-node -f   # watch it come up
```

### Check the node is producing / receiving blocks

```bash
aitbc blockchain height                 # local height
curl -s http://localhost:8202/rpc/head  # head hash + tx_count
aitbc blockchain sync-status            # compare against the hub
```

### Verify the subscription lease (follower)

```bash
# On the hub: is this follower registered?
curl -s http://localhost:8202/rpc/subscribers

# On the follower: is the subscribe loop running?
journalctl -u aitbc-blockchain-node -f | grep -i subscr
```

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Configuration](./2_configuration.md) — Configure your node
- [Consensus](./4_consensus.md) — Consensus mechanism
- [Troubleshooting](./8_troubleshooting.md) — Common issues
