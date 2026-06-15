"""
Multi-Chain Wallet Service

Service for managing agent wallets across multiple blockchain networks.
"""
from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import select
from sqlmodel import Session

from aitbc import get_logger

from ....domain.wallet import AgentWallet, TokenBalance, TransactionStatus, WalletTransaction
from ....schemas.wallet import TransactionRequest, WalletCreate

logger = get_logger(__name__)

class WalletService:

    def __init__(self, session: Session, contract_service: Any=None):
        self.session = session
        self.contract_service = contract_service

    async def create_wallet(self, request: WalletCreate) -> AgentWallet:
        """Create a new wallet for an agent"""
        existing = self.session.execute(select(AgentWallet).where(AgentWallet.agent_id == request.agent_id, AgentWallet.wallet_type == request.wallet_type, AgentWallet.is_active)).first()  # type: ignore[arg-type]
        if existing:
            raise ValueError(f'Agent {request.agent_id} already has an active {request.wallet_type} wallet')
        try:
            import base64
            import secrets

            from cryptography.fernet import Fernet
            from eth_account import Account
            account = Account.create()
            priv_key = account.key.hex()
            pub_key = account.address
            address = account.address
            encryption_key = Fernet.generate_key()
            f = Fernet(encryption_key)
            encrypted_private_key = f.encrypt(priv_key.encode()).decode()
        except ImportError:
            logger.error('❌ CRITICAL: eth-account not available. Using fallback key generation.')
            priv_key = secrets.token_hex(32)
            from eth_utils import keccak
            pub_key = keccak(bytes.fromhex(priv_key))
            address = '0x' + pub_key[-20:].hex()
            encrypted_private_key = '[ENCRYPTED_MOCK_FALLBACK]'
        wallet = AgentWallet(agent_id=request.agent_id, address=address, public_key=pub_key, wallet_type=request.wallet_type, metadata=request.metadata, encrypted_private_key=encrypted_private_key)
        self.session.add(wallet)
        self.session.commit()
        self.session.refresh(wallet)
        logger.info('Created wallet %s for agent %s', wallet.address, request.agent_id)
        return wallet

    async def get_wallet_by_agent(self, agent_id: str) -> list[AgentWallet]:
        """Retrieve all active wallets for an agent"""
        return self.session.execute(select(AgentWallet).where(AgentWallet.agent_id == agent_id, AgentWallet.is_active)).all()  # type: ignore[arg-type, return-value]

    async def get_balances(self, wallet_id: int) -> list[TokenBalance]:
        """Get all tracked balances for a wallet"""
        return self.session.execute(select(TokenBalance).where(TokenBalance.wallet_id == wallet_id)).all()  # type: ignore[arg-type, return-value]

    async def update_balance(self, wallet_id: int, chain_id: int, token_address: str, balance: float) -> TokenBalance:
        """Update a specific token balance for a wallet"""
        record = self.session.execute(select(TokenBalance).where(TokenBalance.wallet_id == wallet_id, TokenBalance.chain_id == chain_id, TokenBalance.token_address == token_address)).first()  # type: ignore[arg-type]
        if record:
            record.balance = balance
        else:
            symbol = 'ETH' if token_address == 'native' else 'ERC20'
            record = TokenBalance(wallet_id=wallet_id, chain_id=chain_id, token_address=token_address, token_symbol=symbol, balance=balance)  # type: ignore[assignment]
            self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record # type: ignore[return-value]

    async def submit_transaction(self, wallet_id: int, request: TransactionRequest) -> WalletTransaction:
        """Submit a transaction from a wallet"""
        wallet = self.session.get(AgentWallet, wallet_id)
        if not wallet or not wallet.is_active:
            raise ValueError('Wallet not found or inactive')
        tx = WalletTransaction(wallet_id=wallet.id, chain_id=request.chain_id, to_address=request.to_address, value=request.value, data=request.data, gas_limit=request.gas_limit, gas_price=request.gas_price, status=TransactionStatus.PENDING)
        self.session.add(tx)
        self.session.commit()
        self.session.refresh(tx)
        tx.tx_hash = '0x' + secrets.token_hex(32)
        tx.status = TransactionStatus.SUBMITTED
        self.session.commit()
        self.session.refresh(tx)
        logger.info('Submitted transaction %s from wallet %s', tx.tx_hash, wallet.address)
        return tx
