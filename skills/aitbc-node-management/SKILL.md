---
name: aitbc-node-management
description: "Deploy, configure, and troubleshoot AITBC blockchain nodes."
version: 1.8.0
author: OWL
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [blockchain, aitbc, deployment, node-management, devops]
    related_skills: [systematic-debugging]
---

# AITBC Node Management

## Path Reference (UPDATED 2026-05-29)

**CRITICAL**: The repo was restructured on 2026-05-29. Many old paths are broken.
See `references/restructure-paths-2026-05-29.md` for the full migration map.

Key changes:
- `systemd/` → `apps/<service>/` (all service files and wrappers)
- `scripts/setup.sh` → `scripts/deployment/setup.sh`
- `infra/` → `scripts/deployment/`
- `requirements-modules/` → central `requirements.txt` / `requirements-optional/`
- `docs/scenarios/`, `docs/agent-training/`, `docs/hermes/`, `docs/planning/` → DELETED

**Old `systemd/` references below are OUTDATED. Use `apps/<service>/` paths.**

## Quick Setup

```bash
# Download setup script directly (process substitution fails in non-interactive shells)
curl -sSL https://raw.githubusercontent.com/oib/AITBC/main/scripts/deployment/setup.sh -o /tmp/aitbc_setup.sh
chmod +x /tmp/aitbc_setup.sh
sudo bash /tmp/aitbc_setup.sh
```

## Prerequisites (install before setup script)

```bash
apt-get install -y python3-pip python3.13-venv postgresql postgresql-contrib redis-server libpq-dev
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt-get install -y nodejs
```

**Gotchas:**
- Node.js v22 may be preinstalled at `/root/.local/bin/node`, taking priority over v24 at `/usr/bin/node`. Remove old symlinks: `rm /root/.local/bin/node` and `ln -sf /usr/bin/node /root/.local/bin/node`.
- If `dpkg` was interrupted earlier, run `dpkg --configure -a` before `apt-get install`.
- If `apt` reports broken packages, run `apt --fix-broken install -y` first.

## Configuration Files

- `/etc/aitbc/blockchain.env` -- chain ID, RPC/P2P settings, block production
- `/etc/aitbc/node.env` -- node ID, island ID, node role, P2P port
- AITBC does NOT use `/etc/aitbc/.env`

Copy templates and customize:
```bash
cp /opt/aitbc/examples/blockchain.env.open-island /etc/aitbc/blockchain.env
cp /opt/aitbc/examples/node.env.open-island /etc/aitbc/node.env
# Edit NODE_ID to be unique
```

## Credentials

If setup script fails before generating credentials, create them manually:

```python
python3 -c "
import secrets
for name in ['api_hash_secret', 'proposer_id', 'keystore_password']:
    with open(f'/etc/aitbc/credentials/{name}', 'w') as f:
        f.write(secrets.token_hex(32) if name != 'keystore_password' else secrets.token_urlsafe(32))
"
chmod 600 /etc/aitbc/credentials/*
```

Then load secrets: `bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh`

## PostgreSQL

The setup script creates 9 databases. If wiped (e.g. by `dpkg --configure -a`), recreate:

```bash
for db in coordinator exchange wallet marketplace governance trading gpu ai mempool; do
  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='aitbc_$db'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE aitbc_$db OWNER aitbc_$db;"
done
```

Set passwords matching what the config expects:
```bash
sudo -u postgres psql -c "ALTER USER aitbc_user WITH PASSWORD 'aitbc_user_password';"
sudo -u postgres psql -c "ALTER USER aitbc_mempool WITH PASSWORD 'aitbc_mempool_password';"
```

## Services (systemd)

```bash
# Link services (paths updated 2026-05-29)
ln -sf /opt/aitbc/apps/blockchain-node/aitbc-blockchain-node.service /etc/systemd/system/
ln -sf /opt/aitbc/apps/blockchain-node/aitbc-blockchain-rpc.service /etc/systemd/system/
ln -sf /opt/aitbc/apps/blockchain-node/aitbc-blockchain-p2p.service /etc/systemd/system/
systemctl daemon-reload

# Start core services
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc aitbc-blockchain-p2p

# Verify
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc aitbc-blockchain-p2p
```

## CLI

```bash
/opt/aitbc/aitbc-cli --help
/opt/aitbc/aitbc-cli wallet list
/opt/aitbc/aitbc-cli genesis info
/opt/aitbc/aitbc-cli blockchain info <chain_id>
```

