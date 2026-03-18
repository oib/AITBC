# AITBC Service Naming Convention

## Updated Service Names (2026-02-13)

All AITBC systemd services now follow the `aitbc-` prefix convention for consistency and easier management.

### Site A (aitbc.bubuit.net) - Production Services

| Old Name | New Name | Port | Description |
|----------|----------|------|-------------|
| blockchain-node.service | aitbc-blockchain-node-1.service | 8081 | Blockchain Node 1 |
| blockchain-node-2.service | aitbc-blockchain-node-2.service | 8082 | Blockchain Node 2 |
| blockchain-rpc.service | aitbc-blockchain-rpc-1.service | - | RPC API for Node 1 |
| blockchain-rpc-2.service | aitbc-blockchain-rpc-2.service | - | RPC API for Node 2 |
| coordinator-api.service | aitbc-coordinator-api.service | 8000 | Coordinator API |
| exchange-mock-api.service | aitbc-exchange-mock-api.service | - | Exchange Mock API |

### Site B (ns3 container) - Remote Node

| Old Name | New Name | Port | Description |
|----------|----------|------|-------------|
| blockchain-node.service | aitbc-blockchain-node-3.service | 8082 | Blockchain Node 3 |
| blockchain-rpc.service | aitbc-blockchain-rpc-3.service | - | RPC API for Node 3 |

### Already Compliant Services
These services already had the `aitbc-` prefix:
- aitbc-exchange-api.service (port 3003)
- aitbc-exchange.service (port 3002)
- aitbc-miner-dashboard.service

### Removed Services
- aitbc-blockchain.service (legacy, was on port 9080)

## Management Commands

### Check Service Status
```bash
# Site A (via SSH)
ssh aitbc-cascade "systemctl status aitbc-blockchain-node-1.service"

# Site B (via SSH)
ssh ns3-root "incus exec aitbc -- systemctl status aitbc-blockchain-node-3.service"
```

### Restart Services
```bash
# Site A
ssh aitbc-cascade "sudo systemctl restart aitbc-blockchain-node-1.service"

# Site B
ssh ns3-root "incus exec aitbc -- sudo systemctl restart aitbc-blockchain-node-3.service"
```

### View Logs
```bash
# Site A
ssh aitbc-cascade "journalctl -u aitbc-blockchain-node-1.service -f"

# Site B
ssh ns3-root "incus exec aitbc -- journalctl -u aitbc-blockchain-node-3.service -f"
```

## Service Dependencies

### Blockchain Nodes
- Node 1: `/opt/blockchain-node` → port 8081
- Node 2: `/opt/blockchain-node-2` → port 8082
- Node 3: `/opt/blockchain-node` → port 8082 (Site B)

### RPC Services
- RPC services are companion services to the main nodes
- They provide HTTP API endpoints for blockchain operations

### Coordinator API
- Main API for job submission, miner management, and receipts
- Runs on localhost:8000 inside container
- Proxied via nginx at https://aitbc.bubuit.net/api/

## Benefits of Standardized Naming

1. **Clarity**: Easy to identify AITBC services among system services
2. **Management**: Simpler to filter and manage with wildcards (`systemctl status aitbc-*`)
3. **Documentation**: Consistent naming across all documentation
4. **Automation**: Easier scripting and automation with predictable names
5. **Debugging**: Faster identification of service-related issues
