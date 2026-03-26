# Networking Configuration
Configure P2P networking for your blockchain node.

## Network Settings

### Firewall Configuration

```bash
# Allow P2P port
sudo ufw allow 7070/tcp

# Allow RPC port
sudo ufw allow 8080/tcp

# Allow from specific IPs
sudo ufw allow from 10.0.0.0/8 to any port 8080
```

### Port Forwarding

If behind a NAT, configure port forwarding:
- External port 7070 → Internal IP:7070
- External port 8080 → Internal IP:8080

## Bootstrap Nodes

### Default Bootstrap Nodes

```yaml
p2p:
  bootstrap_nodes:
    - /dns4/node-1.aitbc.com/tcp/7070/p2p/12D3KooW...
    - /dns4/node-2.aitbc.com/tcp/7070/p2p/12D3KooW...
    - /dns4/node-3.aitbc.com/tcp/7070/p2p/12D3KooW...
```

### Adding Custom Bootstrap Nodes

```bash
aitbc-chain p2p add-bootstrap /dns4/my-node.example.com/tcp/7070/p2p/...
```

## Peer Management

### Connection Limits

```yaml
p2p:
  max_peers: 50
  min_peers: 5
  outbound_peers: 10
  inbound_peers: 40
```

### Peer Scoring

Nodes are scored based on:
- Latency
- Availability
- Protocol compliance
- Block propagation speed

## NAT Traversal

### Supported Methods

| Method | Description |
|--------|-------------|
| AutoNAT | Automatic NAT detection |
| Hole Punching | UDP hole punching |
| Relay | TURN relay fallback |

### Configuration

```yaml
p2p:
  nat:
    enabled: true
    method: auto  # auto, hole_punching, relay
    external_ip: 203.0.113.1
```

## Troubleshooting

### Check Connectivity

```bash
aitbc-chain p2p check-connectivity
```

### List Active Connections

```bash
aitbc-chain p2p connections
```

### Debug Mode

```bash
aitbc-chain start --log-level debug
```

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
