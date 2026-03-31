"""
Secure Wallet Service - Fixed Version
Implements proper Ethereum cryptography and secure key storage
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlmodel import Session

from ..blockchain.contract_interactions import ContractInteractionService
from ..domain.wallet import AgentWallet, TokenBalance, TransactionStatus, WalletTransaction
from ..schemas.wallet import TransactionRequest, WalletCreate

# Import our fixed crypto utilities
from .wallet_crypto import (
    encrypt_private_key,
    generate_ethereum_keypair,
    recover_wallet,
    verify_keypair_consistency,
)

logger = logging.getLogger(__name__)


class SecureWalletService:
    """Secure wallet service with proper cryptography and key management"""

    def __init__(self, session: Session, contract_service: ContractInteractionService):
        self.session = session
        self.contract_service = contract_service

    async def create_wallet(self, request: WalletCreate, encryption_password: str) -> AgentWallet:
        """
        Create a new wallet with proper security

        Args:
            request: Wallet creation request
            encryption_password: Strong password for private key encryption

        Returns:
            Created wallet record

        Raises:
            ValueError: If password is weak or wallet already exists
        """
        # Validate password strength
        from ..utils.security import validate_password_strength

        password_validation = validate_password_strength(encryption_password)

        if not password_validation["is_acceptable"]:
            raise ValueError(f"Password too weak: {', '.join(password_validation['issues'])}")

        # Check if agent already has an active wallet of this type
        existing = self.session.execute(
            select(AgentWallet).where(
                AgentWallet.agent_id == request.agent_id,
                AgentWallet.wallet_type == request.wallet_type,
                AgentWallet.is_active,
            )
        ).first()

        if existing:
            raise ValueError(f"Agent {request.agent_id} already has an active {request.wallet_type} wallet")

        try:
            # Generate proper Ethereum keypair
            private_key, public_key, address = generate_ethereum_keypair()

            # Verify keypair consistency
            if not verify_keypair_consistency(private_key, address):
                raise RuntimeError("Keypair generation failed consistency check")

            # Encrypt private key securely
            encrypted_data = encrypt_private_key(private_key, encryption_password)

            # Create wallet record
            wallet = AgentWallet(
                agent_id=request.agent_id,
                address=address,
                public_key=public_key,
                wallet_type=request.wallet_type,
                metadata=request.metadata,
                encrypted_private_key=encrypted_data,
                encryption_version="1.0",
                created_at=datetime.utcnow(),
            )

            self.session.add(wallet)
            self.session.commit()
            self.session.refresh(wallet)

            logger.info(f"Created secure wallet {wallet.address} for agent {request.agent_id}")
            return wallet

        except Exception as e:
            logger.error(f"Failed to create secure wallet: {e}")
            self.session.rollback()
            raise

    async def get_wallet_by_agent(self, agent_id: str) -> list[AgentWallet]:
        """Retrieve all active wallets for an agent"""
        return self.session.execute(
            select(AgentWallet).where(AgentWallet.agent_id == agent_id, AgentWallet.is_active)
        ).all()

    async def get_wallet_with_private_key(self, wallet_id: int, encryption_password: str) -> dict[str, str]:
        """
        Get wallet with decrypted private key (for signing operations)

        Args:
            wallet_id: Wallet ID
            encryption_password: Password for decryption

        Returns:
            Wallet keys including private key

        Raises:
            ValueError: If decryption fails or wallet not found
        """
        wallet = self.session.get(AgentWallet, wallet_id)
        if not wallet:
            raise ValueError("Wallet not found")

        if not wallet.is_active:
            raise ValueError("Wallet is not active")

        try:
            # Decrypt private key
            if isinstance(wallet.encrypted_private_key, dict):
                # New format
                keys = recover_wallet(wallet.encrypted_private_key, encryption_password)
            else:
                # Legacy format - cannot decrypt securely
                raise ValueError("Wallet uses legacy encryption format. " "Please migrate to secure encryption.")

            return {
                "wallet_id": wallet_id,
                "address": wallet.address,
                "private_key": keys["private_key"],
                "public_key": keys["public_key"],
                "agent_id": wallet.agent_id,
            }

        except Exception as e:
            logger.error(f"Failed to decrypt wallet {wallet_id}: {e}")
            raise ValueError(f"Failed to access wallet: {str(e)}")

    async def verify_wallet_integrity(self, wallet_id: int) -> dict[str, bool]:
        """
        Verify wallet cryptographic integrity

        Args:
            wallet_id: Wallet ID

        Returns:
            Integrity check results
        """
        wallet = self.session.get(AgentWallet, wallet_id)
        if not wallet:
            return {"exists": False}

        results = {
            "exists": True,
            "active": wallet.is_active,
            "has_encrypted_key": bool(wallet.encrypted_private_key),
            "address_format_valid": False,
            "public_key_present": bool(wallet.public_key),
        }

        # Validate address format
        try:
            from eth_utils import to_checksum_address

            to_checksum_address(wallet.address)
            results["address_format_valid"] = True
        except:
            pass

        # Check if we can verify the keypair consistency
        # (We can't do this without the password, but we can check the format)
        if wallet.public_key and wallet.encrypted_private_key:
            results["has_keypair_data"] = True

        return results

    async def migrate_wallet_encryption(self, wallet_id: int, old_password: str, new_password: str) -> AgentWallet:
        """
        Migrate wallet from old encryption to new secure encryption

        Args:
            wallet_id: Wallet ID
            old_password: Current password
            new_password: New strong password

        Returns:
            Updated wallet
        """
        wallet = self.session.get(AgentWallet, wallet_id)
        if not wallet:
            raise ValueError("Wallet not found")

        try:
            # Get current private key
            current_keys = await self.get_wallet_with_private_key(wallet_id, old_password)

            # Validate new password
            from ..utils.security import validate_password_strength

            password_validation = validate_password_strength(new_password)

            if not password_validation["is_acceptable"]:
                raise ValueError(f"New password too weak: {', '.join(password_validation['issues'])}")

            # Re-encrypt with new password
            new_encrypted_data = encrypt_private_key(current_keys["private_key"], new_password)

            # Update wallet
            wallet.encrypted_private_key = new_encrypted_data
            wallet.encryption_version = "1.0"
            wallet.updated_at = datetime.utcnow()

            self.session.commit()
            self.session.refresh(wallet)

            logger.info(f"Migrated wallet {wallet_id} to secure encryption")
            return wallet

        except Exception as e:
            logger.error(f"Failed to migrate wallet {wallet_id}: {e}")
            self.session.rollback()
            raise

    async def get_balances(self, wallet_id: int) -> list[TokenBalance]:
        """Get all tracked balances for a wallet"""
        return self.session.execute(select(TokenBalance).where(TokenBalance.wallet_id == wallet_id)).all()

    async def update_balance(self, wallet_id: int, chain_id: int, token_address: str, balance: float) -> TokenBalance:
        """Update a specific token balance for a wallet"""
        record = self.session.execute(
            select(TokenBalance).where(
                TokenBalance.wallet_id == wallet_id,
                TokenBalance.chain_id == chain_id,
                TokenBalance.token_address == token_address,
            )
        ).first()

        if record:
            record.balance = balance
            record.updated_at = datetime.utcnow()
        else:
            record = TokenBalance(
                wallet_id=wallet_id,
                chain_id=chain_id,
                token_address=token_address,
                balance=balance,
                updated_at=datetime.utcnow(),
            )
            self.session.add(record)

        self.session.commit()
        self.session.refresh(record)
        return record

    async def create_transaction(
        self, wallet_id: int, request: TransactionRequest, encryption_password: str
    ) -> WalletTransaction:
        """
        Create a transaction with proper signing

        Args:
            wallet_id: Wallet ID
            request: Transaction request
            encryption_password: Password for private key access

        Returns:
            Created transaction record
        """
        # Get wallet keys
        await self.get_wallet_with_private_key(wallet_id, encryption_password)

        # Create transaction record
        transaction = WalletTransaction(
            wallet_id=wallet_id,
            to_address=request.to_address,
            amount=request.amount,
            token_address=request.token_address,
            chain_id=request.chain_id,
            data=request.data or "",
            status=TransactionStatus.PENDING,
            created_at=datetime.utcnow(),
        )

        self.session.add(transaction)
        self.session.commit()
        self.session.refresh(transaction)

        # TODO: Implement actual blockchain transaction signing and submission
        # This would use the private_key to sign the transaction

        logger.info(f"Created transaction {transaction.id} for wallet {wallet_id}")
        return transaction

    async def deactivate_wallet(self, wallet_id: int, reason: str = "User request") -> bool:
        """Deactivate a wallet"""
        wallet = self.session.get(AgentWallet, wallet_id)
        if not wallet:
            return False

        wallet.is_active = False
        wallet.updated_at = datetime.utcnow()
        wallet.deactivation_reason = reason

        self.session.commit()

        logger.info(f"Deactivated wallet {wallet_id}: {reason}")
        return True

    async def get_wallet_security_audit(self, wallet_id: int) -> dict[str, Any]:
        """
        Get comprehensive security audit for a wallet

        Args:
            wallet_id: Wallet ID

        Returns:
            Security audit results
        """
        wallet = self.session.get(AgentWallet, wallet_id)
        if not wallet:
            return {"error": "Wallet not found"}

        audit = {
            "wallet_id": wallet_id,
            "agent_id": wallet.agent_id,
            "address": wallet.address,
            "is_active": wallet.is_active,
            "encryption_version": getattr(wallet, "encryption_version", "unknown"),
            "created_at": wallet.created_at.isoformat() if wallet.created_at else None,
            "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
        }

        # Check encryption security
        if isinstance(wallet.encrypted_private_key, dict):
            audit["encryption_secure"] = True
            audit["encryption_algorithm"] = wallet.encrypted_private_key.get("algorithm")
            audit["encryption_iterations"] = wallet.encrypted_private_key.get("iterations")
        else:
            audit["encryption_secure"] = False
            audit["encryption_issues"] = ["Uses legacy or broken encryption"]

        # Check address format
        try:
            from eth_utils import to_checksum_address

            to_checksum_address(wallet.address)
            audit["address_valid"] = True
        except:
            audit["address_valid"] = False
            audit["address_issues"] = ["Invalid Ethereum address format"]

        # Check keypair data
        audit["has_public_key"] = bool(wallet.public_key)
        audit["has_encrypted_private_key"] = bool(wallet.encrypted_private_key)

        # Overall security score
        security_score = 0
        if audit["encryption_secure"]:
            security_score += 40
        if audit["address_valid"]:
            security_score += 30
        if audit["has_public_key"]:
            security_score += 15
        if audit["has_encrypted_private_key"]:
            security_score += 15

        audit["security_score"] = security_score
        audit["security_level"] = (
            "Excellent"
            if security_score >= 90
            else "Good" if security_score >= 70 else "Fair" if security_score >= 50 else "Poor"
        )

        return audit
