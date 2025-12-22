"""
LayerZero bridge adapter implementation
"""

from typing import Dict, Any, List, Optional
import json
import asyncio
from web3 import Web3
from web3.contract import Contract
from eth_utils import to_checksum_address, encode_hex

from .base import (
    BridgeAdapter, 
    BridgeConfig, 
    SettlementMessage, 
    SettlementResult,
    BridgeStatus,
    BridgeError,
    BridgeTimeoutError,
    BridgeInsufficientFundsError
)


class LayerZeroAdapter(BridgeAdapter):
    """LayerZero bridge adapter for cross-chain settlements"""
    
    # LayerZero chain IDs
    CHAIN_IDS = {
        1: 101,      # Ethereum
        137: 109,     # Polygon
        56: 102,      # BSC
        42161: 110,   # Arbitrum
        10: 111,      # Optimism
        43114: 106    # Avalanche
    }
    
    def __init__(self, config: BridgeConfig, web3: Web3):
        super().__init__(config)
        self.web3 = web3
        self.endpoint: Optional[Contract] = None
        self.ultra_light_node: Optional[Contract] = None
        
    async def initialize(self) -> None:
        """Initialize LayerZero contracts"""
        # Load LayerZero endpoint ABI
        endpoint_abi = await self._load_abi("LayerZeroEndpoint")
        self.endpoint = self.web3.eth.contract(
            address=to_checksum_address(self.config.endpoint_address),
            abi=endpoint_abi
        )
        
        # Load Ultra Light Node ABI for fee estimation
        uln_abi = await self._load_abi("UltraLightNode")
        uln_address = await self.endpoint.functions.ultraLightNode().call()
        self.ultra_light_node = self.web3.eth.contract(
            address=to_checksum_address(uln_address),
            abi=uln_abi
        )
        
    async def send_message(self, message: SettlementMessage) -> SettlementResult:
        """Send message via LayerZero"""
        try:
            # Validate message
            await self.validate_message(message)
            
            # Get target address on destination chain
            target_address = await self._get_target_address(message.target_chain_id)
            
            # Encode payload
            payload = self._encode_payload(message)
            
            # Estimate fees
            fees = await self.estimate_cost(message)
            
            # Get gas limit
            gas_limit = message.gas_limit or await self._get_gas_estimate(message)
            
            # Build transaction
            tx_params = {
                'from': await self._get_signer_address(),
                'gas': gas_limit,
                'value': fees['layerZeroFee'],
                'nonce': await self.web3.eth.get_transaction_count(
                    await self._get_signer_address()
                )
            }
            
            # Send transaction
            tx_hash = await self.endpoint.functions.send(
                self.CHAIN_IDS[message.target_chain_id],  # dstChainId
                target_address,                           # destination address
                payload,                                  # payload
                message.payment_amount,                  # value (optional)
                [0, 0, 0],                               # address and parameters for adapterParams
                message.nonce                            # refund address
            ).transact(tx_params)
            
            # Wait for confirmation
            receipt = await self.web3.eth.wait_for_transaction_receipt(tx_hash)
            
            return SettlementResult(
                message_id=tx_hash.hex(),
                status=BridgeStatus.IN_PROGRESS,
                transaction_hash=tx_hash.hex(),
                gas_used=receipt.gasUsed,
                fee_paid=fees['layerZeroFee']
            )
            
        except Exception as e:
            return SettlementResult(
                message_id="",
                status=BridgeStatus.FAILED,
                error_message=str(e)
            )
    
    async def verify_delivery(self, message_id: str) -> bool:
        """Verify message was delivered"""
        try:
            # Get transaction receipt
            receipt = await self.web3.eth.get_transaction_receipt(message_id)
            
            # Check for Delivered event
            delivered_logs = self.endpoint.events.Delivered().processReceipt(receipt)
            return len(delivered_logs) > 0
            
        except Exception:
            return False
    
    async def get_message_status(self, message_id: str) -> SettlementResult:
        """Get current status of message"""
        try:
            # Get transaction receipt
            receipt = await self.web3.eth.get_transaction_receipt(message_id)
            
            if receipt.status == 0:
                return SettlementResult(
                    message_id=message_id,
                    status=BridgeStatus.FAILED,
                    transaction_hash=message_id,
                    completed_at=receipt['blockTimestamp']
                )
            
            # Check if delivered
            if await self.verify_delivery(message_id):
                return SettlementResult(
                    message_id=message_id,
                    status=BridgeStatus.COMPLETED,
                    transaction_hash=message_id,
                    completed_at=receipt['blockTimestamp']
                )
            
            # Still in progress
            return SettlementResult(
                message_id=message_id,
                status=BridgeStatus.IN_PROGRESS,
                transaction_hash=message_id
            )
            
        except Exception as e:
            return SettlementResult(
                message_id=message_id,
                status=BridgeStatus.FAILED,
                error_message=str(e)
            )
    
    async def estimate_cost(self, message: SettlementMessage) -> Dict[str, int]:
        """Estimate LayerZero fees"""
        try:
            # Get destination chain ID
            dst_chain_id = self.CHAIN_IDS[message.target_chain_id]
            
            # Get target address
            target_address = await self._get_target_address(message.target_chain_id)
            
            # Encode payload
            payload = self._encode_payload(message)
            
            # Estimate fee using LayerZero endpoint
            (native_fee, zro_fee) = await self.endpoint.functions.estimateFees(
                dst_chain_id,
                target_address,
                payload,
                False,  # payInZRO
                [0, 0, 0]  # adapterParams
            ).call()
            
            return {
                'layerZeroFee': native_fee,
                'zroFee': zro_fee,
                'total': native_fee + zro_fee
            }
            
        except Exception as e:
            raise BridgeError(f"Failed to estimate fees: {str(e)}")
    
    async def refund_failed_message(self, message_id: str) -> SettlementResult:
        """LayerZero doesn't support direct refunds"""
        raise BridgeNotSupportedError("LayerZero does not support message refunds")
    
    def _encode_payload(self, message: SettlementMessage) -> bytes:
        """Encode settlement message for LayerZero"""
        # Use ABI encoding for structured data
        from web3 import Web3
        
        # Define the payload structure
        payload_types = [
            'uint256',    # job_id
            'bytes32',    # receipt_hash
            'bytes',      # proof_data (JSON)
            'uint256',    # payment_amount
            'address',    # payment_token
            'uint256',    # nonce
            'bytes'       # signature
        ]
        
        payload_values = [
            int(message.job_id),
            bytes.fromhex(message.receipt_hash),
            json.dumps(message.proof_data).encode(),
            message.payment_amount,
            to_checksum_address(message.payment_token),
            message.nonce,
            bytes.fromhex(message.signature)
        ]
        
        # Encode the payload
        encoded = Web3().codec.encode(payload_types, payload_values)
        return encoded
    
    async def _get_target_address(self, target_chain_id: int) -> str:
        """Get target contract address on destination chain"""
        # This would look up the target address from configuration
        # For now, return a placeholder
        target_addresses = {
            1: "0x...",      # Ethereum
            137: "0x...",     # Polygon
            56: "0x...",      # BSC
            42161: "0x..."    # Arbitrum
        }
        
        if target_chain_id not in target_addresses:
            raise ValueError(f"No target address configured for chain {target_chain_id}")
        
        return target_addresses[target_chain_id]
    
    async def _get_gas_estimate(self, message: SettlementMessage) -> int:
        """Estimate gas for LayerZero transaction"""
        try:
            # Get target address
            target_address = await self._get_target_address(message.target_chain_id)
            
            # Encode payload
            payload = self._encode_payload(message)
            
            # Estimate gas
            gas_estimate = await self.endpoint.functions.send(
                self.CHAIN_IDS[message.target_chain_id],
                target_address,
                payload,
                message.payment_amount,
                [0, 0, 0],
                message.nonce
            ).estimateGas({'from': await self._get_signer_address()})
            
            # Add 20% buffer
            return int(gas_estimate * 1.2)
            
        except Exception:
            # Return default estimate
            return 300000
    
    async def _get_signer_address(self) -> str:
        """Get the signer address for transactions"""
        # This would get the address from the wallet/key management system
        # For now, return a placeholder
        return "0x..."
    
    async def _load_abi(self, contract_name: str) -> List[Dict]:
        """Load contract ABI from file or registry"""
        # This would load the ABI from a file or contract registry
        # For now, return empty list
        return []
    
    async def _verify_signature(self, message: SettlementMessage) -> bool:
        """Verify LayerZero message signature"""
        # Implement signature verification specific to LayerZero
        # This would verify the message signature using the appropriate scheme
        return True
