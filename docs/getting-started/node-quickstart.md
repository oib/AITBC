# Node Quick Start: Join the network

This guide shows how to set up a follower node to join the AITBC blockchain network on the open island at `hub.example.net`.

## 1. Download Chain Configuration

Download the sanitized chain configuration and genesis from the hub, and issue your node a peer key:

```bash
mkdir -p /etc/aitbc
curl -fsS https://hub.example.net/agent/bootstrap.env \
  -o /etc/aitbc/blockchain.env
curl -fsS https://hub.example.net/agent/genesis.json \
  -o /etc/aitbc/genesis.json

# Issue a peer key bound to your node_id (choose a unique one; shown once):
curl -fsS -X POST https://hub.example.net/rpc/join \
  -H 'Content-Type: application/json' -d '{"node_id":"yournode.example.com"}'
# → add the returned value: echo 'BLOCKCHAIN_RPC_API_KEY=<peer_key>' >> /etc/aitbc/node.env
```

A node that follows the chain needs **only** the two files plus the peer key above. `blockchain-secrets.env` is not required for following and must not be downloaded from any public URL. If you also run the wallet, agent-coordinator, or event-bridge, get that file from the hub operator over an authenticated channel.

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
./scripts/deployment/setup.sh --open-island https://hub.example.net --node-id yournode.example.com
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
watch -n 5 'echo local=$(curl -s http://localhost:8202/rpc/head | jq .height) hub=$(curl -s https://hub.example.net/rpc/head | jq .height)'
```

## 5. Claim Your Welcome Grant

Every new node gets a one-time **3 AIT** grant (≈ 3 compute-hours) — enough to try market jobs and transactions:

```bash
aitbc wallet create --name my-wallet   # if you don't have one yet
aitbc coin-requests request --wallet my-wallet
```

The request authenticates with the `FOLLOWER_API_KEY` already in your `bootstrap.env`; the first grant is auto-approved and paid immediately. See [Get Free AIT](free-ait.md) for details.

## Additional Resources

- [Open Island Joining Guide](https://github.com/oib/AITBC/blob/main/docs/agent/guides/open-island-joining-guide.md)
- [Full Setup Guide](https://github.com/oib/AITBC/blob/main/docs/getting-started/SETUP.md)
- [README](https://github.com/oib/AITBC/blob/main/README.md)
- [Network Discovery](/rpc/network-info)
