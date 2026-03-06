"""
Multi-Chain Wallet Service

Service for managing agent wallets across multiple blockchain networks.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict
from sqlalchemy import select
from sqlmodel import Session

from ..domain.wallet import (
    AgentWallet, NetworkConfig, TokenBalance, WalletTransaction,
    WalletType, TransactionStatus
)
from ..schemas.wallet import WalletCreate, TransactionRequest
from ..blockchain.contract_interactions import ContractInteractionService

# In a real scenario, these would be proper cryptographic key generation utilities
import secrets
import hashlib

logger = logging.getLogger(__name__)

class WalletService:
    def __init__(
        self,
        session: Session,
        contract_service: ContractInteractionService
    ):
        self.session = session
        self.contract_service = contract_service

    async def create_wallet(self, request: WalletCreate) -> AgentWallet:
        """Create a new wallet for an agent"""
        
        # Check if agent already has an active wallet of this type
        existing = self.session.execute(
            select(AgentWallet).where(
                AgentWallet.agent_id == request.agent_id,
                AgentWallet.wallet_type == request.wallet_type,
                AgentWallet.is_active == True
            )
        ).first()
        
        if existing:
            raise ValueError(f"Agent {request.agent_id} already has an active {request.wallet_type} wallet")

        # Simulate key generation (in reality, use a secure KMS or HSM)
        priv_key = secrets.token_hex(32)
        pub_key = hashlib.sha256(priv_key.encode()).hexdigest()
        # Fake Ethereum address derivation for simulation
        address = "0x" + hashlib.sha3_256(pub_key.encode()).hexdigest()[-40:]

        wallet = AgentWallet(
            agent_id=request.agent_id,
            address=address,
            public_key=pub_key,
            wallet_type=request.wallet_type,
            metadata=request.metadata,
            encrypted_private_key="[ENCRYPTED_MOCK]" # Real implementation would encrypt it securely
        )
        
        self.session.add(wallet)
        self.session.commit()
        self.session.refresh(wallet)
        
        logger.info(f"Created wallet {wallet.address} for agent {request.agent_id}")
        return wallet

    async def get_wallet_by_agent(self, agent_id: str) -> List[AgentWallet]:
        """Retrieve all active wallets for an agent"""
        return self.session.execute(
            select(AgentWallet).where(
                AgentWallet.agent_id == agent_id,
                AgentWallet.is_active == True
            )
        ).all()

    async def get_balances(self, wallet_id: int) -> List[TokenBalance]:
        """Get all tracked balances for a wallet"""
        return self.session.execute(
            select(TokenBalance).where(TokenBalance.wallet_id == wallet_id)
        ).all()

    async def update_balance(self, wallet_id: int, chain_id: int, token_address: str, balance: float) -> TokenBalance:
        """Update a specific token balance for a wallet"""
        record = self.session.execute(
            select(TokenBalance).where(
                TokenBalance.wallet_id == wallet_id,
                TokenBalance.chain_id == chain_id,
                TokenBalance.token_address == token_address
            )
        ).first()

        if record:
            record.balance = balance
        else:
            # Need to get token symbol (mocked here, would usually query RPC)
            symbol = "ETH" if token_address == "native" else "ERC20"
            record = TokenBalance(
                wallet_id=wallet_id,
                chain_id=chain_id,
                token_address=token_address,
                token_symbol=symbol,
                balance=balance
            )
            self.session.add(record)
            
        self.session.commit()
        self.session.refresh(record)
        return record

    async def submit_transaction(self, wallet_id: int, request: TransactionRequest) -> WalletTransaction:
        """Submit a transaction from a wallet"""
        wallet = self.session.get(AgentWallet, wallet_id)
        if not wallet or not wallet.is_active:
            raise ValueError("Wallet not found or inactive")

        # In a real implementation, this would:
        # 1. Fetch the network config
        # 2. Construct the transaction payload
        # 3. Sign it using the KMS/HSM
        # 4. Broadcast via RPC
        
        tx = WalletTransaction(
            wallet_id=wallet.id,
            chain_id=request.chain_id,
            to_address=request.to_address,
            value=request.value,
            data=request.data,
            gas_limit=request.gas_limit,
            gas_price=request.gas_price,
            status=TransactionStatus.PENDING
        )
        
        self.session.add(tx)
        self.session.commit()
        self.session.refresh(tx)
        
        # Mocking the blockchain submission for now
        # tx_hash = await self.contract_service.broadcast_raw_tx(...)
        tx.tx_hash = "0x" + secrets.token_hex(32)
        tx.status = TransactionStatus.SUBMITTED
        
        self.session.commit()
        self.session.refresh(tx)
        
        logger.info(f"Submitted transaction {tx.tx_hash} from wallet {wallet.address}")
        return tx
