# Blockchain Operational Features

**Last Updated:** 2026-09-16

## Overview

This document describes operational features for managing AITBC blockchain synchronization and data management.

## Auto Sync

### Overview — Auto Sync

Automatic bulk sync is implemented in the blockchain node to automatically detect and resolve block gaps without manual intervention.

### Configuration

Configuration parameters in `/etc/aitbc/blockchain.env`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `auto_sync_enabled` | `true` | Enable/disable automatic bulk sync |
| `auto_sync_threshold` | `10` | Block gap threshold to trigger sync |
| `auto_sync_max_retries` | `3` | Max retry attempts for sync |
| `min_bulk_sync_interval` | `60` | Minimum seconds between sync attempts |

### Enabling Auto Sync

To enable on a node:

1. Add `auto_sync_enabled=true` to `/etc/aitbc/blockchain.env`
2. Restart the blockchain node service:

   ```bash
   systemctl restart aitbc-blockchain-node.service
   ```

### Sync Triggers

Automatic sync triggers when:

- A block arrives via gossip
- Import fails due to gap detection
- Gap exceeds `auto_sync_threshold`
- Time since last sync exceeds `min_bulk_sync_interval`

### Code Location

Implementation is located in:

- `apps/blockchain-node/src/aitbc_chain/config.py` - Configuration
- `apps/blockchain-node/src/aitbc_chain/main.py` - Main loop
- `apps/blockchain-node/src/aitbc_chain/sync.py` - Sync logic

## Force Sync

### Overview — Force Sync

Force synchronization lets an operator make a node reorganize to match a
trusted peer: the node fetches the peer's `GET /rpc/export-chain` output and
imports it through the normal validated import path.

### API Endpoints

#### Trigger Force Sync

```http
POST /rpc/force-sync
X-API-Key: <BLOCKCHAIN_RPC_API_KEY>
Content-Type: application/json

{
  "peer_url": "https://hub.example.net",
  "admin_address": "0x<admin address>",
  "admin_signature": "0x<secp256k1 signature over the request>",
  "issued_at": "<unix epoch, within ±5 min of node time>",
  "nonce": "<unique string, single-use>",
  "target_chain_id": "<this node's own chain id>",
  "target_height": 2000
}
```

The request must carry **both** `X-API-Key` (`verify_rpc_api_key`) **and** an
admin signature (`require_admin_signature`); unsigned, wrongly signed, or
replayed bodies return 403. The signer must be listed in
`bridge_admin_addresses`; `issued_at` must be within ±5 minutes, `nonce`
single-use, and `target_chain_id` must equal the **serving** node's chain id.
Prefer `aitbc network force-sync`, which signs and injects the key. `peer_url`
must be `http`/`https`; loopback, link-local, reserved, multicast and
unspecified addresses are rejected — private LAN addresses (10.x) are
allowed for fleet peers. `target_height` is optional and bounds how much of
the peer chain is accepted.

#### Check Sync Configuration

There is no `/rpc/sync/status` endpoint. The sync-related routes are:

```http
GET /rpc/sync/config
```

which returns the node's sync optimization settings (`sync_parallel_*`,
`sync_delta_*`, `gossip_*`). Observe progress through
`aitbc blockchain sync-status` / `aitbc blockchain height` and
`journalctl -u aitbc-blockchain-node -f`.

### Usage

To manually trigger synchronization:

```bash
curl -X POST http://localhost:8202/rpc/force-sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d '{"peer_url":"https://hub.example.net","admin_address":"0x...","admin_signature":"0x...",
       "issued_at":"<unix epoch>","nonce":"<unique>","target_chain_id":"<chain id>"}'
```

## Export

### Overview — Export

Export blockchain data for backup, migration, or analysis purposes.

### API Endpoints — Export

#### Export Full Chain

```http
GET /rpc/export-chain?chain_id=ait-mainnet
```

There are no `/rpc/export/blocks` or `/rpc/export/transactions` routes —
`export-chain` returns the complete state in one document: `blocks`,
`accounts`, and `transactions` for the chain, plus counts and a timestamp.

**Response:**

```json
{
  "success": true,
  "export_data": {
    "chain_id": "ait-mainnet",
    "export_timestamp": "...",
    "block_count": 1000,
    "account_count": 87,
    "transaction_count": 15234,
    "blocks": [ ... ],
    "accounts": [ ... ],
    "transactions": [ ... ]
  },
  "export_size_bytes": 12345678
}
```

### Usage — Export

Export the full chain to file:

```bash
curl -s -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  "http://localhost:8202/rpc/export-chain?chain_id=ait-mainnet" \
  > chain_export.json
```

## Import

### Overview — Import

Import blockchain data from exported files for node initialization or recovery.

