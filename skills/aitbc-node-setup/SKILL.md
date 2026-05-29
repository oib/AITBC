---
name: aitbc-node-setup
description: Set up and configure an AITBC blockchain node (hub or follower) including CLI, genesis, and sync
---

# AITBC Node Setup

## Quick Setup (Follower Node)

1. **Clone and run setup:**
```bash
curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/deployment/setup.sh -o /tmp/aitbc_setup.sh
chmod +x /tmp/aitbc_setup.sh
sudo bash /tmp/aitbc_setup.sh
```

2. **Install prerequisites:**
```bash
apt-get install -y python3-pip python3.13-venv postgresql redis-server
```

3. **Configure follower node:**
```bash
# Remove proposer_id from credentials (follower should NOT produce blocks)
rm -f /etc/aitbc/credentials/proposer_id

# Ensure blockchain.env has:
# ENABLE_BLOCK_PRODUCTION=false
# NODE_ROLE=follower
```

4. **Sync genesis from hub:**
```bash
aitbc genesis sync-from-hub --force \
  --rpc-url http://hub.aitbc.bubuit.net:8006 \
  --chain-id ait-hub.aitbc.bubuit.net
```

5. **Start services (paths updated 2026-05-29):**
```bash
ln -sf /opt/aitbc/apps/blockchain-node/aitbc-blockchain-node.service /etc/systemd/system/
ln -sf /opt/aitbc/apps/blockchain-node/aitbc-blockchain-rpc.service /etc/systemd/system/
ln -sf /opt/aitbc/apps/blockchain-node/aitbc-blockchain-p2p.service /etc/systemd/system/
systemctl daemon-reload

systemctl start aitbc-blockchain-p2p
systemctl start aitbc-blockchain-node
systemctl start aitbc-blockchain-rpc
```

6. **Sync chain:**
```bash
/opt/aitbc/venv/bin/python -c "
import sys, asyncio
sys.path.insert(0, '/opt/aitbc/apps/blockchain-node/src')
sys.path.insert(0, '/opt/aitbc')
from aitbc_chain.config import settings
from aitbc_chain.database import session_scope
from aitbc_chain.sync import ChainSync

async def run():
    s = ChainSync(session_factory=session_scope, chain_id=settings.chain_id)
    n = await s.bulk_import_from('http://hub.aitbc.bubuit.net:8006')
    print(f'Imported {n} blocks')
asyncio.run(run())
"
```

## Dependencies

Use the central requirements system:
```bash
pip install -r /opt/aitbc/requirements.txt
pip install -r /opt/aitbc/requirements-dev.txt  # for testing
pip install -e packages/py/aitbc-agent-core -e packages/py/aitbc-agent-sdk -e packages/py/aitbc-crypto -e packages/py/aitbc-sdk
```

## Key Troubleshooting

### Stale .pyc cache
After ANY code change, clear all caches:
```bash
find /opt/aitbc -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

### Block production not disabled
- Remove `/etc/aitbc/credentials/proposer_id`
- Ensure `ENABLE_BLOCK_PRODUCTION=false` in `/etc/aitbc/blockchain.env`
- Check process env: `cat /proc/<pid>/environ | tr '\0' '\n' | grep BLOCK`
- Force kill stale processes: `pkill -9 -f aitbc_chain`
- Wrapper script path: `apps/blockchain-node/aitbc-blockchain-node-wrapper.py` (NOT `scripts/wrappers/`)

### Chain divergence
```bash
systemctl stop aitbc-blockchain-node
rm -rf /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db*
systemctl start aitbc-blockchain-node
# Then re-sync
```

### Git merge conflicts
```bash
git stash  # or: git checkout --theirs <file>
git pull --rebase
```

### Click command name mapping
- Python function `import_wallet` → CLI command `import-wallet`
- Underscores in function names become hyphens in CLI
- Nested groups: `operations governance vote` (not `operations vote`)

### Transaction signing
- pynacl `sign()` returns `SignedMessage` (sig + message)
- Extract signature: `signed.signature` (64 bytes)
- RPC expects top-level `from`, `to`, `amount`, `fee`, `nonce`, `signature`

### Batch sync
- Use `ChainSync.bulk_import_from(url)` directly
- `sync_cli.py` has a bug (import_url parameter doesn't exist)
- Script: `/opt/aitbc/apps/blockchain-node/src/aitbc_chain/sync.py`

### Service File Locations (updated 2026-05-29)
All systemd service files moved from `systemd/` to `apps/<service>/`:
- Blockchain services: `apps/blockchain-node/`
- Coordinator API: `apps/coordinator-api/`
- AI Engine: `apps/ai-engine/`
- Wallet: `apps/wallet/`
- Exchange: `apps/exchange/`
- Explorer: `apps/blockchain-explorer/`
- Marketplace: `apps/marketplace-service/`

See `aitbc-node-management` skill's `references/restructure-paths-2026-05-29.md` for the full mapping.
