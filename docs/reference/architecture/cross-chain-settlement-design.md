# Cross-Chain Settlement Hooks Design

## Overview

This document outlines the architecture for cross-chain settlement hooks in AITBC, enabling job receipts and proofs to be settled across multiple blockchains using various bridge protocols.

## Architecture

### Core Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AITBC Chain   │    │ Settlement Hooks │    │ Target Chains   │
│                 │    │                  │    │                 │
│ - Job Receipts  │───▶│ - Bridge Manager │───▶│ - Ethereum      │
│ - Proofs        │    │ - Adapters       │    │ - Polygon       │
│ - Payments      │    │ - Router         │    │ - BSC           │
│                 │    │ - Validator      │    │ - Arbitrum      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Settlement Hook Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class SettlementMessage:
    """Message to be settled across chains"""
    source_chain_id: int
    target_chain_id: int
    job_id: str
    receipt_hash: str
    proof_data: Dict[str, Any]
    payment_amount: int
    payment_token: str
    nonce: int
    signature: str

class BridgeAdapter(ABC):
    """Abstract interface for bridge adapters"""
    
    @abstractmethod
    async def send_message(self, message: SettlementMessage) -> str:
        """Send message to target chain"""
        pass
    
    @abstractmethod
    async def verify_delivery(self, message_id: str) -> bool:
        """Verify message was delivered"""
        pass
    
    @abstractmethod
    async def estimate_cost(self, message: SettlementMessage) -> Dict[str, int]:
        """Estimate bridge fees"""
        pass
    
    @abstractmethod
    def get_supported_chains(self) -> List[int]:
        """Get list of supported target chains"""
        pass
    
    @abstractmethod
    def get_max_message_size(self) -> int:
        """Get maximum message size in bytes"""
        pass
```

### Bridge Manager

```python
class BridgeManager:
    """Manages multiple bridge adapters"""
    
    def __init__(self):
        self.adapters: Dict[str, BridgeAdapter] = {}
        self.default_adapter: str = None
    
    def register_adapter(self, name: str, adapter: BridgeAdapter):
        """Register a bridge adapter"""
        self.adapters[name] = adapter
    
    async def settle_cross_chain(
        self, 
        message: SettlementMessage,
        bridge_name: str = None
    ) -> str:
        """Settle message across chains"""
        adapter = self._get_adapter(bridge_name)
        
        # Validate message
        self._validate_message(message, adapter)
        
        # Send message
        message_id = await adapter.send_message(message)
        
        # Store settlement record
        await self._store_settlement(message_id, message)
        
        return message_id
    
    def _get_adapter(self, bridge_name: str = None) -> BridgeAdapter:
        """Get bridge adapter"""
        if bridge_name:
            return self.adapters[bridge_name]
        return self.adapters[self.default_adapter]
```

## Bridge Implementations

### 1. LayerZero Adapter

```python
class LayerZeroAdapter(BridgeAdapter):
    """LayerZero bridge adapter"""
    
    def __init__(self, endpoint_address: str, chain_id: int):
        self.endpoint = endpoint_address
        self.chain_id = chain_id
        self.contract = self._load_contract()
    
    async def send_message(self, message: SettlementMessage) -> str:
        """Send via LayerZero"""
        # Encode settlement data
        payload = self._encode_payload(message)
        
        # Estimate fees
        fees = await self._estimate_fees(message)
        
        # Send transaction
        tx = await self.contract.send(
            message.target_chain_id,
            self._get_target_address(message.target_chain_id),
            payload,
            message.payment_amount,
            message.payment_token,
            fees
        )
        
        return tx.hash
    
    def _encode_payload(self, message: SettlementMessage) -> bytes:
        """Encode message for LayerZero"""
        return abi.encode(
            ['uint256', 'bytes32', 'bytes', 'uint256', 'address'],
            [
                message.job_id,
                message.receipt_hash,
                json.dumps(message.proof_data),
                message.payment_amount,
                message.payment_token
            ]
        )
```

### 2. Chainlink CCIP Adapter

```python
class ChainlinkCCIPAdapter(BridgeAdapter):
    """Chainlink CCIP bridge adapter"""
    
    def __init__(self, router_address: str, chain_id: int):
        self.router = router_address
        self.chain_id = chain_id
        self.contract = self._load_contract()
    
    async def send_message(self, message: SettlementMessage) -> str:
        """Send via Chainlink CCIP"""
        # Create CCIP message
        ccip_message = {
            'receiver': self._get_target_address(message.target_chain_id),
            'data': self._encode_payload(message),
            'tokenAmounts': [{
                'token': message.payment_token,
                'amount': message.payment_amount
            }]
        }
        
        # Estimate fees
        fees = await self.contract.getFee(ccip_message)
        
        # Send transaction
        tx = await self.contract.ccipSend(ccip_message, {'value': fees})
        
        return tx.hash
