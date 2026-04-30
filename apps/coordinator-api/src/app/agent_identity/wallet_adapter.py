"""
Multi-Chain Wallet Adapter Implementation
Provides blockchain-agnostic wallet interface for agents
"""

from abc import ABC, abstractmethod
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any

from aitbc import get_logger

logger = get_logger(__name__)

from sqlmodel import Session, select

from ..domain.agent_identity import AgentWallet, AgentWalletUpdate, ChainType


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
        # This would deploy the AgentWallet contract for the agent
        # For now, return a mock implementation
        return {
            "chain_id": self.chain_id,
            "chain_type": self.chain_type,
            "wallet_address": f"0x{'0' * 40}",  # Mock address
            "contract_address": f"0x{'1' * 40}",  # Mock contract
            "transaction_hash": f"0x{'2' * 64}",  # Mock tx hash
            "created_at": datetime.now(datetime.UTC).isoformat(),
        }

    async def get_balance(self, wallet_address: str) -> Decimal:
        """Get ETH balance for wallet"""
        # Mock implementation - would call eth_getBalance
        return Decimal("1.5")  # Mock balance

    async def execute_transaction(
        self, from_address: str, to_address: str, amount: Decimal, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute Ethereum transaction"""
        # Mock implementation - would call eth_sendTransaction
        return {
            "transaction_hash": f"0x{'3' * 64}",
            "from_address": from_address,
            "to_address": to_address,
            "amount": str(amount),
            "gas_used": "21000",
            "gas_price": "20000000000",
            "status": "success",
            "block_number": 12345,
            "timestamp": datetime.now(datetime.UTC).isoformat(),
        }

    async def get_transaction_history(self, wallet_address: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Get transaction history for wallet"""
        # Mock implementation - would query blockchain
        return [
            {
                "hash": f"0x{'4' * 64}",
                "from_address": wallet_address,
                "to_address": f"0x{'5' * 40}",
                "amount": "0.1",
                "gas_used": "21000",
                "block_number": 12344,
                "timestamp": datetime.now(datetime.UTC).isoformat(),
            }
        ]

    async def verify_address(self, address: str) -> bool:
        """Verify Ethereum address format"""
        try:
            # Basic Ethereum address validation
            if not address.startswith("0x") or len(address) != 42:
                return False
            int(address, 16)  # Check if it's a valid hex
            return True
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

        # Initialize default chain configurations
        self._initialize_chain_configs()

    def _initialize_chain_configs(self):
        """Initialize default blockchain configurations"""
        self.chain_configs = {
            1: {  # Ethereum Mainnet
                "chain_type": ChainType.ETHEREUM,
                "rpc_url": "https://mainnet.infura.io/v3/YOUR_PROJECT_ID",
                "name": "Ethereum Mainnet",
            },
            137: {  # Polygon Mainnet
                "chain_type": ChainType.POLYGON,
                "rpc_url": "https://polygon-rpc.com",
                "name": "Polygon Mainnet",
            },
            56: {  # BSC Mainnet
                "chain_type": ChainType.BSC,
                "rpc_url": "https://bsc-dataseed1.binance.org",
                "name": "BSC Mainnet",
            },
            42161: {  # Arbitrum One
                "chain_type": ChainType.ARBITRUM,
                "rpc_url": "https://arb1.arbitrum.io/rpc",
                "name": "Arbitrum One",
            },
            10: {"chain_type": ChainType.OPTIMISM, "rpc_url": "https://mainnet.optimism.io", "name": "Optimism"},  # Optimism
            43114: {  # Avalanche C-Chain
                "chain_type": ChainType.AVALANCHE,
                "rpc_url": "https://api.avax.network/ext/bc/C/rpc",
                "name": "Avalanche C-Chain",
            },
        }

    def get_adapter(self, chain_id: int) -> WalletAdapter:
        """Get or create wallet adapter for a specific chain"""
        if chain_id not in self.adapters:
            config = self.chain_configs.get(chain_id)
            if not config:
                raise ValueError(f"Unsupported chain ID: {chain_id}")

            # Create appropriate adapter based on chain type
            if config["chain_type"] in [ChainType.ETHEREUM, ChainType.ARBITRUM, ChainType.OPTIMISM]:
                self.adapters[chain_id] = EthereumWalletAdapter(chain_id, config["rpc_url"])
            elif config["chain_type"] == ChainType.POLYGON:
                self.adapters[chain_id] = PolygonWalletAdapter(chain_id, config["rpc_url"])
            elif config["chain_type"] == ChainType.BSC:
                self.adapters[chain_id] = BSCWalletAdapter(chain_id, config["rpc_url"])
            else:
                raise ValueError(f"Unsupported chain type: {config['chain_type']}")

        return self.adapters[chain_id]

    async def create_agent_wallet(self, agent_id: str, chain_id: int, owner_address: str) -> AgentWallet:
        """Create an agent wallet on a specific blockchain"""

        adapter = self.get_adapter(chain_id)

        # Create wallet on blockchain
        wallet_result = await adapter.create_wallet(owner_address)

        # Create wallet record in database
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

        logger.info(f"Created agent wallet: {wallet.id} on chain {chain_id}")
        return wallet

    async def get_wallet_balance(self, agent_id: str, chain_id: int) -> Decimal:
        """Get wallet balance for an agent on a specific chain"""

        # Get wallet from database
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active
        )
        wallet = self.session.exec(stmt).first()

        if not wallet:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")

        # Get balance from blockchain
        adapter = self.get_adapter(chain_id)
        balance = await adapter.get_balance(wallet.chain_address)

        # Update wallet in database
        wallet.balance = float(balance)
        self.session.commit()

        return balance

    async def execute_wallet_transaction(
        self, agent_id: str, chain_id: int, to_address: str, amount: Decimal, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a transaction from agent wallet"""

        # Get wallet from database
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active
        )
        wallet = self.session.exec(stmt).first()

        if not wallet:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")

        # Check spending limit
        if wallet.spending_limit > 0 and (wallet.total_spent + float(amount)) > wallet.spending_limit:
            raise ValueError("Transaction amount exceeds spending limit")

        # Execute transaction on blockchain
        adapter = self.get_adapter(chain_id)
        tx_result = await adapter.execute_transaction(wallet.chain_address, to_address, amount, data)

        # Update wallet in database
        wallet.total_spent += float(amount)
        wallet.last_transaction = datetime.now(datetime.UTC)
        wallet.transaction_count += 1
        self.session.commit()

        logger.info(f"Executed wallet transaction: {tx_result['transaction_hash']}")
        return tx_result

    async def get_wallet_transaction_history(
        self, agent_id: str, chain_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Get transaction history for agent wallet"""

        # Get wallet from database
        stmt = select(AgentWallet).where(
            AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id, AgentWallet.is_active
        )
        wallet = self.session.exec(stmt).first()

        if not wallet:
            raise ValueError(f"Active wallet not found for agent {agent_id} on chain {chain_id}")

        # Get transaction history from blockchain
        adapter = self.get_adapter(chain_id)
        history = await adapter.get_transaction_history(wallet.chain_address, limit, offset)

        return history

    async def update_agent_wallet(self, agent_id: str, chain_id: int, request: AgentWalletUpdate) -> AgentWallet:
        """Update agent wallet settings"""

        # Get wallet from database
        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id)
        wallet = self.session.exec(stmt).first()

        if not wallet:
            raise ValueError(f"Wallet not found for agent {agent_id} on chain {chain_id}")

        # Update fields
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(wallet, field):
                setattr(wallet, field, value)

        wallet.updated_at = datetime.now(datetime.UTC)

        self.session.commit()
        self.session.refresh(wallet)

        logger.info(f"Updated agent wallet: {wallet.id}")
        return wallet

    async def get_all_agent_wallets(self, agent_id: str) -> list[AgentWallet]:
        """Get all wallets for an agent across all chains"""

        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id)
        return self.session.exec(stmt).all()

    async def deactivate_wallet(self, agent_id: str, chain_id: int) -> bool:
        """Deactivate an agent wallet"""

        # Get wallet from database
        stmt = select(AgentWallet).where(AgentWallet.agent_id == agent_id, AgentWallet.chain_id == chain_id)
        wallet = self.session.exec(stmt).first()

        if not wallet:
            raise ValueError(f"Wallet not found for agent {agent_id} on chain {chain_id}")

        # Deactivate wallet
        wallet.is_active = False
        wallet.updated_at = datetime.now(datetime.UTC)

        self.session.commit()

        logger.info(f"Deactivated agent wallet: {wallet.id}")
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
            # Get current balance
            try:
                balance = await self.get_wallet_balance(agent_id, wallet.chain_id)
                total_balance += float(balance)
            except Exception as e:
                logger.warning(f"Failed to get balance for wallet {wallet.id}: {e}")
                balance = 0.0

            total_spent += wallet.total_spent
            total_transactions += wallet.transaction_count

            if wallet.is_active:
                active_wallets += 1

            # Chain breakdown
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
            logger.error(f"Error verifying address {address} on chain {chain_id}: {e}")
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

        return sync_results

    def add_chain_config(self, chain_id: int, chain_type: ChainType, rpc_url: str, name: str):
        """Add a new blockchain configuration"""

        self.chain_configs[chain_id] = {"chain_type": chain_type, "rpc_url": rpc_url, "name": name}

        # Remove cached adapter if it exists
        if chain_id in self.adapters:
            del self.adapters[chain_id]

        logger.info(f"Added chain config: {chain_id} - {name}")

    def get_supported_chains(self) -> list[dict[str, Any]]:
        """Get list of supported blockchains"""

        return [
            {"chain_id": chain_id, "chain_type": config["chain_type"], "name": config["name"], "rpc_url": config["rpc_url"]}
            for chain_id, config in self.chain_configs.items()
        ]
