import sys
from pathlib import Path
import json

# Setup sys.path
sys.path.insert(0, str(Path('/opt/aitbc/apps/blockchain-node/src')))

from aitbc_chain.config import settings
from aitbc_chain.mempool import init_mempool, get_mempool

# Use development mempool backend configuration exactly like main node
init_mempool(
    backend=settings.mempool_backend,
    db_path=str(settings.db_path.parent / "mempool.db"),
    max_size=settings.mempool_max_size,
    min_fee=settings.min_fee,
)

mempool = get_mempool()
print(f"Mempool class: {mempool.__class__.__name__}")
print(f"Mempool DB path: {mempool._db_path}")

chain_id = 'ait-mainnet'
rows = mempool._conn.execute("SELECT * FROM mempool WHERE chain_id = ?", (chain_id,)).fetchall()
print(f"Found {len(rows)} raw rows in DB")
for r in rows:
    print(r)

txs = mempool.drain(100, 1000000, chain_id)
print(f"Drained {len(txs)} txs")
for tx in txs:
    print(tx)