**`aitbc` on PATH:** Test scripts and documentation use `aitbc` as the command name. A shim is available at `/opt/aitbc/aitbc-cli` that delegates to the venv binary. Add a symlink if tests fail with "command not found":
```bash
ln -sf /opt/aitbc/aitbc-cli /usr/local/bin/aitbc
```

## Genesis Management

### Deterministic Genesis (v1.4.0+)

Genesis blocks are now **deterministic** -- loaded from `genesis.json`, never auto-created. The `_ensure_genesis_block()` method in `poa.py` requires a genesis.json file at `/var/lib/aitbc/data/{chain_id}/genesis.json`.

**For follower nodes** joining an existing chain, sync genesis from the hub:

```bash
# Fetch genesis from hub RPC
aitbc-cli genesis sync-from-hub --force

# Verify
aitbc-cli genesis info
```

The `sync-from-hub` command fetches the genesis block from the hub's `/rpc/blocks-range` endpoint and saves it as `genesis.json`.

**genesis.json format:**
```json
{
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "block": {
    "height": 0,
    "hash": "0x...",
    "parent_hash": "0x00",
    "proposer": "genesis",
    "timestamp": "2026-05-26T18:33:29.295665",
    "tx_count": 0,
    "state_root": "0x..."
  },
  "allocations": []
}
```

**If genesis.json is missing**, the node fails to start with a clear error:
```
RuntimeError: Genesis file required but not found for chain ait-hub.aitbc.bubuit.net.
Please create genesis.json at /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/genesis.json
```

## Debugging Node Issues

### read_file Tool Caching Pitfall

The `read_file` tool may return stale cached content that doesn't match the actual file on disk. When file state is uncertain (e.g., after git pulls, or when user reports changes you can see):

**Always verify with terminal tools:**
```bash
sed -n '22p;24p;134p;136p' /opt/aitbc/cli/aitbc_cli/core/main.py
```
or
```bash
cat -n /opt/aitbc/cli/aitbc_cli/core/main.py | head -30
```

Do NOT trust `read_file` alone when debugging file modification issues. The terminal always reads from disk directly.

### Reading Wallet Files

Wallet files are at `/root/.aitbc/wallets/<name>.json`. They contain:
- `private_key`: hex string with `0x` prefix (32 bytes = 64 hex chars + `0x`)
- `public_key`: hex string with `0x` prefix
- `address`: AITBC address starting with `aitbc1`

When loading the private key for signing, strip the `0x` prefix:
```python
private_key_bytes = bytes.fromhex(wallet["private_key"].replace("0x", ""))
```

### Ed25519 Signing Pitfall

`nacl.signing.SigningKey.sign()` returns a `SignedMessage` object (64-byte signature + message concatenated). To get just the signature:

```python
signed = signing_key.sign(message)
signature = signed.signature  # 64 bytes
sig_hex = signature.hex()     # 128 hex chars
```

Do NOT use `signature.hex()` on the full `SignedMessage` -- it will be too long (216+ hex chars instead of 128).

### Transaction RPC Submission

The `/rpc/transaction` endpoint expects a specific JSON schema. Key points:
- All transaction fields at TOP level, not nested
- `payload` is a separate free-form object (can be `{}`)
- `signature` is required: 64-byte Ed25519 signature as hex string (128 chars)
- `amount` and `fee` must be integers, not floats

```json
{
  "from": "aitbc1...",
  "to": "aitbc1...",
  "amount": 1,
  "fee": 10,
  "nonce": 0,
  "type": "TRANSFER",
  "payload": {},
  "signature": "<64-byte-ed25519-sig-hex>"
}
```

Required fields: `from`, `to`, `amount`, `signature`. Default `fee`: 10, default `nonce`: 0.

**Signing recipe (verified working):**
```python
from nacl.signing import SigningKey
import json

private_key_hex = wallet["private_key"].replace("0x", "")
private_key_bytes = bytes.fromhex(private_key_hex)
signing_key = SigningKey(private_key_bytes)

tx_payload = {"type": "TRANSFER", "from": from_addr, "to": to_addr, "amount": int(amount), "fee": int(fee), "nonce": 0}
message = json.dumps(tx_payload, sort_keys=True).encode()
signed = signing_key.sign(message)
signature = signed.signature  # 64 bytes, NOT the full SignedMessage
```

### CLI Import Cascade Pattern

**Always pull first when CLI commands fail:** `cd /opt/aitbc && git pull`

The CLI entry point (`aitbc_cli.py`) loads `core/main.py` via `importlib.util.spec_from_file_location`. This means **any import error in ANY command file cascades to ALL commands** -- the entire CLI fails at startup.

