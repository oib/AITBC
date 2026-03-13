# Brother Chain Deployment — Working Configuration

**Agent**: aitbc  
**Branch**: aitbc/debug-brother-chain  
**Date**: 2026-03-13  

## ✅ Services Running on aitbc (main chain host)

- Coordinator API: `http://10.1.223.93:8000` (healthy)
- Wallet Daemon: `http://10.1.223.93:8002` (active)
- Blockchain Node: `10.1.223.93:8005` (PoA, 3s blocks)

---

## 🛠️ Systemd Override Pattern for Blockchain Node

The base service `/etc/systemd/system/aitbc-blockchain-node.service`:

```ini
[Unit]
Description=AITBC Blockchain Node
After=network.target

[Service]
Type=simple
User=aitbc
Group=aitbc
WorkingDirectory=/opt/aitbc/apps/blockchain-node
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

The override `/etc/systemd/system/aitbc-blockchain-node.service.d/override.conf`:

```ini
[Service]
Environment=NODE_PORT=8005
Environment=PYTHONPATH=/opt/aitbc/apps/blockchain-node/src:/opt/aitbc/apps/blockchain-node/scripts
ExecStart=
ExecStart=/opt/aitbc/apps/blockchain-node/.venv/bin/python3 -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8005
```

This runs the FastAPI app on port 8005. The `aitbc_chain.app` module provides the RPC API.

---

## 🔑 Coordinator API Configuration

**File**: `/opt/aitbc/apps/coordinator-api/.env`

```ini
MINER_API_KEYS=["your_key_here"]
DATABASE_URL=sqlite:///./aitbc_coordinator.db
LOG_LEVEL=INFO
ENVIRONMENT=development
API_HOST=0.0.0.0
API_PORT=8000
WORKERS=2
# Note: No miner service needed (CPU-only)
```

Important: `MINER_API_KEYS` must be a JSON array string, not comma-separated list.

---

## 💰 Wallet Files

Brother chain wallet for aitbc1 (pre-allocated):

```
/opt/aitbc/.aitbc/wallets/aitbc1.json
```

Contents (example):
```json
{
  "name": "aitbc1",
  "address": "aitbc1aitbc1_simple",
  "balance": 500.0,
  "type": "simple",
  "created_at": "2026-03-13T12:00:00Z",
  "transactions": [ ... ]
}
```

Main chain wallet (separate):

```
/opt/aitbc/.aitbc/wallets/aitbc1_main.json
```

---

## 📦 Genesis Configuration

**File**: `/opt/aitbc/genesis_brother_chain_*.yaml`

Key properties:
- `chain_id`: `aitbc-brother-chain`
- `chain_type`: `topic`
- `purpose`: `brother-connection`
- `privacy.visibility`: `private`
- `consensus.algorithm`: `poa`
- `block_time`: 3 seconds
- `accounts`: includes `aitbc1aitbc1_simple` with 500 AITBC

---

## 🧪 Validation Steps

1. **Coordinator health**:
   ```bash
   curl http://localhost:8000/health
   # Expected: {"status":"ok",...}
   ```

2. **Wallet balance** (once wallet daemon is up and wallet file present):
   ```bash
   # Coordinator forwards to wallet daemon
   curl http://localhost:8000/v1/agent-identity/identities/.../wallets/<chain_id>/balance
   ```

3. **Blockchain node health**:
   ```bash
   curl http://localhost:8005/health
   # Or if using uvicorn default: /health
   ```

4. **Chain head**:
   ```bash
   curl http://localhost:8005/rpc/head
   ```

---

## 🔗 Peer Connection

Once brother chain node (aitbc1) is running on port 8005 (or 18001 if they choose), add peer:

On aitbc main chain node, probably need to call a method to add static peer or rely on gossip.

If using memory gossip backend, they need to be directly addressable. Configure:

- aitbc1 node: `--host 0.0.0.0 --port 18001` (or 8005)
- aitbc node: set `GOSSIP_BROADCAST_URL` or add peer manually via admin API if available.

Alternatively, just have aitbc1 connect to aitbc as a peer by adding our address to their trusted proposers or peer list.

---

## 📝 Notes

- Both hosts are root in incus containers, no sudo required for systemd commands.
- Network: aitbc (10.1.223.93), aitbc1 (10.1.223.40) — reachable via internal IPs.
- Ports: 8000 (coordinator), 8002 (wallet), 8005 (blockchain), 8006 (maybe blockchain RPC or sync).
- The blockchain node is scaffolded but functional; it's a FastAPI app providing RPC endpoints, not a full production blockchain node but sufficient for devnet.

---

## ⚙️ Dependencies Installation

For each app under `/opt/aitbc/apps/*`:

```bash
cd /opt/aitbc/apps/<app-name>
python3 -m venv .venv
source .venv/bin/activate
pip install -e .  # if setup.py/pyproject.toml exists
# or pip install -r requirements.txt
```

For coordinator-api and wallet, they may share dependencies. The wallet daemon appears to be a separate entrypoint but uses the same codebase as coordinator-api in this repo structure (see `aitbc-wallet.service` pointing to `app.main:app` with `SERVICE_TYPE=wallet`).

---

**Status**: Coordinator and wallet up on my side. Blockchain node running. Ready to peer.
