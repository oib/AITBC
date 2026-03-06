with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Fix get_head
content = content.replace(
    "async def get_head() -> Dict[str, Any]:",
    "async def get_head(chain_id: str = \"ait-devnet\") -> Dict[str, Any]:"
)

# Fix other endpoints that are missing chain_id
content = content.replace(
    "async def get_block(height_or_hash: str) -> Dict[str, Any]:",
    "async def get_block(height_or_hash: str, chain_id: str = \"ait-devnet\") -> Dict[str, Any]:"
)

content = content.replace(
    "async def get_transaction(tx_hash: str) -> Dict[str, Any]:",
    "async def get_transaction(tx_hash: str, chain_id: str = \"ait-devnet\") -> Dict[str, Any]:"
)

content = content.replace(
    "async def get_mempool_txs() -> List[Dict[str, Any]]:",
    "async def get_mempool_txs(chain_id: str = \"ait-devnet\") -> List[Dict[str, Any]]:"
)

content = content.replace(
    "async def sync_status() -> Dict[str, Any]:",
    "async def sync_status(chain_id: str = \"ait-devnet\") -> Dict[str, Any]:"
)

content = content.replace(
    "async def import_block(request: ImportBlockRequest) -> Dict[str, Any]:",
    "async def import_block(request: ImportBlockRequest, chain_id: str = \"ait-devnet\") -> Dict[str, Any]:"
)

# Fix transaction model dumping for chain_id
content = content.replace(
    "        tx_hash = mempool.add(tx_dict)",
    "        tx_hash = mempool.add(tx_dict, chain_id=chain_id)"
)

content = content.replace(
    "        response = await send_transaction(tx_request)",
    "        response = await send_transaction(tx_request, chain_id=chain_id)"
)

# In get_addresses the missing param is chain_id
content = content.replace(
    """async def get_addresses(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_balance: int = Query(0, ge=0),
) -> Dict[str, Any]:""",
    """async def get_addresses(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_balance: int = Query(0, ge=0),
    chain_id: str = "ait-devnet"
) -> Dict[str, Any]:"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(content)
