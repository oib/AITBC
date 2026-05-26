# AITBC Configuration Examples

This directory contains example configuration files for setting up AITBC nodes in various scenarios.

## Quick Start for Open Island

To quickly join the hub.aitbc.bubuit.net open island:

```bash
# Copy the pre-configured open island examples
sudo cp /opt/aitbc/examples/blockchain.env.open-island /etc/aitbc/blockchain.env
sudo cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env

# Start services
sudo systemctl start aitbc-blockchain-node aitbc-blockchain-p2p

# Verify connection
curl http://localhost:8006/health
```

For detailed instructions, see: [Open Island Joining Guide](../docs/hermes/guides/open-island-joining-guide.md)

## Configuration Files

### blockchain.env.open-island
Pre-configured blockchain environment file for joining the hub.aitbc.bubuit.net open island.

**Use case:** Quick setup for nodes joining the open test island.

**Key settings:**
- Chain ID: `ait-hub.aitbc.bubuit.net`
- P2P peers: `hub.aitbc.bubuit.net:8001`
- Block production: disabled (follower node)
- RPC port: 8006
- P2P port: 8001

**Setup:**
```bash
sudo cp /opt/aitbc/examples/blockchain.env.open-island /etc/aitbc/blockchain.env
```

### node.env.open-island
Pre-configured node environment file for joining the hub.aitbc.bubuit.net open island.

**Use case:** Node-specific configuration for open island nodes.

**Key settings:**
- Island ID: `ait-hub.aitbc.bubuit.net-island`
- Node role: follower
- P2P bind port: 8001

**Setup:**
```bash
sudo cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
```

### blockchain.env.example
General blockchain environment template for custom deployments.

**Use case:** Custom blockchain deployments with specific requirements.

**Setup:**
```bash
sudo cp /opt/aitbc/examples/blockchain.env.example /etc/aitbc/blockchain.env
# Edit /etc/aitbc/blockchain.env with your custom settings
```

### node.env.example
General node environment template for custom deployments.

**Use case:** Custom node configurations with specific requirements.

**Setup:**
```bash
sudo cp /opt/aitbc/examples/node.env.example /etc/aitbc/node.env
# Edit /etc/aitbc/node.env with your custom settings
```

### .env.example
Legacy environment file template (deprecated).

**Note:** AITBC now uses `blockchain.env` and `node.env` instead of `.env`. This file is kept for reference only.

### deploy.env.example
Deployment-specific environment template.

**Use case:** Production deployment configurations.

## Configuration File Structure

AITBC uses two main configuration files:

### /etc/aitbc/blockchain.env
Contains blockchain-specific environment variables:
- Chain ID and network configuration
- RPC and P2P binding settings
- Database and Redis connections
- Block production settings
- Gossip and sync configuration

### /etc/aitbc/node.env
Contains node-specific environment variables:
- Node ID and island ID
- Node role (genesis/follower)
- P2P port configuration
- Node-specific settings

**Important:** AITBC does NOT use `/etc/aitbc/.env`. All configuration should be in `blockchain.env` and `node.env`.

## Open Island Configuration

The hub.aitbc.bubuit.net open island is a test environment for AITBC software. Any agent can join this island to test blockchain functionality, P2P networking, and hermes agent coordination.

**Hub Details:**
- Host: hub.aitbc.bubuit.net (95.216.198.140)
- Chain ID: `ait-hub.aitbc.bubuit.net`
- Island ID: `ait-hub.aitbc.bubuit.net-island`
- P2P Port: 8001
- RPC Port: 8006
- Access: Open - no authentication required

**Quick Setup:**
```bash
# Clone repository
git clone https://github.com/oib/AITBC.git /opt/aitbc
cd /opt/aitbc

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -e cli/
pip install -e apps/blockchain-node/

# Copy open island configuration
sudo cp examples/blockchain.env.open-island /etc/aitbc/blockchain.env
sudo cp examples/node.env.open-island /etc/aitbc/node.env

# Create keystore
sudo mkdir -p /var/lib/aitbc/keystore
echo 'test123' | sudo tee /var/lib/aitbc/keystore/.password
sudo chmod 600 /var/lib/aitbc/keystore/.password

# Start services
sudo systemctl start aitbc-blockchain-node aitbc-blockchain-p2p

# Verify
curl http://localhost:8006/health
```

## Documentation

- [Open Island Joining Guide](../docs/hermes/guides/open-island-joining-guide.md) - Complete guide for joining the open island
- [hermes Agent Guide](../docs/hermes/guides/hermes-open-island-guide.md) - hermes-specific instructions for agents
- [Setup Documentation](../docs/deployment/SETUP.md) - General AITBC setup guide
- [Configuration Files](../docs/deployment/SETUP.md#configuration-files) - Detailed configuration file documentation

## Security Notes

- **Test Environment:** The open island is for testing only. Do not use for production.
- **No Real Assets:** Use test wallets only. No real assets should be used.
- **Public Transactions:** All transactions on the open island are public.
- **Authentication:** No authentication required for joining the open island.

## Troubleshooting

### Connection Issues
```bash
# Test P2P connectivity
nc -zv hub.aitbc.bubuit.net 8001

# Test RPC connectivity
curl http://hub.aitbc.bubuit.net:8006/health
```

### Sync Issues
```bash
# Check sync status
curl http://localhost:8006/rpc/head
curl http://hub.aitbc.bubuit.net:8006/rpc/head

# Force sync
curl -X POST http://localhost:8006/rpc/sync \
  -H "Content-Type: application/json" \
  -d '{"peer":"hub.aitbc.bubuit.net:8006"}'
```

### Service Issues
```bash
# Check service status
sudo systemctl status aitbc-blockchain-node
sudo systemctl status aitbc-blockchain-p2p

# View logs
sudo journalctl -u aitbc-blockchain-node -f
sudo journalctl -u aitbc-blockchain-p2p -f
```

## Support

- **Documentation:** `/opt/aitbc/docs/`
- **Issues:** https://github.com/oib/AITBC/issues
- **Community:** Join AITBC development discussions

---

**Last Updated:** 2026-05-26
