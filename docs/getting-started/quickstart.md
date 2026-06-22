# Quick Start: Join the AITBC Network

This guide shows how to set up a follower node to join the AITBC blockchain network.

## 1. Download Chain Configuration

Download the public chain configuration and cluster secrets from the hub:

```bash
curl https://hub.aitbc.bubuit.net/agent/blockchain.env \
  -o /etc/aitbc/blockchain.env
curl https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env \
  -o /etc/aitbc/blockchain-secrets.env
```

## 2. Create Your Node Configuration

Create a local configuration file for your node:

```bash
cat > /etc/aitbc/node.env << EOF
NODE_ID=yournode.example.com
NODE_ROLE=follower
BLOCKCHAIN_MODE=follower
MARKET_ROLE=customer    # or: shop, provider
HARDWARE_PROFILE=nogpu  # or: gpu
EOF
```

### Configuration Options:

- **NODE_ID**: Your node's unique identifier (e.g., your domain name)
- **NODE_ROLE**: Set to `follower` for follower nodes
- **BLOCKCHAIN_MODE**: Set to `follower` to sync with the hub
- **MARKET_ROLE**:
  - `customer` - Consume GPU resources
  - `shop` - Provide marketplace services
  - `provider` - Offer GPU compute capacity
- **HARDWARE_PROFILE**:
  - `nogpu` - Node without GPU resources
  - `gpu` - Node with GPU resources

## 3. Start the Node

Start the blockchain node service:

```bash
systemctl start aitbc-blockchain-node
```

## 4. Verify Connection

Check that your node is syncing with the network:

```bash
systemctl status aitbc-blockchain-node
journalctl -u aitbc-blockchain-node -f
```

## Additional Resources

- [Full Setup Guide](https://github.com/oib/AITBC/blob/main/docs/getting-started/SETUP.md)
- [README](https://github.com/oib/AITBC/blob/main/README.md)
- [Network Discovery](/agent/openapi.json)
