# Node Operations
Day-to-day operations for blockchain nodes.

## Starting the Node

```bash
# Start in foreground (for testing)
aitbc-chain start

# Start as daemon
aitbc-chain start --daemon

# Start with custom config
aitbc-chain start --config /path/to/config.yaml
```

## Stopping the Node

```bash
# Graceful shutdown
aitbc-chain stop

# Force stop
aitbc-chain stop --force
```

## Node Status

```bash
aitbc-chain status
```

Shows:
- Block height
- Peers connected
- Mempool size
- Last block time

## Checking Sync Status

```bash
aitbc-chain sync-status
```

Shows:
- Current height
- Target height
- Sync progress percentage
- Estimated time to sync

## Managing Peers

### List Peers

```bash
aitbc-chain peers list
```

### Add Peer

```bash
aitbc-chain peers add /dns4/new-node.example.com/tcp/7070/p2p/...
```

### Remove Peer

```bash
aitbc-chain peers remove <PEER_ID>
```

## Backup & Restore

### Backup Data

```bash
aitbc-chain backup --output /backup/chain-backup.tar.gz
```

### Restore Data

```bash
aitbc-chain restore --input /backup/chain-backup.tar.gz
```

## Log Management

```bash
# View logs
aitbc-chain logs --tail 100

# Filter by level
aitbc-chain logs --level error

# Export logs
aitbc-chain logs --export /var/log/aitbc-chain.log
```

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Consensus](./4_consensus.md) — Consensus mechanism