### API Endpoints — Import

There are no `/rpc/import/blocks`, `/rpc/import/transactions`, or
`/rpc/import/chain` routes — the real import surface is:

#### Import a Single Block

```http
POST /rpc/importBlock
X-API-Key: <key>
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "height": 1001,
  "hash": "0x<64-hex>",
  "parent_hash": "0x...",
  "proposer": "0x...",
  "transactions": [ ... ]
}
```

Requires a valid `X-API-Key`. The block goes through the same validated import
path as peer sync (signature, parent linkage, state root, transaction
application); a height or hash that already exists returns `409`.

#### Import Full Chain State

```http
POST /rpc/import-chain
X-API-Key: <BLOCKCHAIN_RPC_API_KEY>
Content-Type: application/json

{
  "admin_address": "0x<admin address>",
  "admin_signature": "0x<signature over the export payload>",
  "issued_at": "<unix epoch, within ±5 min of node time>",
  "nonce": "<unique string, single-use>",
  "target_chain_id": "<this node's own chain id>",
  "chain_id": "ait-mainnet",
  "blocks": [ ... ],
  "accounts": [ ... ],
  "transactions": [ ... ]
}
```

The body is the `export_data` object from `GET /rpc/export-chain` plus
**admin credentials** — `admin_address` and `admin_signature` are verified by
`require_admin_signature` (signer in `bridge_admin_addresses`, fresh
`issued_at`/`nonce`/`target_chain_id`) before anything is written; the route
also requires the `X-API-Key` header (`verify_rpc_api_key`).

### Usage — Import

Import a single block:

```bash
curl -X POST http://localhost:8202/rpc/importBlock \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -H "Content-Type: application/json" \
  -d @block.json
```

Import a full chain export (admin-signed):

```bash
jq '.export_data + {admin_address: "0x...", admin_signature: "0x...",
     issued_at: "<unix epoch>", nonce: "<unique>",
     target_chain_id: "<chain id>"}' \
  chain_export.json | \
curl -X POST http://localhost:8202/rpc/import-chain \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $BLOCKCHAIN_RPC_API_KEY" \
  -d @-
```

## Troubleshooting

### Auto Sync Not Triggering

**Symptoms**: Block gaps not detected or sync not starting.

**Solutions**:

- Verify `auto_sync_enabled=true` in `/etc/aitbc/blockchain.env`
- Check `auto_sync_threshold` is appropriate for your network
- Verify blockchain node service is running
- Check logs: `journalctl -u aitbc-blockchain-node.service -f`

### Force Sync Failing

**Symptoms**: Force sync returns error or times out.

**Solutions**:

- Verify the admin signature (`admin_address` + `admin_signature` + fresh
  `issued_at`/`nonce`/`target_chain_id`) — 403 names which guard tripped
- Verify `peer_url` is reachable and serves `GET /rpc/export-chain` (the node
  pulls the peer's export itself)
- `peer_url` must be http/https; loopback, link-local, reserved, multicast
  and unspecified addresses are rejected with 400 — private LAN addresses
  are allowed
- If `target_height` is set, verify the peer actually has that many blocks
- Check network connectivity
- Review logs for specific error messages: `journalctl -u aitbc-blockchain-rpc -f`

### Export Failing

**Symptoms**: Export returns error or incomplete data.

**Solutions**:

- Verify sufficient disk space
- Check `chain_id` exists (the export covers the whole chain — there is no
  height-range parameter)
- Check database connectivity

### Import Failing

**Symptoms**: Import returns error or data not persisted.

**Solutions**:

- For `import-chain`: verify the admin signature over the payload plus the
  freshness fields (`issued_at`/`nonce`/`target_chain_id`) and the
  `X-API-Key` header — the signature must cover the exact body being posted
- Check `chain_id` matches a supported chain
- Verify the payload has the `export_data` structure (`blocks`, `accounts`,
  `transactions` arrays)
- For `importBlock`: verify the `X-API-Key` header and block hash format
  (`0x` + 64 hex); a `409` means the height/hash already exists
- Check database write permissions
- Verify import lock is not held by another process

## Security Notes

- Auto sync uses same authentication as blockchain RPC
- Force sync requires admin privileges
- Export/Import operations should be performed on trusted nodes only
- Export files may contain sensitive transaction data - secure appropriately
- Import operations can overwrite existing data - use with caution
- Validate export files before importing from untrusted sources

## Performance Considerations

- Auto sync runs in background with minimal impact on node performance
- Force sync may temporarily increase resource usage
- Export operations can be memory-intensive for large ranges
- Import operations may lock database during processing
- Use appropriate batch sizes for large exports/imports
- Schedule exports during low-traffic periods when possible
