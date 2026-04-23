# Blockchain Operational Features

## Overview

This document describes operational features for managing AITBC blockchain synchronization and data management.

## Auto Sync

### Overview

Automatic bulk sync is implemented in the blockchain node to automatically detect and resolve block gaps without manual intervention.

### Configuration

Configuration parameters in `/etc/aitbc/.env`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `auto_sync_enabled` | `true` | Enable/disable automatic bulk sync |
| `auto_sync_threshold` | `10` | Block gap threshold to trigger sync |
| `auto_sync_max_retries` | `3` | Max retry attempts for sync |
| `min_bulk_sync_interval` | `60` | Minimum seconds between sync attempts |

### Enabling Auto Sync

To enable on a node:

1. Add `auto_sync_enabled=true` to `/etc/aitbc/.env`
2. Restart the blockchain node service:
   ```bash
   sudo systemctl restart aitbc-blockchain-node.service
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

### Overview

Force synchronization allows manual triggering of blockchain data synchronization between nodes.

### API Endpoints

#### Trigger Force Sync

```http
POST /rpc/force_sync
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "from_height": 1000,
  "to_height": 2000
}
```

#### Check Sync Status

```http
GET /rpc/sync/status
```

### Usage

To manually trigger synchronization:

```bash
curl -X POST http://localhost:8006/rpc/force_sync \
  -H "Content-Type: application/json" \
  -d '{"chain_id":"ait-mainnet","from_height":0,"to_height":1000}'
```

## Export

### Overview

Export blockchain data for backup, migration, or analysis purposes.

### API Endpoints

#### Export Blocks

```http
POST /rpc/export/blocks
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "from_height": 0,
  "to_height": 1000
}
```

#### Export Transactions

```http
POST /rpc/export/transactions
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "from_height": 0,
  "to_height": 1000
}
```

### Usage

Export blocks to file:

```bash
curl -X POST http://localhost:8006/rpc/export/blocks \
  -H "Content-Type: application/json" \
  -d '{"chain_id":"ait-mainnet","from_height":0,"to_height":1000}' \
  > blocks_export.json
```

## Import

### Overview

Import blockchain data from exported files for node initialization or recovery.

### API Endpoints

#### Import Blocks

```http
POST /rpc/import/blocks
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "file": "/path/to/blocks_export.json"
}
```

#### Import Transactions

```http
POST /rpc/import/transactions
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "file": "/path/to/transactions_export.json"
}
```

### Usage

Import blocks from file:

```bash
curl -X POST http://localhost:8006/rpc/import/blocks \
  -H "Content-Type: application/json" \
  -d '{"chain_id":"ait-mainnet","file":"/path/to/blocks_export.json"}'
```

### Import Chain

```http
POST /rpc/import/chain
Content-Type: application/json

{
  "chain_id": "ait-mainnet",
  "file": "/path/to/chain_export.json"
}
```

## Troubleshooting

### Auto Sync Not Triggering

**Symptoms**: Block gaps not detected or sync not starting.

**Solutions**:
- Verify `auto_sync_enabled=true` in `/etc/aitbc/.env`
- Check `auto_sync_threshold` is appropriate for your network
- Verify blockchain node service is running
- Check logs: `journalctl -u aitbc-blockchain-node.service -f`

### Force Sync Failing

**Symptoms**: Force sync returns error or times out.

**Solutions**:
- Verify target node is accessible
- Check chain_id matches target node
- Verify height range is valid
- Check network connectivity
- Review logs for specific error messages

### Export Failing

**Symptoms**: Export returns error or incomplete data.

**Solutions**:
- Verify sufficient disk space
- Check chain_id exists
- Verify height range is valid
- Check database connectivity

### Import Failing

**Symptoms**: Import returns error or data not persisted.

**Solutions**:
- Verify export file exists and is valid JSON
- Check chain_id matches
- Verify file format matches expected structure
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
