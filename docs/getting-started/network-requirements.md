# Network Requirements

This guide covers the network configuration requirements for AITBC nodes.

## Firewall Configuration

Ensure your firewall allows the following ports:

### Outbound Ports
- **Port 8006** to hub.aitbc.bubuit.net (blockchain RPC)
- **Port 8011** to hub.aitbc.bubuit.net (Hermes coordinator)

### Inbound Ports
- **Port 8006** (your blockchain RPC)
- **Port 7070** (P2P)

## UFW Configuration Example

```bash
# Allow outbound to hub
ufw allow out to hub.aitbc.bubuit.net port 8006
ufw allow out to hub.aitbc.bubuit.net port 8011

# Allow inbound RPC
ufw allow 8006/tcp

# Allow inbound P2P
ufw allow 7070/tcp

# Enable firewall
ufw enable
```

## iptables Configuration Example

```bash
# Allow outbound to hub
iptables -A OUTPUT -d hub.aitbc.bubuit.net -p tcp --dport 8006 -j ACCEPT
iptables -A OUTPUT -d hub.aitbc.bubuit.net -p tcp --dport 8011 -j ACCEPT

# Allow inbound RPC
iptables -A INPUT -p tcp --dport 8006 -j ACCEPT

# Allow inbound P2P
iptables -A INPUT -p tcp --dport 7070 -j ACCEPT
```

## DNS Resolution

Ensure your system can resolve hub.aitbc.bubuit.net:

```bash
# Test DNS resolution
nslookup hub.aitbc.bubuit.net
ping hub.aitbc.bubuit.net
```

## Network Latency

For optimal performance, ensure:
- Latency to hub < 100ms
- Stable connection with minimal packet loss
- Sufficient bandwidth for block synchronization

## See Also

- [Blockchain Setup](blockchain-setup.md)
- [Troubleshooting](troubleshooting.md)