**Current command availability (as of 2026-05-27):**
- **Working (18 groups, 170+ subcommands):** wallet, genesis, transactions, blockchain, exchange, ai, market, gpu, mining, system, hermes, operations, resource, simulate, edge, workflow, config, crosschain, monitor
- **Disabled (code exists, commented out in main.py):** `analytics`, `deployment`, `node`, `agent_comm` -- require `aitbc_cli.core` module implementation.
- **Re-enabled (2026-05-27):** `cross_chain` and `monitor` -- no core dependencies. Both are fully working as of commit ab0480df.

### Click Command Name Mapping

When adding new subcommands, be aware of Click's name conversion:
- Function names with underscores become hyphenated: `import_wallet` → `import-wallet`, `import_config` → `import-config`
- Nested groups: `operations governance vote` (not `operations vote`)
- Always test with `--help` first to discover actual command names
- The function name in the Python file determines the command name, NOT a separate name parameter

**Test script pitfall:** Test scripts often use underscore names (e.g., `get_gpu`) but Click registers them with hyphens (`get-gpu`). When a test fails with "No such command", check `aitbc <group> <subgroup> --help` for the actual command name. This affected ALL 19 edge subcommands in `test_edge_advanced.sh`.

**Edge CLI positional args pitfall:** Most edge subcommands take positional arguments, NOT `--flag value` options. For example:
- `aitbc edge gpu get-gpu GPU_ID` (NOT `get-gpu --gpu-id GPU_ID`)
- `aitbc edge database init-db DATABASE_ID ISLAND_ID CAPACITY_GB` (NOT `init-db --db-name X`)
- `aitbc edge serve submit-request GPU_ID MODEL_NAME INPUT_DATA` (NOT `submit-request --request-type X`)

Always check `aitbc edge <group> <command> --help` for the correct argument style before writing test invocations.

### ctx.obj Key Naming Pitfall

The CLI's `cli()` function in `main.py` sets these keys in `ctx.obj`:
- `url`, `api_key`, `output`, `verbose`, `debug`, `chain_id`

Command code accessing `ctx.obj` must use these exact keys. Common mistakes:
- `ctx.obj['output_format']` → should be `ctx.obj['output']`
- `ctx.obj['config']` → does not exist; build config from `ctx.obj['url']` directly

### Click CliRunner Isolated Mode Pitfall

Python unit tests using Click's `CliRunner` in isolated mode do NOT invoke the top-level `cli()` function, so `ctx.obj` is never populated. Tests that call commands accessing `ctx.obj['output']` will fail with `KeyError`.

**Fix options:**
1. Add a pytest fixture that patches `ctx.obj` with default values
2. Change command code to use `ctx.obj.get('output', 'table')` instead of direct dict access
3. Use `CliRunner.invoke()` with `obj={...}` parameter

### Python Test Import Pitfalls

When writing Python tests that import CLI command modules:
- `aitbc_cli.commands.governance` → does NOT exist; governance is inside `operations.py`
- `aitbc_cli.commands.marketplace` → does NOT exist; the file is `marketplace_cmd.py`
- All tests need `cli/` on `sys.path` to import `aitbc_cli.*` -- add to `tests/conftest.py`:
  ```python
  sys.path.insert(0, str(project_root / "cli"))
  ```
- `tests/__init__.py` must exist (even empty) for `from tests.fixtures.common` to work

### Import/Add_command Half-State Pitfall

When re-enabling disabled CLI commands, BOTH the import line AND the `add_command` line must be uncommented. A half-state (one uncommented, the other still commented) causes:
- Import uncommented + add_command commented → command loaded but not registered (silent)
- Import commented + add_command uncommented → `NameError: name 'X' is not defined` on startup

Always verify both lines are in sync after re-enabling commands.

### transactions send -- Full Error Chain

When running `transactions send`, errors progress through several stages as fixes are applied:

1. **`termios.error: (25, 'Inappropriate ioctl for device')`** -- `getpass` requires TTY. Fixed by checking `--password`, `--password-file`, or `AITBC_WALLET_PASSWORD` env var before calling `getpass`.

2. **`Wallet 'X' not found`** -- Wallet path mismatch. `wallet create` saves to `/root/.aitbc/wallets/` but `transactions send` looks elsewhere. Fixed by aligning wallet path resolution.

3. **`Error decrypting wallet: Unsupported cipher`** -- Wallet created with `--no-encrypt` still triggers decryption. Fixed by detecting unencrypted wallets and skipping decryption.

