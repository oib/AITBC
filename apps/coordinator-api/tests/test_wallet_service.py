import pytest
from unittest.mock import AsyncMock

from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.services.wallet_service import WalletService
from app.domain.wallet import WalletType, NetworkType, NetworkConfig, TransactionStatus
from app.schemas.wallet import WalletCreate, TransactionRequest

@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()

@pytest.fixture
def mock_contract_service():
    return AsyncMock()

@pytest.fixture
def wallet_service(test_db, mock_contract_service):
    # Setup some basic networks
    network = NetworkConfig(
        chain_id=1,
        name="Ethereum",
        network_type=NetworkType.EVM,
        rpc_url="http://localhost:8545",
        explorer_url="http://etherscan.io",
        native_currency_symbol="ETH"
    )
    test_db.add(network)
    test_db.commit()
    
    return WalletService(session=test_db, contract_service=mock_contract_service)

@pytest.mark.asyncio
async def test_create_wallet(wallet_service):
    request = WalletCreate(agent_id="agent-123", wallet_type=WalletType.EOA)
    wallet = await wallet_service.create_wallet(request)
    
    assert wallet.agent_id == "agent-123"
    assert wallet.wallet_type == WalletType.EOA
    assert wallet.address.startswith("0x")
    assert wallet.is_active is True

@pytest.mark.asyncio
async def test_create_duplicate_wallet_fails(wallet_service):
    request = WalletCreate(agent_id="agent-123", wallet_type=WalletType.EOA)
    await wallet_service.create_wallet(request)
    
    with pytest.raises(ValueError):
        await wallet_service.create_wallet(request)

@pytest.mark.asyncio
async def test_get_wallet_by_agent(wallet_service):
    await wallet_service.create_wallet(WalletCreate(agent_id="agent-123", wallet_type=WalletType.EOA))
    await wallet_service.create_wallet(WalletCreate(agent_id="agent-123", wallet_type=WalletType.SMART_CONTRACT))
    
    wallets = await wallet_service.get_wallet_by_agent("agent-123")
    assert len(wallets) == 2

@pytest.mark.asyncio
async def test_update_balance(wallet_service):
    wallet = await wallet_service.create_wallet(WalletCreate(agent_id="agent-123"))
    
    balance = await wallet_service.update_balance(
        wallet_id=wallet.id,
        chain_id=1,
        token_address="native",
        balance=10.5
    )
    
    assert balance.balance == 10.5
    assert balance.token_symbol == "ETH"
    
    # Update existing
    balance2 = await wallet_service.update_balance(
        wallet_id=wallet.id,
        chain_id=1,
        token_address="native",
        balance=20.0
    )
    assert balance2.id == balance.id
    assert balance2.balance == 20.0

@pytest.mark.asyncio
async def test_submit_transaction(wallet_service):
    wallet = await wallet_service.create_wallet(WalletCreate(agent_id="agent-123"))
    
    tx_req = TransactionRequest(
        chain_id=1,
        to_address="0x1234567890123456789012345678901234567890",
        value=1.5
    )
    
    tx = await wallet_service.submit_transaction(wallet.id, tx_req)
    
    assert tx.wallet_id == wallet.id
    assert tx.chain_id == 1
    assert tx.to_address == tx_req.to_address
    assert tx.value == 1.5
    assert tx.status == TransactionStatus.SUBMITTED
    assert tx.tx_hash is not None
    assert tx.tx_hash.startswith("0x")
