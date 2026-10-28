#!/usr/bin/env bash
# bridge-transplant.sh — scripted bc-2 -> island lock transplant (Refs #662, card Lock-B-path)
#
# The relayer is rpc-local: a cross_chain_transfer row is only visible to the
# relayer whose own store holds it. bc-2 locks accepted on an intake rpc (hub)
# never reach the island relayer on hub1. This script performs the proven
# transplant: copy the row into the relayer's source-chain db as pending,
# then fire the explicit relay (the finalizer's own relay phase is
# unreliable — #662 follow-up) with the full rpc-island env, including the
# database mempool backend and the island BRIDGE_RELEASE_PRIVATE_KEY.
#
# Usage:
#   bridge-transplant.sh --transfer-id 0x... [--source-host hub] [--relayer-host hub1]
#                        [--source-chain bc-2] [--target-chain bc-2-island-1] [--dry-run]
set -euo pipefail

TRANSFER_ID=""
SOURCE_HOST="hub"
RELAYER_HOST="hub1"
SOURCE_CHAIN="bc-2"
TARGET_CHAIN="bc-2-island-1"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --transfer-id) TRANSFER_ID="$2"; shift 2 ;;
        --source-host) SOURCE_HOST="$2"; shift 2 ;;
        --relayer-host) RELAYER_HOST="$2"; shift 2 ;;
        --source-chain) SOURCE_CHAIN="$2"; shift 2 ;;
        --target-chain) TARGET_CHAIN="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

[[ -n "$TRANSFER_ID" ]] || { echo "--transfer-id is required" >&2; exit 2; }

echo "==> step 1: read source row on ${SOURCE_HOST} (${SOURCE_CHAIN})"
ROW=$(ssh "$SOURCE_HOST" "python3 -c \"
import sqlite3, json
db = sqlite3.connect('file:/var/lib/aitbc/data/${SOURCE_CHAIN}/chain.db?mode=ro', uri=True)
cols = [r[1] for r in db.execute('PRAGMA table_info(cross_chain_transfer)').fetchall()]
row = db.execute('SELECT * FROM cross_chain_transfer WHERE transfer_id=?', ('${TRANSFER_ID}',)).fetchone()
print(json.dumps(dict(zip(cols, row))) if row else '')
\"")
[[ -n "$ROW" ]] || { echo "ERROR: transfer ${TRANSFER_ID} not found on ${SOURCE_HOST}" >&2; exit 1; }
echo "    source row: $(echo "$ROW" | python3 -c "import json,sys; r=json.load(sys.stdin); print(r['status'], r['source_chain'], '->', r['target_chain'], r['amount'])")"

if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] would insert pending copy into ${RELAYER_HOST} ${SOURCE_CHAIN} db and trigger relay"
    exit 0
fi

echo "==> step 2: transplant pending copy into ${RELAYER_HOST} (${SOURCE_CHAIN})"
echo "$ROW" | ssh "$RELAYER_HOST" "python3 -c \"
import sqlite3, json, sys
row = json.load(sys.stdin)
db = sqlite3.connect('file:/var/lib/aitbc/data/${SOURCE_CHAIN}/chain.db?mode=rw', uri=True)
exists = db.execute('SELECT 1 FROM cross_chain_transfer WHERE transfer_id=?', (row['transfer_id'],)).fetchone()
if exists:
    db.execute('''UPDATE cross_chain_transfer SET status=?, target_tx_hash=NULL,
                  confirm_time=NULL, proof_hash=NULL WHERE transfer_id=?''',
               ('pending', row['transfer_id']))
else:
    cols = [r[1] for r in db.execute('PRAGMA table_info(cross_chain_transfer)').fetchall()]
    row['status'] = 'pending'; row['target_tx_hash'] = None
    row['confirm_time'] = None; row['proof_hash'] = None
    db.execute('INSERT INTO cross_chain_transfer (%s) VALUES (%s)' %
               (','.join(cols), ','.join('?' * len(cols))), [row.get(c) for c in cols])
db.commit()
print('transplanted:', row['transfer_id'][:20], 'pending')
\""

echo "==> step 3: explicit relay on ${RELAYER_HOST} (signed release, database mempool)"
ssh "$RELAYER_HOST" 'cat > /tmp/bridge-relay-trigger.py' <<'PYEOF'
import os, sys, logging
logging.basicConfig(level=logging.INFO)
for f in ("/etc/aitbc/blockchain-island.env", "/etc/aitbc/node-island.env",
          "/etc/aitbc/aitbc-blockchain-rpc-island.env", "/etc/aitbc/blockchain-secrets-island.env",
          "/etc/aitbc/validator-secrets-island.env"):
    try:
        for line in open(f):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass
os.environ["AITBC_DATA_DIR"] = "/var/lib/aitbc"
os.environ["CHAIN_ID"] = os.environ.get("CHAIN_ID", "bc-2-island-1")
sys.path.insert(0, "/opt/aitbc")
sys.path.insert(0, "/opt/aitbc/apps/blockchain-node/src")
from aitbc_chain.mempool import init_mempool
init_mempool(backend=os.environ.get("MEMPOOL_BACKEND", "database"),
             db_url=os.environ.get("MEMPOOL_DB_URL", ""))
from aitbc_chain.database import session_scope
from aitbc_chain.cross_chain.bridge import init_cross_chain_bridge, get_cross_chain_bridge
init_cross_chain_bridge(session_scope)
b = get_cross_chain_bridge()
n = b._relay_pending_transfers(os.environ.get("SOURCE_CHAIN", "bc-2"))
print("relayed:", n)
PYEOF
ssh "$RELAYER_HOST" "/opt/aitbc/venv/bin/python /tmp/bridge-relay-trigger.py"

echo "==> step 4: post-state"
ssh "$RELAYER_HOST" "python3 -c \"
import sqlite3
for f in ('${SOURCE_CHAIN}', '${TARGET_CHAIN}'):
    db = sqlite3.connect(f'file:/var/lib/aitbc/data/{f}/chain.db?mode=ro', uri=True)
    print(f, db.execute('SELECT status, target_tx_hash FROM cross_chain_transfer WHERE transfer_id=?', ('${TRANSFER_ID}',)).fetchall())
\""
echo "done."