4. **`Error loading private key: non-hexadecimal number found in fromhex()`** -- Private key stored with `0x` prefix in wallet JSON. Fixed by stripping prefix before hex decode.

5. **`AttributeError: 'bytes' object has no attribute 'signature'`** -- Code calls `.signature` on raw bytes instead of a `SigningKey` object. Fix: wrap bytes in `SigningKey(private_key_bytes)` first.

6. **`422 Unprocessable Content` (missing signature)** -- Transaction not signed. `SigningKey.sign()` returns `SignedMessage` (64-byte sig + message). Must extract `.signature` to get just the 64 bytes, then `.hex()` for the hex string.

7. **`400: Failed to submit transaction: transaction.to is required`** -- Server-side bug in `submit_transaction()`. The function reads `tx_data.payload.get("to")` instead of using the already-validated `tx_data.recipient` field. Fix: change to `"to": tx_data.payload.get("to") or tx_data.recipient`.

### Server-Side Code Updates

When the AITBC team pushes server-side fixes, you MUST restart the RPC service:
```bash
systemctl restart aitbc-blockchain-rpc
```

### Gossip Sync Monitoring

```bash
watch -n5 'curl -s http://localhost:8006/rpc/head | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Local: {d[\"height\"]}, tx: {d[\"tx_count\"]}\")"'
journalctl -u aitbc-blockchain-p2p -f | grep -E "block|import|sync|peer"
```

### Follower Node Block Production Issue

**CRITICAL:** The wrapper script previously force-set `AITBC_FORCE_ENABLE_BLOCK_PRODUCTION=true`. Removed in commit 00497a65.

**Fix for follower nodes -- THREE steps:**
```bash
# 1. Remove proposer_id from credentials
rm /etc/aitbc/credentials/proposer_id

# 2. Clear stale wrapper env overrides
grep -q 'AITBC_FORCE_ENABLE_BLOCK_PRODUCTION' /opt/aitbc/apps/blockchain-node/aitbc-blockchain-node-wrapper.py && \
  sed -i '/AITBC_FORCE_ENABLE_BLOCK_PRODUCTION/d; /ENABLE_BLOCK_PRODUCTION/d; /enable_block_production/d' \
  /opt/aitbc/apps/blockchain-node/aitbc-blockchain-node-wrapper.py

# 3. Full clean restart
rm /run/aitbc/secrets/.env
bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh
systemctl stop aitbc-blockchain-node
pkill -9 -f aitbc_chain 2>/dev/null || true
sleep 2
find /opt/aitbc -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
systemctl start aitbc-blockchain-node
```

**Verification:** Check logs for "Block production disabled on this node" -- NOT "Starting PoA proposer loop".

**Stale .pyc issue:** After modifying Python source files, stale `.pyc` bytecode caches may cause OLD code to keep running. Always clear:
```bash
find /opt/aitbc -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```
Then restart. If code changes don't take effect, the `.pyc` is stale.

### Batch Sync for Fast Catch-Up

```python
import asyncio, os, sys
sys.path.insert(0, "/opt/aitbc/apps/blockchain-node/src")
os.environ["PYTHONPATH"] = "/opt/aitbc/apps/blockchain-node/src:/opt/aitbc"
from aitbc_chain.config import settings
from aitbc_chain.database import session_scope
from aitbc_chain.sync import ChainSync

async def run():
    sync = ChainSync(session_factory=session_scope, chain_id=settings.chain_id, batch_size=500, poll_interval=0.5)
    try:
        imported = await sync.bulk_import_from("<HUB_RPC_URL>")
        print(f"Imported {imported} blocks")
    finally:
        await sync.close()
asyncio.run(run())
```

### load-keystore-secrets.sh Duplicate Entry Bug (fixed 9ec53892)

The script previously appended to `/run/aitbc/secrets/.env` without clearing it first. Fixed by adding `> "$ENV_FILE"` at the start. If duplicates accumulated:
```bash
rm /run/aitbc/secrets/.env
bash /opt/aitbc/scripts/utils/load-keystore-secrets.sh
```

### Git Divergent Branches

When `git pull` fails with "divergent branches" (e.g. after a force-push):
```bash
git stash
git pull --rebase origin main
git stash pop
```
Unlike merge, rebase preserves a linear history. Local unpublished commits are replayed on top of the incoming remote commits. If any local changes are truly stale, skip the stash and just `git checkout -- .` before pulling.

### Git Merge Conflicts

