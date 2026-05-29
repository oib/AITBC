# Blockchain Node Issues

This guide covers blockchain node problems including sync issues, forks, and P2P connectivity.

## Node Won't Sync

**Symptoms:**
- Block height not increasing
- Sync status shows "syncing" indefinitely
- Peers not connecting

**Diagnosis:**
```bash
# Check sync status
curl http://localhost:8080/v1/network

# Check peer connections
curl http://localhost:8080/v1/network/peers

# Check blockchain logs
sudo journalctl -u aitbc-blockchain -n 50
```

**Solutions:**
1. Add bootstrap peers
```bash
# Edit configuration
echo "BOOTSTRAP_PEERS=peer1.example.com:8080,peer2.example.com:8080" >> /etc/aitbc/blockchain.env

# Restart service
sudo systemctl restart aitbc-blockchain
```

2. Check network connectivity
```bash
# Test peer connectivity
telnet peer.example.com 8080

# Check firewall
sudo ufw status
```

3. Reset blockchain state
```bash
# Stop service
sudo systemctl stop aitbc-blockchain

# Backup data
mv /var/lib/aitbc/blockchain /var/lib/aitbc/blockchain.backup

# Start service
sudo systemctl start aitbc-blockchain
```

## Fork Detected

**Symptoms:**
- Multiple blockchain branches
- Consensus failures
- Invalid blocks

**Diagnosis:**
```bash
# Check blockchain height
curl http://localhost:8080/v1/blocks/head

# Check for forks
curl http://localhost:8080/v1/blocks/forks
```

**Solutions:**
1. Choose correct fork
```bash
# Revert to correct height
curl -X POST http://localhost:8080/v1/admin/revert \
  -H "Content-Type: application/json" \
  -d '{"height": 12345}'
```

2. Restart with clean state
```bash
# Stop service
sudo systemctl stop aitbc-blockchain

# Clear blockchain data
rm -rf /var/lib/aitbc/blockchain

# Start service
sudo systemctl start aitbc-blockchain
```

## See Also

- [Network Issues](network-issues.md) - Network connectivity and firewall issues
- [Service Management](service-management.md) - General service troubleshooting
- [Database Issues](database-issues.md) - Database-related blockchain issues
