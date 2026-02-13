# AITBC Blockchain Node Deployment Summary

## Overview
Successfully deployed two independent AITBC blockchain nodes on the same server for testing and development.

## Node Configuration

### Node 1
- **Location**: `/opt/blockchain-node`
- **P2P Port**: 7070
- **RPC Port**: 8082
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
# Node 1
sudo systemctl status blockchain-node    # Consensus node
sudo systemctl status blockchain-rpc     # RPC API

# Node 2
sudo systemctl status blockchain-node-2  # Consensus node
sudo systemctl status blockchain-rpc-2   # RPC API
```

### API Endpoints
- Node 1 RPC: `http://127.0.0.1:8082/docs`
- Node 2 RPC: `http://127.0.0.1:8081/docs`

## Testing

### Test Scripts
1. **Basic Test**: `/opt/test_blockchain_simple.py`
   - Verifies node responsiveness
   - Tests faucet functionality
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

## Current Status

### ✅ Working
- Both nodes are running and producing blocks
- RPC APIs are responsive
- Faucet (minting) is functional
- Transaction submission works
- Block production active (2s block time)

### ⚠️ Limitations
- Nodes are running independently (not connected)
- Using memory gossip backend (no cross-node communication)
- Different chain heights (expected for independent nodes)

## Production Deployment Guidelines

To connect nodes in a production network:

### 1. Network Configuration
- Deploy nodes on separate servers
- Configure proper firewall rules
- Ensure P2P ports are accessible

### 2. Gossip Backend
- Use Redis for distributed gossip:
  ```env
  GOSSIP_BACKEND=redis
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
1. **Port Conflicts**: Ensure ports 7070/7071 and 8081/8082 are available
2. **Permission Issues**: Check file permissions in `/opt/blockchain-node*`
3. **Database Issues**: Remove/rename database to reset chain

### Logs
```bash
# Node logs
sudo journalctl -u blockchain-node -f
sudo journalctl -u blockchain-node-2 -f

# RPC logs
sudo journalctl -u blockchain-rpc -f
sudo journalctl -u blockchain-rpc-2 -f
```

## Next Steps

1. **Multi-Server Deployment**: Deploy nodes on different servers
2. **Redis Setup**: Configure Redis for shared gossip
3. **Network Testing**: Test cross-node communication
4. **Load Testing**: Test network under load
5. **Monitoring**: Set up proper monitoring and alerting

## Files Created/Modified

### Deployment Scripts
- `/home/oib/windsurf/aitbc/scripts/deploy/deploy-first-node.sh`
- `/home/oib/windsurf/aitbc/scripts/deploy/deploy-second-node.sh`
- `/home/oib/windsurf/aitbc/scripts/deploy/setup-gossip-relay.sh`

### Test Scripts
- `/home/oib/windsurf/aitbc/tests/test_blockchain_nodes.py`
- `/home/oib/windsurf/aitbc/tests/test_blockchain_simple.py`
- `/home/oib/windsurf/aitbc/tests/test_blockchain_final.py`

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
