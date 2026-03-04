with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "r") as f:
    content = f.read()

# Update get_addresses endpoint
content = content.replace(
    """@router.get("/addresses", summary="Get a list of top addresses by balance")
async def get_addresses(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_balance: int = Query(0, ge=0),
) -> Dict[str, Any]:""",
    """@router.get("/addresses", summary="Get a list of top addresses by balance")
async def get_addresses(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_balance: int = Query(0, ge=0),
    chain_id: str = "ait-devnet"
) -> Dict[str, Any]:"""
)

content = content.replace(
    """        addresses = session.exec(
            select(Account)
            .where(Account.balance >= min_balance)""",
    """        addresses = session.exec(
            select(Account)
            .where(Account.chain_id == chain_id)
            .where(Account.balance >= min_balance)"""
)

content = content.replace(
    """        total_count = len(session.exec(select(Account).where(Account.balance >= min_balance)).all())""",
    """        total_count = len(session.exec(select(Account).where(Account.chain_id == chain_id).where(Account.balance >= min_balance)).all())"""
)

content = content.replace(
    """            sent_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.sender == addr.address)).one()
            received_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.recipient == addr.address)).one()""",
    """            sent_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.chain_id == chain_id).where(Transaction.sender == addr.address)).one()
            received_count = session.exec(select(func.count()).select_from(Transaction).where(Transaction.chain_id == chain_id).where(Transaction.recipient == addr.address)).one()"""
)

# Update send_transaction endpoint
content = content.replace(
    """@router.post("/sendTx", summary="Submit a new transaction")
async def send_transaction(request: TransactionRequest) -> Dict[str, Any]:""",
    """@router.post("/sendTx", summary="Submit a new transaction")
async def send_transaction(request: TransactionRequest, chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

content = content.replace(
    """        tx_hash = mempool.add(tx_dict)""",
    """        tx_hash = mempool.add(tx_dict, chain_id)"""
)

# Update submit_receipt endpoint
content = content.replace(
    """@router.post("/submitReceipt", summary="Submit receipt claim transaction")
async def submit_receipt(request: ReceiptSubmissionRequest) -> Dict[str, Any]:""",
    """@router.post("/submitReceipt", summary="Submit receipt claim transaction")
async def submit_receipt(request: ReceiptSubmissionRequest, chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

content = content.replace(
    """        response = await send_transaction(tx_request)""",
    """        response = await send_transaction(tx_request, chain_id)"""
)

# Update mint_faucet endpoint
content = content.replace(
    """@router.post("/admin/mintFaucet", summary="Mint devnet funds to an address")
async def mint_faucet(request: MintFaucetRequest) -> Dict[str, Any]:""",
    """@router.post("/admin/mintFaucet", summary="Mint devnet funds to an address")
async def mint_faucet(request: MintFaucetRequest, chain_id: str = "ait-devnet") -> Dict[str, Any]:"""
)

content = content.replace(
    """        account = session.exec(select(Account).where(Account.address == request.address)).first()
        if account is None:
            account = Account(address=request.address, balance=request.amount)""",
    """        account = session.exec(select(Account).where(Account.chain_id == chain_id).where(Account.address == request.address)).first()
        if account is None:
            account = Account(chain_id=chain_id, address=request.address, balance=request.amount)"""
)

# Update _update_balances and _update_balance (if they exist)
content = content.replace(
    """            sender_acc = session.exec(select(Account).where(Account.address == tx.sender)).first()
            if not sender_acc:
                sender_acc = Account(address=tx.sender, balance=0)""",
    """            sender_acc = session.exec(select(Account).where(Account.chain_id == chain_id).where(Account.address == tx.sender)).first()
            if not sender_acc:
                sender_acc = Account(chain_id=chain_id, address=tx.sender, balance=0)"""
)

content = content.replace(
    """            recipient_acc = session.exec(select(Account).where(Account.address == tx.recipient)).first()
            if not recipient_acc:
                recipient_acc = Account(address=tx.recipient, balance=0)""",
    """            recipient_acc = session.exec(select(Account).where(Account.chain_id == chain_id).where(Account.address == tx.recipient)).first()
            if not recipient_acc:
                recipient_acc = Account(chain_id=chain_id, address=tx.recipient, balance=0)"""
)

with open("/home/oib/windsurf/aitbc/apps/blockchain-node/src/aitbc_chain/rpc/router.py", "w") as f:
    f.write(content)
