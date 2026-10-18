# AITBC Blockchain Node Deployment Summary

> **⚠️ Historical deployment record — do not use as a current reference.**
> This page documents a retired two-node test deployment
> (`/opt/blockchain-node{,-2}`, `blockchain-node*.service` units, RPC on
> 8081/8202, independent 2s chains with a memory gossip backend). The current
> deployment is a hub + follower fleet running from `/opt/aitbc` with systemd
> units `aitbc-blockchain-node` / `aitbc-blockchain-rpc` /
> `aitbc-blockchain-p2p` (hub only), env configuration under `/etc/aitbc/`, and
> lease-based subscription sync over the hub's RPC on 443/8202.
>
> **Current docs:** [blockchain/README.md](../blockchain/README.md) —
> [configuration](../blockchain/2_configuration.md),
> [operations](../blockchain/3_operations.md),
> [networking](../blockchain/6_networking.md),
> [getting-started/node/blockchain-setup.md](../getting-started/node/blockchain-setup.md).

## Overview

Successfully deployed two independent AITBC blockchain nodes on the same server for testing and development.

## Node Configuration

### Node 1

- **Location**: `/opt/blockchain-node`
- **P2P Port**: 7070
- **RPC Port**: 8202
- **Database**: `/opt/blockchain-node/data/chain.db`
- **Status**: ✅ Operational
- **Chain Height**: 717,593+ (actively producing blocks)

### Node 2

- **Location**: `/opt/blockchain-node-2`
- **P2P Port**: 7071
- **RPC Port**: 8081
- **Database**: `/opt/blockchain-node-2/data/chain2.db`
- **Status**: ✅ Operational
- **Chain Height**: 174+ (actively producing blocks)

## Services

### Systemd Services

```bash
# Node 1 (2)
systemctl status blockchain-node    # Consensus node
systemctl status blockchain-rpc     # RPC API

# Node 2 (2)
systemctl status blockchain-node-2  # Consensus node
systemctl status blockchain-rpc-2   # RPC API
```

### API Endpoints

- Node 1 RPC: `http://127.0.0.1:8202/docs`
- Node 2 RPC: `http://127.0.0.1:8081/docs` <!-- check-ports: ignore -->

## Testing

### Test Scripts

1. **Basic Test**: `/opt/test_blockchain_simple.py`
   - Verifies node responsiveness
   - Checks chain head

2. **Comprehensive Test**: `/opt/test_blockchain_nodes.py`
   - Full test suite with multiple scenarios
   - Currently shows nodes operating independently

### Running Tests

```bash
cd /opt/blockchain-node
source .venv/bin/activate
cd ..
python test_blockchain_final.py
```

## Status at the Time of the Deployment (historical)

### ✅ Working then

- Both nodes were running and producing blocks
- RPC APIs were responsive
- Transaction submission worked
- Block production active (2s block time)

### ⚠️ Limitations then

- Nodes were running independently (not connected)
- Used memory gossip backend (no cross-node communication)
- Different chain heights (expected for independent nodes)

This deployment has since been replaced — see the banner at the top for the
current fleet documentation.

## Production Deployment Guidelines

To connect nodes in a production network:

### 1. Network Configuration

- Deploy nodes on separate servers
- Configure proper firewall rules
- Ensure P2P ports are accessible

### 2. Gossip Backend

- Use Redis for distributed gossip:

  ```env
  GOSSIP_BACKEND=memory
  GOSSIP_BROADCAST_URL=redis://redis-server:6379/0
  ```

### 3. Peer Discovery

- Configure peer list in each node
- Use DNS seeds or static peer configuration
- Implement proper peer authentication

### 4. Security

- Use TLS for P2P communication
- Implement node authentication
- Configure proper access controls

## Troubleshooting

### Common Issues

1. **Port Conflicts**: Ensure ports 7070/7071 and 8081/8202 are available
2. **Permission Issues**: Check file permissions in `/opt/blockchain-node*`
3. **Database Issues**: Remove/rename database to reset chain

### Logs

```bash
# Node logs
journalctl -u blockchain-node -f
journalctl -u blockchain-node-2 -f

# RPC logs
journalctl -u blockchain-rpc -f
journalctl -u blockchain-rpc-2 -f
```

## Next Steps

1. **Multi-Server Deployment**: Deploy nodes on different servers
2. **Redis Setup**: Configure Redis for shared gossip
3. **Network Testing**: Test cross-node communication
4. **Load Testing**: Test network under load
5. **Monitoring**: Set up proper monitoring and alerting

## Files Created/Modified

### Deployment Scripts

- `/opt/aitbc/scripts/deployment/deploy-first-node.sh`
- `/opt/aitbc/scripts/deployment/deploy-second-node.sh`
- `/opt/aitbc/scripts/deployment/setup-gossip-relay.sh`

### Test Scripts — Files Created/Modified

- `/opt/aitbc/tests/test_blockchain_nodes.py`
- `/opt/aitbc/tests/test_blockchain_simple.py`
- `/opt/aitbc/tests/test_blockchain_final.py`

### Configuration Files

- `/opt/blockchain-node/.env`
- `/opt/blockchain-node-2/.env`
- `/etc/systemd/system/blockchain-node*.service`
- `/etc/systemd/system/blockchain-rpc*.service`

## Summary

✅ Successfully deployed two independent blockchain nodes
✅ Both nodes are fully operational and producing blocks
✅ RPC APIs are functional for testing
✅ Test suite created and validated
⚠️ Nodes not connected (expected for current configuration)

The deployment provides a solid foundation for:

- Development and testing
- Multi-node network simulation
- Production deployment preparation
