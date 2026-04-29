"""
Smart contract integration for AITBC Agent SDK
Provides methods for interacting with deployed smart contracts
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from web3 import Web3
from web3.contract import Contract

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import NetworkError

logger = get_logger(__name__)


@dataclass
class ContractConfig:
    """Configuration for smart contract addresses"""
    payment_processor: str
    agent_marketplace: str
    staking_contract: str
    treasury_manager: str
    network: str = "mainnet"
    rpc_url: Optional[str] = None

    @classmethod
    def from_env(cls, network: str = "mainnet") -> "ContractConfig":
        """Load contract configuration from environment variables"""
        return cls(
            payment_processor=getenv(f"{network.upper()}_PAYMENT_PROCESSOR_ADDRESS", ""),
            agent_marketplace=getenv(f"{network.upper()}_AGENT_MARKETPLACE_ADDRESS", ""),
            staking_contract=getenv(f"{network.upper()}_STAKING_CONTRACT_ADDRESS", ""),
            treasury_manager=getenv(f"{network.upper()}_TREASURY_MANAGER_ADDRESS", ""),
            network=network,
            rpc_url=getenv(f"{network.upper()}_RPC_URL", ""),
        )


class ContractClient:
    """Web3 client for smart contract interactions"""

    def __init__(self, config: ContractConfig, private_key: Optional[str] = None):
        self.config = config
        self.private_key = private_key
        self.w3: Optional[Web3] = None
        self.contracts: Dict[str, Contract] = {}
        self._connect()

    def _connect(self) -> None:
        """Connect to blockchain network"""
        if not self.config.rpc_url:
            raise ValueError("RPC URL not configured")

        self.w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
        
        if not self.w3.is_connected():
            raise NetworkError("Failed to connect to blockchain")

        logger.info(f"Connected to {self.config.network} at {self.config.rpc_url}")

        # Load contract ABIs and initialize contracts
        self._load_contracts()

    def _load_contracts(self) -> None:
        """Load contract ABIs and initialize contract instances"""
        # In a real implementation, these would be loaded from compiled artifacts
        # For now, we'll use placeholder ABIs
        payment_processor_abi = self._load_abi("PaymentProcessor")
        agent_marketplace_abi = self._load_abi("AgentMarketplace")
        staking_contract_abi = self._load_abi("StakingContract")

        if self.config.payment_processor:
            self.contracts["payment_processor"] = self.w3.eth.contract(
                address=self.config.payment_processor,
                abi=payment_processor_abi
            )

        if self.config.agent_marketplace:
            self.contracts["agent_marketplace"] = self.w3.eth.contract(
                address=self.config.agent_marketplace,
                abi=agent_marketplace_abi
            )

        if self.config.staking_contract:
            self.contracts["staking_contract"] = self.w3.eth.contract(
                address=self.config.staking_contract,
                abi=staking_contract_abi
            )

        logger.info(f"Loaded {len(self.contracts)} contracts")

    def _load_abi(self, contract_name: str) -> List[Dict]:
        """Load contract ABI from artifacts"""
        # In a real implementation, this would load from compiled contract artifacts
        # For now, return a minimal ABI
        return [
            {
                "inputs": [],
                "name": "getBalance",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]

    async def get_contract_balance(self, contract_name: str, address: str) -> int:
        """Get balance from a contract"""
        contract = self.contracts.get(contract_name)
        if not contract:
            raise ValueError(f"Contract {contract_name} not loaded")

        try:
            balance = contract.functions.getBalance(address).call()
            return balance
        except Exception as e:
            logger.error(f"Error getting balance from {contract_name}: {e}")
            raise

    async def send_transaction(
        self,
        contract_name: str,
        method_name: str,
        *args: Any,
        **kwargs: Any
    ) -> str:
        """Send a transaction to a contract"""
        contract = self.contracts.get(contract_name)
        if not contract:
            raise ValueError(f"Contract {contract_name} not loaded")

        if not self.private_key:
            raise ValueError("Private key required for transactions")

        try:
            # Get the contract method
            contract_method = getattr(contract.functions, method_name)
            
            # Build transaction
            transaction = contract_method(*args, **kwargs).build_transaction({
                'from': self.w3.eth.account.from_key(self.private_key).address,
                'gas': kwargs.get('gas', 200000),
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(
                    self.w3.eth.account.from_key(self.private_key).address
                ),
            })

            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(transaction, self.private_key)

            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            logger.info(f"Transaction sent: {tx_hash.hex()}")
            return tx_hash.hex()

        except Exception as e:
            logger.error(f"Error sending transaction to {contract_name}.{method_name}: {e}")
            raise

    async def wait_for_transaction(self, tx_hash: str, timeout: int = 120) -> Dict:
        """Wait for a transaction to be mined"""
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            return {
                "status": "success" if receipt["status"] == 1 else "failed",
                "block_number": receipt["blockNumber"],
                "gas_used": receipt["gasUsed"],
                "transaction_hash": receipt["transactionHash"].hex(),
            }
        except Exception as e:
            logger.error(f"Error waiting for transaction {tx_hash}: {e}")
            raise


class AgentContractIntegration:
    """Smart contract integration for AITBC agents"""

    def __init__(self, contract_client: ContractClient):
        self.contract_client = contract_client
        self.agent_address: Optional[str] = None

    def set_agent_address(self, address: str) -> None:
        """Set the agent's blockchain address"""
        self.agent_address = address
        logger.info(f"Agent address set to {address}")

    async def register_on_marketplace(
        self,
        capabilities: Dict[str, Any],
        stake_amount: int = 0
    ) -> str:
        """Register agent on the marketplace contract"""
        if not self.agent_address:
            raise ValueError("Agent address not set")

        try:
            # Register agent on marketplace
            tx_hash = await self.contract_client.send_transaction(
                "agent_marketplace",
                "registerAgent",
                self.agent_address,
                json.dumps(capabilities),
                stake_amount
            )

            # Wait for confirmation
            receipt = await self.contract_client.wait_for_transaction(tx_hash)
            
            if receipt["status"] == "success":
                logger.info(f"Agent registered on marketplace: {tx_hash}")
                return tx_hash
            else:
                raise Exception(f"Transaction failed: {receipt}")

        except Exception as e:
            logger.error(f"Failed to register on marketplace: {e}")
            raise

    async def stake_tokens(self, amount: int, lock_period: int) -> str:
        """Stake tokens in the staking contract"""
        if not self.agent_address:
            raise ValueError("Agent address not set")

        try:
            # Approve staking contract to spend tokens
            approve_tx = await self.contract_client.send_transaction(
                "payment_processor",
                "approve",
                self.contract_client.config.staking_contract,
                amount
            )
            
            await self.contract_client.wait_for_transaction(approve_tx)

            # Stake tokens
            stake_tx = await self.contract_client.send_transaction(
                "staking_contract",
                "stake",
                amount,
                lock_period
            )

            receipt = await self.contract_client.wait_for_transaction(stake_tx)
            
            if receipt["status"] == "success":
                logger.info(f"Tokens staked: {stake_tx}")
                return stake_tx
            else:
                raise Exception(f"Transaction failed: {receipt}")

        except Exception as e:
            logger.error(f"Failed to stake tokens: {e}")
            raise

    async def unstake_tokens(self) -> str:
        """Unstake tokens from the staking contract"""
        if not self.agent_address:
            raise ValueError("Agent address not set")

        try:
            tx_hash = await self.contract_client.send_transaction(
                "staking_contract",
                "unstake"
            )

            receipt = await self.contract_client.wait_for_transaction(tx_hash)
            
            if receipt["status"] == "success":
                logger.info(f"Tokens unstaked: {tx_hash}")
                return tx_hash
            else:
                raise Exception(f"Transaction failed: {receipt}")

        except Exception as e:
            logger.error(f"Failed to unstake tokens: {e}")
            raise

    async def get_stake_info(self) -> Dict[str, Any]:
        """Get staking information for the agent"""
        if not self.agent_address:
            raise ValueError("Agent address not set")

        try:
            stake_info = await self.contract_client.get_contract_balance(
                "staking_contract",
                self.agent_address
            )
            
            return {
                "staked_amount": stake_info,
                "rewards": 0,  # Would be fetched from contract
                "unlock_time": 0,  # Would be fetched from contract
            }
        except Exception as e:
            logger.error(f"Failed to get stake info: {e}")
            raise

    async def submit_job_completion(
        self,
        job_id: str,
        result_hash: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Submit job completion to marketplace contract"""
        if not self.agent_address:
            raise ValueError("Agent address not set")

        try:
            tx_hash = await self.contract_client.send_transaction(
                "agent_marketplace",
                "completeJob",
                job_id,
                result_hash,
                json.dumps(metadata or {})
            )

            receipt = await self.contract_client.wait_for_transaction(tx_hash)
            
            if receipt["status"] == "success":
                logger.info(f"Job completion submitted: {tx_hash}")
                return tx_hash
            else:
                raise Exception(f"Transaction failed: {receipt}")

        except Exception as e:
            logger.error(f"Failed to submit job completion: {e}")
            raise

    async def claim_rewards(self) -> str:
        """Claim rewards from marketplace contract"""
        if not self.agent_address:
            raise ValueError("Agent address not set")

        try:
            tx_hash = await self.contract_client.send_transaction(
                "agent_marketplace",
                "claimRewards"
            )

            receipt = await self.contract_client.wait_for_transaction(tx_hash)
            
            if receipt["status"] == "success":
                logger.info(f"Rewards claimed: {tx_hash}")
                return tx_hash
            else:
                raise Exception(f"Transaction failed: {receipt}")

        except Exception as e:
            logger.error(f"Failed to claim rewards: {e}")
            raise

    async def listen_to_contract_events(
        self,
        contract_name: str,
        event_name: str,
        callback: callable
    ) -> None:
        """Listen to contract events"""
        contract = self.contract_client.contracts.get(contract_name)
        if not contract:
            raise ValueError(f"Contract {contract_name} not loaded")

        try:
            # Create event filter
            event_filter = contract.events[event_name].create_filter(from_block='latest')
            
            # Poll for events
            while True:
                for event in event_filter.get_new_entries():
                    await callback(event)
                
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Error listening to events: {e}")
            raise


def getenv(key: str, default: str = "") -> str:
    """Get environment variable with default"""
    import os
    return os.getenv(key, default)