When local changes conflict with upstream pulls:
```bash
git stash
git pull
git stash pop
# Or: git checkout --theirs <file> to accept upstream version
```

If local WIP changes are not needed:
```bash
git checkout -- .
git pull
```

## Scenario Testing Workflow

When asked to run/play scenarios:
1. **Do NOT fix or debug issues** -- only describe the issue and suggest a fix
2. User pushes fixes, then says "retry"
3. Cycle: agent analyzes → describes issue + suggests fix → user pushes → agent retries
4. Exception: if user explicitly says to proceed with setup/joining, continue iteratively

## Data Directory Paths (Updated 2026-05-27)

**Canonical data directory:** `/var/lib/aitbc/data/` (NOT `/opt/aitbc/data/`)

All scripts, systemd services, and configuration files have been migrated. If you encounter `/opt/aitbc/data/` in any file, it should be updated to `/var/lib/aitbc/data/`.

Key subdirectories:
- `/var/lib/aitbc/data/{chain_id}/genesis.json` -- genesis block files
- `/var/lib/aitbc/data/coordinator.db` -- coordinator SQLite database
- `/var/lib/aitbc/keystore/` -- wallet keystore

## Edge API Service Setup

The edge API service file is at `/opt/aitbc/apps/aitbc-edge/edge-api.service` (NOT in `/opt/aitbc/systemd/`). To deploy:

```bash
# Link service
ln -sf /opt/aitbc/apps/aitbc-edge/edge-api.service /etc/systemd/system/edge-api.service
systemctl daemon-reload
systemctl start edge-api
```

The edge API uses SQLite (aiosqlite) for storage and runs on port 8103 by default.

## Ollama Installation (Required for AI Inference)

The production miner requires Ollama running on port 11434. Without it, the miner exits immediately.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start service
systemctl start ollama

# Pull a model that fits in available VRAM
ollama pull llama3.2:3b    # 2GB, fits in 16GB VRAM

# Verify
curl http://localhost:11434/api/tags
```

**Note:** On GPU hosts, Ollama auto-detects NVIDIA GPUs during installation. Verify with `nvidia-smi` that the GPU shows activity during inference.

## Troubleshooting

### Service Dependency Chain

When starting AITBC production services, start in this order:

```
1. PostgreSQL + Redis         (databases + gossip network)
2. Ollama (port 11434)        (AI runtime for inference)
3. blockchain-node (port 8006) (blockchain data)
4. blockchain-p2p (port 8001) (peer networking)
5. blockchain-rpc (port 8006) (RPC API)
6. coordinator-api (port 8011) (central orchestrator)
7. production-miner           (needs Ollama + coordinator)
```

**Critical:** The production miner exits on startup if Ollama is not reachable on port 11434. Always start Ollama first.

**Critical:** After modifying any Python source file (miner, CLI commands, etc.), you MUST restart the relevant systemd service. Stale processes keep running old code even after files change on disk:
```bash
systemctl restart aitbc-production-miner
```

### Miner Job Type Inference

The `production_miner.py` `execute_job` function checks `payload.get('type')` to determine how to process a job. Jobs submitted via the API with `model`/`prompt` fields but no explicit `type` field will have `type=None` and fall through to "Unsupported job type".

**Fix:** Add fallback inference before the type check:
```python
job_type = payload.get('type')
if job_type is None and 'model' in payload and 'prompt' in payload:
    job_type = 'inference'
```

### Miner Service PATH Fix

The production miner systemd service must include system binaries in PATH:

```
[Service]
Environment="PATH=/opt/aitbc/venv/bin:/usr/bin:/usr/local/bin"
```

Without `/usr/bin`, `nvidia-smi` is not found and the miner falls back to CPU-only mode. After any PATH change:
```bash
systemctl daemon-reload && systemctl restart aitbc-production-miner
```

Verify GPU detection: `journalctl -u aitbc-production-miner | grep "GPU detected"`

### Coordinator API & Production Services

For production service deployment (coordinator, miner, Ollama), see the **aitbc-deployment** skill.

```bash
# Link and start coordinator API
ln -sf /opt/aitbc/apps/coordinator-api/aitbc-coordinator-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl start aitbc-coordinator-api

# Verify
curl http://localhost:8011/health
```

## Monitoring

```bash
# Chain status
curl -s http://localhost:8006/rpc/head | python3 -m json.tool

# Hub comparison
curl -s <HUB_RPC_URL>/rpc/head | python3 -m json.tool

# Service logs
journalctl -u aitbc-blockchain-node -f
journalctl -u aitbc-blockchain-p2p -f
```
