# Troubleshooting

This guide covers common issues and debugging steps for AITBC nodes.

## Blockchain Not Syncing

```bash
# Check service status
systemctl status aitbc-blockchain-node.service
systemctl status aitbc-blockchain-rpc.service

# Check logs
journalctl -u aitbc-blockchain-node -f
journalctl -u aitbc-blockchain-rpc -f

# Verify hub connectivity (public path via nginx; :8202 is internal-only)
curl -s https://hub.example.net/rpc/health
```

## Genesis Block Mismatch

```bash
# Clear database and restart
systemctl stop aitbc-blockchain-node.service
rm -f /var/lib/aitbc/data/ait-localnet/chain.db*
systemctl start aitbc-blockchain-node.service
```

## Agent Messages Not Received

```bash
# Verify agent-coordinator connectivity (agent messaging is :8107, not the
# coordinator-api on :8203)
curl -s http://localhost:8107/health
```

## Service Won't Start

```bash
# Check for syntax errors in config files
systemctl status <service-name>

# Check detailed logs
journalctl -xe

# Verify environment files
cat /etc/aitbc/blockchain.env
cat /etc/aitbc/node.env
```

## Database Lock Issues

```bash
# Stop the service FIRST — deleting WAL/SHM under a live SQLite DB can
# corrupt it (WAL holds committed-but-uncheckpointed transactions)
systemctl stop aitbc-blockchain-node.service

# Check for stale WAL files
ls -la /var/lib/aitbc/data/ait-localnet/

# Remove stale lock files
rm -f /var/lib/aitbc/data/ait-localnet/chain.db-shm
rm -f /var/lib/aitbc/data/ait-localnet/chain.db-wal

# Restart service
systemctl start aitbc-blockchain-node.service
```

## Network Connectivity Issues

```bash
# Test RPC connectivity (public path via nginx; :8202 is internal-only)
curl -v https://hub.example.net/rpc/health

# Test coordinator connectivity (coordinator-api port)
curl -v http://localhost:8203/health   # check-ports: ignore

# Check firewall rules
iptables -L -n
ufw status

# Check DNS resolution
nslookup hub.example.net
```

## See Also

- [Blockchain Setup](../node/blockchain-setup.md)
- Agent Messaging
- Network Requirements
