# Blockchain Setup

This guide covers configuring the AITBC blockchain node for follower nodes on the island.

## Quick Start (10 minutes)

For a faster setup using the CLI:

```bash
cd /opt/aitbc
python -m venv .venv && source .venv/bin/activate
pip install -e .

aitbc-chain init --name my-node --network ait-devnet
```

Edit `~/.aitbc/chain.yaml`:
```yaml
node:
  name: my-node
  data_dir: ./data
rpc:
  bind_host: 0.0.0.0
  bind_port: 8202
p2p:
  bind_port: 7070
  bootstrap_nodes:
    - /dns4/node-1.aitbc.com/tcp/7070/p2p/...
```

```bash
aitbc-chain start
aitbc-chain status
curl http://localhost:8202/rpc/health
```

## Prerequisites

- Ubuntu Linux system
- Python 3.13+
- Network access to hub.aitbc.bubuit.net
- AITBC codebase installed

**Hardware Requirements:**

AITBC runs from small VPS up, depending on your goal:

| Use Case | CPU | RAM | Storage | Network | GPU |
|----------|-----|-----|---------|---------|-----|
| **Hub Node (run island)** | 2 cores | 2 GB | 50 GB SSD | 50 Mbps | Not required |
| **Follower Node** | 2 cores | 2 GB | 50 GB SSD | 50 Mbps | Not required |
| **With Agent + Ollama (cloud AI)** | 4 cores | 4 GB | 100 GB SSD | 100 Mbps | Not required |
| **Earning Coins (mining)** | 8+ cores | 16+ GB | 500 GB SSD | 1 Gbps | GPU with 16GB+ VRAM (minimum) |
| **Production Hub** | 8+ cores | 16+ GB | 1 TB SSD | 1 Gbps | Optional |

**Notes:**
- For Agent and Ollama, consider using cloud AI models to reduce local hardware requirements
- For earning coins, GPU with 16GB+ VRAM is minimum to load AI models
- Hub nodes can run on minimal hardware for basic island operation

## 1. Install AITBC Blockchain Node

```bash
# Clone repository (if not already done)
cd /opt
git clone <aitbc-repo-url> aitbc
cd /opt/aitbc

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure Blockchain Environment

Create `/etc/aitbc/blockchain.env`:

```bash
CHAIN_ID=ait-hub.aitbc.bubuit.net
SUPPORTED_CHAINS=ait-hub.aitbc.bubuit.net
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8202
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7070
ENABLE_BLOCK_PRODUCTION=false  # Set to false for follower nodes
GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379
MEMPOOL_BACKEND=database
MEMPOOL_DB_URL=postgresql+psycopg2://aitbc_mempool:password@localhost:5432/aitbc_mempool
PROPOSER_ID=<your-proposer-address>
DEFAULT_PEER_RPC_URL=http://hub.aitbc.bubuit.net:8202
P2P_NODE_ID=<your-node-id>
P2P_PEERS=auto
```

### `PROPOSER_ID` and `GENESIS_WALLET_ADDRESS` are different things

Conflating these two has already caused a production outage, so they are worth stating plainly:

| Variable | What it is | Holds funds? |
|---|---|---|
| `PROPOSER_ID` | The identity a node signs blocks *as*. Must match the address of the key in `keystore/proposer.json`, or the blocks it produces fail verification on every follower. | No |
| `GENESIS_WALLET_ADDRESS` | The wallet holding the genesis allocation — the account AIT transfers are sent *from*, paired with `GENESIS_WALLET_PRIVATE_KEY`. Read by bridge-monitor, blockchain-node escrow, and the CLI exchange command. | Yes |

Setting `GENESIS_WALLET_ADDRESS` to the proposer address does not fail loudly. It produces
transfers from an account that does not exist, so bridge deposits and faucet transfers stop
working while block production looks perfectly healthy.

**A follower still needs its own `PROPOSER_ID`**, even with `ENABLE_BLOCK_PRODUCTION=false`.
It is not inert there: the node filters gossip with it, skipping any block whose `proposer`
equals its own as self-proposed (`aitbc_chain/main.py`). Copying the hub's `PROPOSER_ID` into
a follower's env therefore makes that follower silently discard every block the hub gossips.
It still catches up over bulk RPC sync, so the symptom is a node that falls behind and
recovers in bursts rather than one that visibly fails. Use your own node's address, or leave
it empty if the node never produces blocks.

Two things to check when setting it:

- **Write it once.** Settings are read case-insensitively, so `PROPOSER_ID` and `proposer_id`
  are the same setting written two ways — but both reach the process as distinct environment
  variables, and the lowercase spelling wins. An env file containing both has one live value
  and one line of dead text that reads exactly like configuration.
- **It must be the full 40-hex address.** `validate_address` accepts a short `ait1…` body, but
  signature verification canonicalises `ait1<body>` to `0x<body>` only at exactly 40 hex
  characters. A shorter id passes validation, fails to match any keystore entry (`Failed to
  load proposer key from keystore` on every start), and produces blocks no peer can verify.

## 3. Setup Genesis Block

```bash
# Create data directory
mkdir -p /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/