```

### 3. Wormhole Adapter

```python
class WormholeAdapter(BridgeAdapter):
    """Wormhole bridge adapter"""
    
    def __init__(self, bridge_address: str, chain_id: int):
        self.bridge = bridge_address
        self.chain_id = chain_id
        self.contract = self._load_contract()
    
    async def send_message(self, message: SettlementMessage) -> str:
        """Send via Wormhole"""
        # Encode payload
        payload = self._encode_payload(message)
        
        # Send transaction
        tx = await self.contract.publishMessage(
            message.nonce,
            payload,
            message.payment_amount
        )
        
        return tx.hash
```

## Integration with Coordinator

### Settlement Hook in Coordinator

```python
class SettlementHook:
    """Settlement hook for coordinator"""
    
    def __init__(self, bridge_manager: BridgeManager):
        self.bridge_manager = bridge_manager
    
    async def on_job_completed(self, job: Job) -> None:
        """Called when job completes"""
        # Check if cross-chain settlement needed
        if job.requires_cross_chain_settlement:
            await self._settle_cross_chain(job)
    
    async def _settle_cross_chain(self, job: Job) -> None:
        """Settle job across chains"""
        # Create settlement message
        message = SettlementMessage(
            source_chain_id=await self._get_chain_id(),
            target_chain_id=job.target_chain,
            job_id=job.id,
            receipt_hash=job.receipt.hash,
            proof_data=job.receipt.proof,
            payment_amount=job.payment_amount,
            payment_token=job.payment_token,
            nonce=await self._get_nonce(),
            signature=await self._sign_message(job)
        )
        
        # Send via appropriate bridge
        await self.bridge_manager.settle_cross_chain(
            message,
            bridge_name=job.preferred_bridge
        )
```

### Coordinator API Endpoints

```python
@app.post("/v1/settlement/cross-chain")
async def initiate_cross_chain_settlement(
    request: CrossChainSettlementRequest
):
    """Initiate cross-chain settlement"""
    job = await get_job(request.job_id)
    
    if not job.completed:
        raise HTTPException(400, "Job not completed")
    
    # Create settlement message
    message = SettlementMessage(
        source_chain_id=request.source_chain,
        target_chain_id=request.target_chain,
        job_id=job.id,
        receipt_hash=job.receipt.hash,
        proof_data=job.receipt.proof,
        payment_amount=request.amount,
        payment_token=request.token,
        nonce=await generate_nonce(),
        signature=await sign_settlement(job, request)
    )
    
    # Send settlement
    message_id = await settlement_hook.settle_cross_chain(message)
    
    return {"message_id": message_id, "status": "pending"}

@app.get("/v1/settlement/{message_id}/status")
async def get_settlement_status(message_id: str):
    """Get settlement status"""
    status = await bridge_manager.get_settlement_status(message_id)
    return status
```

## Configuration

### Bridge Configuration

```yaml
bridges:
  layerzero:
    enabled: true
    endpoint_address: "0x..."
    supported_chains: [1, 137, 56, 42161]
    default_fee: "0.001"
  
  chainlink_ccip:
    enabled: true
    router_address: "0x..."
    supported_chains: [1, 137, 56, 42161]
    default_fee: "0.002"
  
  wormhole:
    enabled: false
    bridge_address: "0x..."
    supported_chains: [1, 137, 56]
    default_fee: "0.0015"

settlement:
  default_bridge: "layerzero"
  max_retries: 3
  retry_delay: 30
  timeout: 3600
```

## Security Considerations

### Message Validation
- Verify signatures on all settlement messages
- Validate chain IDs and addresses
- Check message size limits
- Prevent replay attacks with nonces

### Bridge Security
- Use reputable audited bridge contracts
- Implement bridge-specific security checks
- Monitor for bridge vulnerabilities
- Have fallback mechanisms

### Economic Security
- Validate payment amounts
- Check token allowances
- Implement fee limits
- Monitor for economic attacks

## Monitoring

### Metrics to Track
- Settlement success rate per bridge
- Average settlement time
- Cost per settlement
- Failed settlement reasons
- Bridge health status

### Alerts
- Settlement failures
- High settlement costs
- Bridge downtime
- Unusual settlement patterns

## Testing

### Test Scenarios
1. **Happy Path**: Successful settlement across chains
2. **Bridge Failure**: Handle bridge unavailability
3. **Message Too Large**: Handle size limits
4. **Insufficient Funds**: Handle payment failures
5. **Replay Attack**: Prevent duplicate settlements

### Test Networks
- Ethereum Sepolia
- Polygon Mumbai
- BSC Testnet
- Arbitrum Goerli

## Migration Path

### Phase 1: Single Bridge
- Implement LayerZero adapter
- Basic settlement functionality
- Test on testnets

### Phase 2: Multiple Bridges
- Add Chainlink CCIP
- Implement bridge selection logic
- Add cost optimization

### Phase 3: Advanced Features
- Add Wormhole support
- Implement atomic settlements
- Add settlement routing

## Future Enhancements

1. **Atomic Settlements**: Ensure all-or-nothing settlements
2. **Settlement Routing**: Automatically select optimal bridge
3. **Batch Settlements**: Settle multiple jobs together
4. **Cross-Chain Governance**: Governance across chains
5. **Privacy Features**: Confidential settlements

---

*Document Version: 1.0*
*Last Updated: 2025-01-10*
*Owner: Core Protocol Team*
