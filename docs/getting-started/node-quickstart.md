# Node Quick Start: Join the network

This guide shows how to set up a follower node to join the AITBC blockchain network on the open island at `hub.aitbc.bubuit.net`.

## 1. Download Chain Configuration

Download the public chain configuration and genesis from the hub:

```bash
mkdir -p /etc/aitbc
curl https://hub.aitbc.bubuit.net/agent/blockchain.env \
  -o /etc/aitbc/blockchain.env
curl https://hub.aitbc.bubuit.net/agent/genesis.json \
  -o /etc/aitbc/genesis.json
```

A node that follows the chain needs **only** the two files above. `blockchain-secrets.env` is not required and must not be downloaded from any public URL. If you also run the wallet, agent-coordinator, or event-bridge, get that file from the hub operator over an authenticated channel.

## 2. Create Your Node Configuration

Create a local configuration file for your node with a unique identity:

```bash
cat > /etc/aitbc/node.env << EOF
NODE_ID=yournode.example.com
P2P_NODE_ID=yournode.example.com
BLOCKCHAIN_MODE=follower
MARKET_ROLE=customer
HARDWARE_PROFILE=nogpu
EOF
```

Set `default_peer_rpc_url` to the hub's **base URL** (no `/rpc` suffix). The setup script can do this for you:

```bash
cd /opt/aitbc
./scripts/deployment/setup.sh --open-island https://hub.aitbc.bubuit.net --node-id yournode.example.com
```

## 3. Start the Node

Start the blockchain node service:

```bash
systemctl start aitbc-blockchain-node
```

## 4. Verify Connection

Check that your node is syncing with the network:

```bash
systemctl status aitbc-blockchain-node
journalctl -u aitbc-blockchain-node -f | grep -iE 'subscribed|lease|websocket|Imported block'

# Compare heights after a minute or two
watch -n 5 'echo local=$(curl -s http://localhost:8202/rpc/head | jq .height) hub=$(curl -s https://hub.aitbc.bubuit.net/rpc/head | jq .height)'
```

## Additional Resources

- [Open Island Joining Guide](https://github.com/oib/AITBC/blob/main/docs/agent/guides/open-island-joining-guide.md)
- [Full Setup Guide](https://github.com/oib/AITBC/blob/main/docs/getting-started/SETUP.md)
- [README](https://github.com/oib/AITBC/blob/main/README.md)
- [Network Discovery](/rpc/network-info)
