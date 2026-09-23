# Blockchain Node Issues

This guide covers blockchain node problems including sync issues, forks, and P2P connectivity.

## Node Won't Sync

**Symptoms:**

- Block height not increasing
- Sync status shows "syncing" indefinitely
- Peers not connecting

**Diagnosis:**

```bash
# Check node/sync status
curl http://localhost:8202/rpc/status

# Check registered push-sync subscribers (on the proposer)
curl http://localhost:8202/rpc/subscribers

# Check blockchain logs
journalctl -u aitbc-blockchain-node -n 50
```

**Solutions:**

1. Check the subscription path — followers sync via lease-based subscription, not bootstrap peers (there is no `BOOTSTRAP_PEERS` setting)

```bash
# Verify the hub is configured as the default peer (base URL, no /rpc suffix)
grep default_peer_rpc_url /etc/aitbc/node.env

# Confirm your peer key is enrolled on the hub (a 403 means it is not in
# the hub's BLOCKCHAIN_RPC_API_KEY_PEERS)
journalctl -u aitbc-blockchain-node -n 200 | grep -i "subscribe\|lease\|403"

# Restart service
systemctl restart aitbc-blockchain-node
```

1. Check network connectivity

```bash
# Test reachability of the hub RPC (public nginx endpoint)
curl -s https://hub.example.net/rpc/head

# Check firewall
ufw status
```

1. Reset blockchain state — the DB is **chain-scoped**: `$AITBC_DATA_DIR/data/<chain_id>/chain.db`

```bash
# Stop service
systemctl stop aitbc-blockchain-node

# Backup data (adjust CHAIN_ID to yours)
mv /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
   /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db.backup

# Start service
systemctl start aitbc-blockchain-node
```

## Fork Detected

**Symptoms:**

- Multiple blockchain branches
- Consensus failures
- Invalid blocks

**Diagnosis:**

```bash
# Check blockchain height (the /v1 mount aliases /rpc)
curl http://localhost:8202/rpc/head

# Compare with the proposer (public endpoint; raw :8202 is internal-only)
curl https://hub.example.net/rpc/head
```

**Solutions:**

1. Reorg onto the proposer's chain

```bash
# Force-sync is admin-signed (verify_admin_signature), not API-key gated
curl -X POST http://localhost:8202/rpc/force-sync \
  -H "Content-Type: application/json" \
  -d '{"peer_url": "https://hub.example.net", "admin_address": "<admin_addr>", "admin_signature": "<sig>"}'
```

1. Last resort — resync from scratch (destroys local chain state)

```bash
systemctl stop aitbc-blockchain-node aitbc-blockchain-rpc
# DB is chain-scoped: $AITBC_DATA_DIR/data/<chain_id>/chain.db
mv /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db \
   /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db.forked
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc
# the node re-syncs from the proposer via subscription/pull sync
```

## See Also

- [Network Issues](network-issues.md) - Network connectivity and firewall issues
- [Service Management](service-management.md) - General service troubleshooting
- [Database Issues](database-issues.md) - Database-related blockchain issues
