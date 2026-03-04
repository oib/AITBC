with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Update Account endpoint
content = content.replace(
    """        account = session.get(Account, address)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        # Get transaction counts
        sent_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.sender == address)).one()
        received_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.recipient == address)).one()""",
    """        account = session.exec(select(Account).where(Account.address == address)).first()
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        # Get transaction counts
        sent_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.sender == address)).one()
        received_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.recipient == address)).one()"""
)

# Replace all hardcoded cfg.chain_id with a query parameter or path parameter where applicable
content = content.replace(
    """@router.get("/head", summary="Get the current chain head block")
async def get_head() -> Dict[str, Any]:""",
    """@router.get("/head", summary="Get the current chain head block")
async def get_head(chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

content = content.replace(
    """select(Block).order_by(Block.height.desc()).limit(1)""",
    """select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)"""
)

content = content.replace(
    """@router.get("/blocks/{height_or_hash}", summary="Get a block by height or hash")
async def get_block(height_or_hash: str) -> Dict[str, Any]:""",
    """@router.get("/blocks/{height_or_hash}", summary="Get a block by height or hash")
async def get_block(height_or_hash: str, chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

content = content.replace(
    """query = select(Block).where(Block.height == height)""",
    """query = select(Block).where(Block.chain_id == chain_id).where(Block.height == height)"""
)

content = content.replace(
    """query = select(Block).where(Block.hash == height_or_hash)""",
    """query = select(Block).where(Block.chain_id == chain_id).where(Block.hash == height_or_hash)"""
)

content = content.replace(
    """        txs = session.exec(select(Transaction).where(Transaction.block_height == block.height)).all()""",
    """        txs = session.exec(select(Transaction).where(Transaction.chain_id == chain_id).where(Transaction.block_height == block.height)).all()"""
)

content = content.replace(
    """        receipts = session.exec(select(Receipt).where(Receipt.block_height == block.height)).all()""",
    """        receipts = session.exec(select(Receipt).where(Receipt.chain_id == chain_id).where(Receipt.block_height == block.height)).all()"""
)

content = content.replace(
    """@router.get("/transactions/{tx_hash}", summary="Get a transaction by hash")
async def get_transaction(tx_hash: str) -> Dict[str, Any]:""",
    """@router.get("/transactions/{tx_hash}", summary="Get a transaction by hash")
async def get_transaction(tx_hash: str, chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

content = content.replace(
    """        tx = session.exec(select(Transaction).where(Transaction.tx_hash == tx_hash)).first()""",
    """        tx = session.exec(select(Transaction).where(Transaction.chain_id == chain_id).where(Transaction.tx_hash == tx_hash)).first()"""
)

content = content.replace(
    """        # If not in block, check mempool
        if tx is None:
            mempool_txs = get_mempool().list_transactions()""",
    """        # If not in block, check mempool
        if tx is None:
            mempool_txs = get_mempool().list_transactions(chain_id)"""
)

content = content.replace(
    """@router.get("/mempool", summary="Get current mempool transactions")
async def get_mempool_txs() -> List[Dict[str, Any]]:""",
    """@router.get("/mempool", summary="Get current mempool transactions")
async def get_mempool_txs(chain_id: str = "ait-devnet") -> List[Dict[str, Any]]:"""
)

content = content.replace(
    """    txs = get_mempool().list_transactions()""",
    """    txs = get_mempool().list_transactions(chain_id)"""
)

content = content.replace(
    """@router.get("/metrics", summary="Get node metrics")
async def get_metrics() -> PlainTextResponse:""",
    """@router.get("/chains", summary="Get supported chains")
async def get_chains() -> List[str]:
    from ..config import settings as cfg
    return [c.strip() for c in cfg.supported_chains.split(",")]

@router.get("/metrics", summary="Get node metrics")
async def get_metrics() -> PlainTextResponse:"""
)

content = content.replace(
    """async def import_block(request: ImportBlockRequest) -> Dict[str, Any]:""",
    """async def import_block(request: ImportBlockRequest, chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

content = content.replace(
    """    sync = ChainSync(
        session_factory=session_scope,
        chain_id=cfg.chain_id,
        max_reorg_depth=cfg.max_reorg_depth,
        validator=validator,
        validate_signatures=cfg.sync_validate_signatures,
    )""",
    """    sync = ChainSync(
        session_factory=session_scope,
        chain_id=chain_id,
        max_reorg_depth=cfg.max_reorg_depth,
        validator=validator,
        validate_signatures=cfg.sync_validate_signatures,
    )"""
)

content = content.replace(
    """@router.get("/syncStatus", summary="Get chain sync status")
async def sync_status() -> Dict[str, Any]:""",
    """@router.get("/syncStatus", summary="Get chain sync status")
async def sync_status(chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

content = content.replace(
    """    sync = ChainSync(session_factory=session_scope, chain_id=cfg.chain_id)""",
    """    sync = ChainSync(session_factory=session_scope, chain_id=chain_id)"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(content)
