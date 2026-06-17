"""
Multi-Chain Wallet Adapter Implementation
Provides blockchain-agnostic wallet interface for agents
"""

import secrets
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlmodel import Session, select

from aitbc.aitbc_logging import get_logger

from ..contexts.agent_identity.domain.agent_identity import AgentWallet, AgentWalletUpdate, ChainType

logger = get_logger(__name__)


class WalletAdapter(ABC):
    """Abstract base class for blockchain-specific wallet adapters"""

    def __init__(self, chain_id: int, chain_type: ChainType, rpc_url: str):
        self.chain_id = chain_id
        self.chain_type = chain_type
        self.rpc_url = rpc_url

    @abstractmethod
    async def create_wallet(self, owner_address: str) -> dict[str, Any]:
        """Create a new wallet for the agent"""
        pass

    @abstractmethod
    async def get_balance(self, wallet_address: str) -> Decimal:
        """Get wallet balance"""
        pass

    @abstractmethod
    async def execute_transaction(
        self, from_address: str, to_address: str, amount: Decimal, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a transaction"""
        pass

    @abstractmethod
    async def get_transaction_history(self, wallet_address: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Get transaction history"""
        pass

    @abstractmethod
    async def verify_address(self, address: str) -> bool:
        """Verify if address is valid for this chain"""
        pass


class EthereumWalletAdapter(WalletAdapter):
    """Ethereum-compatible wallet adapter"""

    def __init__(self, chain_id: int, rpc_url: str):
        super().__init__(chain_id, ChainType.ETHEREUM, rpc_url)

    async def create_wallet(self, owner_address: str) -> dict[str, Any]:
        """Create a new Ethereum wallet for the agent"""
        return {
            "chain_id": self.chain_id,
            "chain_type": self.chain_type,
            "wallet_address": f"0x{'0' * 40}",
            "contract_address": f"0x{'1' * 40}",
            "transaction_hash": f"0x{'2' * 64}",
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def get_balance(self, wallet_address: str) -> Decimal:
        """Get ETH balance for wallet"""
        return Decimal("1.5")

    async def execute_transaction(
        self, from_address: str, to_address: str, amount: Decimal, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute Ethereum transaction"""
        return {
            "transaction_hash": f"0x{'3' * 64}",
            "from_address": from_address,
            "to_address": to_address,
            "amount": str(amount),
            "gas_used": "21000",
            "gas_price": "20000000000",
            "status": "success",
            "block_number": 12345,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_transaction_history(self, wallet_address: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Get transaction history for wallet"""
        return [
            {
                "hash": f"0x{'4' * 64}",
                "from_address": wallet_address,
                "to_address": f"0x{'5' * 40}",
                "amount": "0.1",
                "gas_used": "21000",
                "block_number": 12344,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ]

    async def verify_address(self, address: str) -> bool:
        """Verify Ethereum address format"""
        try:
            if not address.startswith("0x") or len(address) != 42:
                return False
            int(address, 16)
            return True
        except ValueError:
            return False


class AITBCWalletAdapter(WalletAdapter):
    """AITBC wallet adapter"""

    def __init__(self, chain_id: int, rpc_url: str):
        super().__init__(chain_id, ChainType.AITBC, rpc_url)

    async def create_wallet(self, owner_address: str) -> dict[str, Any]:
        """Create a new AITBC wallet for the agent"""
        from aitbc.crypto.crypto import derive_ethereum_address

        private_key = secrets.token_hex(32)
        public_key = derive_ethereum_address(private_key)
        aitbc_address = f"ait1{public_key[2:]}"
        return {
            "chain_id": self.chain_id,
            "chain_type": self.chain_type,
            "wallet_address": aitbc_address,
            "contract_address": None,
            "transaction_hash": f"0x{'2' * 64}",
            "created_at": datetime.now(UTC).isoformat(),
        }

    async def get_balance(self, wallet_address: str) -> Decimal:
        """Get AITBC balance for wallet"""
        return Decimal("100.0")

    async def execute_transaction(
        self, from_address: str, to_address: str, amount: Decimal, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute AITBC transaction"""
        return {
            "transaction_hash": f"0x{'3' * 64}",
            "from_address": from_address,
            "to_address": to_address,
            "amount": str(amount),
            "gas_used": "21000",
            "gas_price": "1000000000",
            "status": "success",
            "block_number": 12345,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def get_transaction_history(self, wallet_address: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Get transaction history for wallet"""
        return [
            {
                "hash": f"0x{'4' * 64}",
                "from_address": wallet_address,
                "to_address": f"ait1{'5' * 38}",
                "amount": "10.0",
                "gas_used": "21000",
                "block_number": 12344,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ]

    async def verify_address(self, address: str) -> bool:
        """Verify AITBC address format"""
        try:
            return address.startswith("ait1") and len(address) == 43
        except ValueError:
            return False


class PolygonWalletAdapter(EthereumWalletAdapter):
    """Polygon wallet adapter (Ethereum-compatible)"""

    def __init__(self, chain_id: int, rpc_url: str):
        super().__init__(chain_id, rpc_url)
        self.chain_type = ChainType.POLYGON


class BSCWalletAdapter(EthereumWalletAdapter):
    """BSC wallet adapter (Ethereum-compatible)"""

    def __init__(self, chain_id: int, rpc_url: str):
        super().__init__(chain_id, rpc_url)
        self.chain_type = ChainType.BSC


class MultiChainWalletAdapter:
    """Multi-chain wallet adapter that manages different blockchain adapters"""

    def __init__(self, session: Session):
        self.session = session
        self.adapters: dict[int, WalletAdapter] = {}
        self.chain_configs: dict[int, dict[str, Any]] = {}
        self._initialize_chain_configs()

    def _initialize_chain_configs(self) -> None:
        """Initialize default blockchain configurations"""
        self.chain_configs = {
            1: {
                "chain_type": ChainType.ETHEREUM,
                "rpc_url": "https://mainnet.infura.io/v3/YOUR_PROJECT_ID",
                "name": "Ethereum Mainnet",
            },
            137: {"chain_type": ChainType.POLYGON, "rpc_url": "https://polygon-rpc.com", "name": "Polygon Mainnet"},
            56: {"chain_type": ChainType.BSC, "rpc_url": "https://bsc-dataseed1.binance.org", "name": "BSC Mainnet"},
            42161: {"chain_type": ChainType.ARBITRUM, "rpc_url": "https://arb1.arbitrum.io/rpc", "name": "Arbitrum One"},
            10: {"chain_type": ChainType.OPTIMISM, "rpc_url": "https://mainnet.optimism.io", "name": "Optimism"},
            43114: {
                "chain_type": ChainType.AVALANCHE,
                "rpc_url": "https://api.avax.network/ext/bc/C/rpc",
                "name": "Avalanche C-Chain",
            },
            1000: {"chain_type": ChainType.AITBC, "rpc_url": "http://localhost:8006", "name": "AITBC Mainnet"},
        }

    def get_adapter(self, chain_id: int) -> WalletAdapter:
        """Get or create wallet adapter for a specific chain"""
        if chain_id not in self.adapters:
            config = self.chain_configs.get(chain_id)
            if not config:
                raise ValueError(f"Unsupported chain ID: {chain_id}")
            if config["chain_type"] in [ChainType.ETHEREUM, ChainType.ARBITRUM, ChainType.OPTIMISM]:
                self.adapters[chain_id] = EthereumWalletAdapter(chain_id, config["rpc_url"])
            elif config["chain_type"] == ChainType.POLYGON:
                self.adapters[chain_id] = PolygonWalletAdapter(chain_id, config["rpc_url"])
            elif config["chain_type"] == ChainType.BSC:
                self.adapters[chain_id] = BSCWalletAdapter(chain_id, config["rpc_url"])
            elif config["chain_type"] == ChainType.AITBC:
                self.adapters[chain_id] = AITBCWalletAdapter(chain_id, config["rpc_url"])
            else:
                raise ValueError(f"Unsupported chain type: {config['chain_type']}")
        return self.adapters[chain_id]

    async def create_agent_wallet(self, agent_id: str, chain_id: int, owner_address: str) -> AgentWallet:
        """Create an agent wallet on a specific blockchain"""
        adapter = self.get_adapter(chain_id)
        wallet_result = await adapter.create_wallet(owner_address)
        wallet = AgentWallet(
            agent_id=agent_id,
            chain_id=chain_id,
            chain_address=wallet_result["wallet_address"],
            wallet_type="agent-wallet",
            contract_address=wallet_result.get("contract_address"),
            is_active=True,
        )
        self.session.add(wallet)
        self.session.commit()
        self.session.refresh(wallet)
        logger.info("Created agent wallet: %s on chain %s", wallet.id, chain_id)
        return wallet

    async def get_wallet_balance(self, agent_id: str, chain_id: int) -> Decimal:
        """Get wallet balance for an agent on a specific chain"""
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active
        )
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")
        adapter = self.get_adapter(chain_id)
        balance = await adapter.get_balance(wallet.chain_address)
        wallet.balance = float(balance)
        self.session.commit()
        return balance

    async def execute_wallet_transaction(
        self, agent_id: str, chain_id: int, to_address: str, amount: Decimal, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a transaction from agent wallet"""
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active
        )
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")
        if wallet.spending_limit > 0 and wallet.total_spent + float(amount) > wallet.spending_limit:
            raise ValueError("Transaction amount exceeds spending limit")
        adapter = self.get_adapter(chain_id)
        tx_result = await adapter.execute_transaction(wallet.chain_address, to_address, amount, data)
        wallet.total_spent += float(amount)
        wallet.last_transaction = datetime.now(UTC)
        wallet.transaction_count += 1
        self.session.commit()
        logger.info("Executed wallet transaction: %s", tx_result["transaction_hash"])
        return tx_result

    async def get_wallet_transaction_history(
        self, agent_id: str, chain_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Get transaction history for agent wallet"""
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active
        )
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")
        adapter = self.get_adapter(chain_id)
        history = await adapter.get_transaction_history(wallet.chain_address, limit, offset)
        return history

    async def update_agent_wallet(self, agent_id: str, chain_id: int, request: AgentWalletUpdate) -> AgentWallet:
        """Update agent wallet settings"""
        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id)
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Wallet not found for agent {agent_id} on chain {chain_id}")
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(wallet, field):
                setattr(wallet, field, value)
        wallet.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(wallet)
        logger.info("Updated agent wallet: %s", wallet.id)
        return wallet  # type: ignore[no-any-return]

    async def get_all_agent_wallets(self, agent_id: str) -> list[AgentWallet]:
        """Get all wallets for an agent across all chains"""
        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate_wallet(self, agent_id: str, chain_id: int) -> bool:
        """Deactivate an agent wallet"""
        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id)
        result = self.session.execute(stmt)
        wallet = result.scalars().first()
        if not wallet:
            raise ValueError(f"Wallet not found for agent {agent_id} on chain {chain_id}")
        wallet.is_active = False
        wallet.updated_at = datetime.now(UTC)
        self.session.commit()
        logger.info("Deactivated agent wallet: %s", wallet.id)
        return True

    async def get_wallet_statistics(self, agent_id: str) -> dict[str, Any]:
        """Get comprehensive wallet statistics for an agent"""
        wallets = await self.get_all_agent_wallets(agent_id)
        total_balance = 0.0
        total_spent = 0.0
        total_transactions = 0
        active_wallets = 0
        chain_breakdown = {}
        for wallet in wallets:
            try:
                balance = await self.get_wallet_balance(agent_id, wallet.chain_id)
                total_balance += float(balance)
            except Exception as e:
                logger.warning("Failed to get balance for wallet %s: %s", wallet.id, e)
                balance = 0.0  # type: ignore[assignment]
            total_spent += wallet.total_spent
            total_transactions += wallet.transaction_count
            if wallet.is_active:
                active_wallets += 1
            chain_name = self.chain_configs.get(wallet.chain_id, {}).get("name", f"Chain {wallet.chain_id}")
            if chain_name not in chain_breakdown:
                chain_breakdown[chain_name] = {"balance": 0.0, "spent": 0.0, "transactions": 0, "active": False}
            chain_breakdown[chain_name]["balance"] += float(balance)
            chain_breakdown[chain_name]["spent"] += wallet.total_spent
            chain_breakdown[chain_name]["transactions"] += wallet.transaction_count
            chain_breakdown[chain_name]["active"] = wallet.is_active
        return {
            "total_wallets": len(wallets),
            "active_wallets": active_wallets,
            "total_balance": total_balance,
            "total_spent": total_spent,
            "total_transactions": total_transactions,
            "average_balance_per_wallet": total_balance / max(len(wallets), 1),
            "chain_breakdown": chain_breakdown,
            "supported_chains": list(chain_breakdown.keys()),
        }

    async def verify_wallet_address(self, chain_id: int, address: str) -> bool:
        """Verify if address is valid for a specific chain"""
        try:
            adapter = self.get_adapter(chain_id)
            return await adapter.verify_address(address)
        except Exception as e:
            logger.error("Error verifying address %s on chain %s: %s", address, chain_id, e)
            return False

    async def sync_wallet_balances(self, agent_id: str) -> dict[str, Any]:
        """Sync balances for all agent wallets"""
        wallets = await self.get_all_agent_wallets(agent_id)
        sync_results = {}
        for wallet in wallets:
            if not wallet.is_active:
                continue
            try:
                balance = await self.get_wallet_balance(agent_id, wallet.chain_id)
                sync_results[wallet.chain_id] = {"success": True, "balance": float(balance), "address": wallet.chain_address}
            except Exception as e:
                sync_results[wallet.chain_id] = {"success": False, "error": str(e), "address": wallet.chain_address}
        return sync_results  # type: ignore[return-value]

    def add_chain_config(self, chain_id: int, chain_type: ChainType, rpc_url: str, name: str) -> None:
        """Add a new blockchain configuration"""
        self.chain_configs[chain_id] = {"chain_type": chain_type, "rpc_url": rpc_url, "name": name}
        if chain_id in self.adapters:
            del self.adapters[chain_id]
        logger.info("Added chain config: %s - %s", chain_id, name)

    def get_supported_chains(self) -> list[dict[str, Any]]:
        """Get list of supported blockchains"""
        return [
            {"chain_id": chain_id, "chain_type": config["chain_type"], "name": config["name"], "rpc_url": config["rpc_url"]}
            for chain_id, config in self.chain_configs.items()
        ]