# Copy genesis.json from hub (must match hub's genesis)
# Genesis hash: cb501afac77f861ad145aa7fc1106bb8f9caa90ed5c2498f0d4e73107c327504
```

**Genesis file content:**
```json
{
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "block": {
    "height": 0,
    "hash": "cb501afac77f861ad145aa7fc1106bb8f9caa90ed5c2498f0d4e73107c327504",
    "parent_hash": "0x00",
    "proposer": "ait1db5247d03ca2e40f3995a583b2c097ab703efd4d",
    "timestamp": "2026-05-30T16:50:31.562096+00:00",
    "tx_count": 0,
    "chain_id": "ait-hub.aitbc.bubuit.net",
    "state_root": "0x00",
    "metadata": {
      "chain_type": "mainnet",
      "purpose": "production",
      "consensus_algorithm": "poa"
    }
  },
  "allocations": [
    {
      "address": "ait1db5247d03ca2e40f3995a583b2c097ab703efd4d",
      "balance": 1000000000,
      "nonce": 0
    }
  ]
}
```

> **Copy this byte for byte.** The genesis hash above is computed over these fields, so the
> `proposer` and `allocations[].address` here are historical facts of the chain, not settings.
> They record who proposed block 0 and who received the initial supply. Do **not** update them
> to match a node's current `PROPOSER_ID` — a node whose genesis differs computes a different
> genesis hash and cannot join.

## 4. Start Blockchain Services

```bash
# Create systemd service for blockchain node
cat > /etc/systemd/system/aitbc-blockchain-node.service << 'EOF'
[Unit]
Description=AITBC Blockchain Node
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc
Environment=PATH=/usr/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/etc/aitbc/blockchain.env
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for RPC
cat > /etc/systemd/system/aitbc-blockchain-rpc.service << 'EOF'
[Unit]
Description=AITBC Blockchain RPC API
After=network.target aitbc-blockchain-node.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc
EnvironmentFile=/etc/aitbc/blockchain.env
ExecStart=/opt/aitbc/venv/bin/python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8202
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start services
systemctl daemon-reload
systemctl enable aitbc-blockchain-node.service
systemctl enable aitbc-blockchain-rpc.service
systemctl start aitbc-blockchain-node.service
systemctl start aitbc-blockchain-rpc.service
```

## 5. Verify Sync

```bash
# Check health
curl -s http://localhost:8202/health

# Check genesis block
curl -s http://localhost:8202/rpc/blocks/0

# Should show hash: cb501afac77f861ad145aa7fc1106bb8f9caa90ed5c2498f0d4e73107c327504
```

## See Also

- [Agent Messaging](agent-messaging.md)
- [Configuration Guide](configuration-guide.md)
- [Troubleshooting](../reference/troubleshooting.md)
