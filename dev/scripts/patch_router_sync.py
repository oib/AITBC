with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Fix sync_status chain_id undefined issue
content = content.replace(
    """@router.get("/syncStatus", summary="Get chain sync status")
async def sync_status() -> Dict[str, Any]:""",
    """@router.get("/syncStatus", summary="Get chain sync status")
async def sync_status(chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

# And fix import_block chain_id
content = content.replace(
    """async def import_block(request: ImportBlockRequest) -> Dict[str, Any]:""",
    """async def import_block(request: ImportBlockRequest, chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

# Replace cfg.chain_id with chain_id in import_block
content = content.replace(
    """    sync = ChainSync(
        session_factory=session_scope,
        chain_id=cfg.chain_id,""",
    """    sync = ChainSync(
        session_factory=session_scope,
        chain_id=chain_id,"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(content)
