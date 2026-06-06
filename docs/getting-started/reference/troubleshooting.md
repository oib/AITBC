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

# Verify hub connectivity
curl -s http://hub.aitbc.bubuit.net:8202/health
```

## Genesis Block Mismatch

```bash
# Clear database and restart
systemctl stop aitbc-blockchain-node.service
rm -f /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db*
systemctl start aitbc-blockchain-node.service
```

## Hermes Messages Not Received

```bash
# Check agent daemon status
systemctl status aitbc-agent-daemon

# Check logs
journalctl -u aitbc-agent-daemon -f

# Verify coordinator connectivity
curl -s http://localhost:8203/health
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
# Check for stale WAL files
ls -la /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/

# Remove stale lock files
rm -f /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db-shm
rm -f /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db-wal

# Restart service
systemctl restart aitbc-blockchain-node.service
```

## Network Connectivity Issues

```bash
# Test RPC connectivity
curl -v http://hub.aitbc.bubuit.net:8202/health

# Test coordinator connectivity
curl -v http://localhost:8203/health

# Check firewall rules
iptables -L -n
ufw status

# Check DNS resolution
nslookup hub.aitbc.bubuit.net
```

## See Also

- [Blockchain Setup](blockchain-setup.md)
- [Hermes Messaging](hermes-messaging.md)
- [Network Requirements](network-requirements.md)
