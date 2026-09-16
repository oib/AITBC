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

1. Add bootstrap peers

```bash
# Edit configuration
echo "BOOTSTRAP_PEERS=peer1.example.com:8080,peer2.example.com:8080" >> /etc/aitbc/blockchain.env  # check-ports: ignore

# Restart service
systemctl restart aitbc-blockchain-node
```

1. Check network connectivity

```bash
# Test peer connectivity
telnet peer.example.com 8080

# Check firewall
ufw status
```

1. Reset blockchain state

```bash
# Stop service
systemctl stop aitbc-blockchain-node

# Backup data
mv /opt/aitbc/data/aitbc-chain.db /opt/aitbc/data/aitbc-chain.db.backup

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

# Compare with the proposer
curl http://hub.aitbc.bubuit.net:8202/rpc/head
```

**Solutions:**

1. Reorg onto the proposer's chain

```bash
# Force-sync is admin-signed (verify_admin_signature), not API-key gated
curl -X POST http://localhost:8202/rpc/force-sync \
  -H "Content-Type: application/json" \
  -d '{"peer_url": "http://hub.aitbc.bubuit.net:8202", "admin_address": "<admin_addr>", "admin_signature": "<sig>"}'
```

1. Last resort — resync from scratch (destroys local chain state)

```bash
systemctl stop aitbc-blockchain-node aitbc-blockchain-rpc
mv /opt/aitbc/data/aitbc-chain.db /opt/aitbc/data/aitbc-chain.db.forked
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc
# the node re-syncs from the proposer via subscription/pull sync
```

## See Also

- [Network Issues](network-issues.md) - Network connectivity and firewall issues
- [Service Management](service-management.md) - General service troubleshooting
- [Database Issues](database-issues.md) - Database-related blockchain issues
