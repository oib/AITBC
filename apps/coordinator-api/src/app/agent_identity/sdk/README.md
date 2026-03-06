# AITBC Agent Identity SDK

The AITBC Agent Identity SDK provides a comprehensive Python interface for managing agent identities across multiple blockchains. This SDK enables developers to create, manage, and verify agent identities with cross-chain compatibility.

## Features

- **Multi-Chain Support**: Ethereum, Polygon, BSC, Arbitrum, Optimism, Avalanche, and more
- **Identity Management**: Create, update, and manage agent identities
- **Cross-Chain Mapping**: Register and manage identities across multiple blockchains
- **Wallet Integration**: Create and manage agent wallets on supported chains
- **Verification System**: Verify identities with multiple verification levels
- **Reputation Management**: Sync and manage agent reputation across chains
- **Search & Discovery**: Advanced search capabilities for agent discovery
- **Import/Export**: Backup and restore agent identity data

## Installation

```bash
pip install aitbc-agent-identity-sdk
```

## Quick Start

```python
import asyncio
from aitbc_agent_identity_sdk import AgentIdentityClient

async def main():
    # Initialize the client
    async with AgentIdentityClient(
        base_url="http://localhost:8000/v1",
        api_key="your_api_key"
    ) as client:
        
        # Create a new agent identity
        identity = await client.create_identity(
            owner_address="0x1234567890123456789012345678901234567890",
            chains=[1, 137],  # Ethereum and Polygon
            display_name="My AI Agent",
            description="An intelligent AI agent for decentralized computing"
        )
        
        print(f"Created identity: {identity.agent_id}")
        print(f"Supported chains: {identity.supported_chains}")
        
        # Get identity details
        details = await client.get_identity(identity.agent_id)
        print(f"Reputation score: {details['identity']['reputation_score']}")
        
        # Create a wallet on Ethereum
        wallet = await client.create_wallet(
            agent_id=identity.agent_id,
            chain_id=1,
            owner_address="0x1234567890123456789012345678901234567890"
        )
        
        print(f"Created wallet: {wallet.chain_address}")
        
        # Get wallet balance
        balance = await client.get_wallet_balance(identity.agent_id, 1)
        print(f"Wallet balance: {balance} ETH")

if __name__ == "__main__":
    asyncio.run(main())
```

## Core Concepts

### Agent Identity

An agent identity represents a unified identity across multiple blockchains. Each identity has:

- **Agent ID**: Unique identifier for the agent
- **Owner Address**: Ethereum address that owns the identity
- **Cross-Chain Mappings**: Addresses on different blockchains
- **Verification Status**: Verification level and status
- **Reputation Score**: Cross-chain aggregated reputation

### Cross-Chain Mapping

Cross-chain mappings link an agent identity to specific addresses on different blockchains:

```python
# Register cross-chain mappings
await client.register_cross_chain_mappings(
    agent_id="agent_123",
    chain_mappings={
        1: "0x123...",  # Ethereum
        137: "0x456...", # Polygon
        56: "0x789..."   # BSC
    },
    verifier_address="0xverifier..."
)
```

### Wallet Management

Each agent can have wallets on different chains:

```python
# Create wallet on specific chain
wallet = await client.create_wallet(
    agent_id="agent_123",
    chain_id=1,
    owner_address="0x123..."
)

# Execute transaction
tx = await client.execute_transaction(
    agent_id="agent_123",
    chain_id=1,
    to_address="0x456...",
    amount=0.1
)
```

## API Reference

### Identity Management

#### Create Identity

```python
await client.create_identity(
    owner_address: str,
    chains: List[int],
    display_name: str = "",
    description: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None
) -> CreateIdentityResponse
```

#### Get Identity

```python
await client.get_identity(agent_id: str) -> Dict[str, Any]
```

#### Update Identity

```python
await client.update_identity(
    agent_id: str,
    updates: Dict[str, Any]
) -> UpdateIdentityResponse
```

#### Deactivate Identity

```python
await client.deactivate_identity(agent_id: str, reason: str = "") -> bool
```

### Cross-Chain Operations

#### Register Cross-Chain Mappings

```python
await client.register_cross_chain_mappings(
    agent_id: str,
    chain_mappings: Dict[int, str],
    verifier_address: Optional[str] = None,
    verification_type: VerificationType = VerificationType.BASIC
) -> Dict[str, Any]
```

#### Get Cross-Chain Mappings

```python
await client.get_cross_chain_mappings(agent_id: str) -> List[CrossChainMapping]
```

#### Verify Identity

```python
await client.verify_identity(
    agent_id: str,
    chain_id: int,
    verifier_address: str,
    proof_hash: str,
    proof_data: Dict[str, Any],
    verification_type: VerificationType = VerificationType.BASIC
) -> VerifyIdentityResponse
```

#### Migrate Identity

```python
await client.migrate_identity(
    agent_id: str,
    from_chain: int,
    to_chain: int,
    new_address: str,
    verifier_address: Optional[str] = None
) -> MigrationResponse
```

### Wallet Operations

#### Create Wallet

```python
await client.create_wallet(
    agent_id: str,
    chain_id: int,
    owner_address: Optional[str] = None
) -> AgentWallet
```

#### Get Wallet Balance

```python
await client.get_wallet_balance(agent_id: str, chain_id: int) -> float
```

#### Execute Transaction

```python
await client.execute_transaction(
    agent_id: str,
    chain_id: int,
    to_address: str,
    amount: float,
    data: Optional[Dict[str, Any]] = None
) -> TransactionResponse
```

#### Get Transaction History

```python
await client.get_transaction_history(
    agent_id: str,
    chain_id: int,
    limit: int = 50,
    offset: int = 0
) -> List[Transaction]
```

### Search and Discovery

#### Search Identities

```python
await client.search_identities(
    query: str = "",
    chains: Optional[List[int]] = None,
    status: Optional[IdentityStatus] = None,
    verification_level: Optional[VerificationType] = None,
    min_reputation: Optional[float] = None,
    limit: int = 50,
    offset: int = 0
) -> SearchResponse
```

#### Sync Reputation

```python
await client.sync_reputation(agent_id: str) -> SyncReputationResponse
```

### Utility Functions

#### Get Registry Health

```python
await client.get_registry_health() -> RegistryHealth
```

#### Get Supported Chains

```python
await client.get_supported_chains() -> List[ChainConfig]
```

#### Export/Import Identity

```python
# Export
await client.export_identity(agent_id: str, format: str = 'json') -> Dict[str, Any]

# Import
await client.import_identity(export_data: Dict[str, Any]) -> Dict[str, Any]
```

## Models

### IdentityStatus

```python
class IdentityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
```

### VerificationType

```python
class VerificationType(str, Enum):
    BASIC = "basic"
    ADVANCED = "advanced"
    ZERO_KNOWLEDGE = "zero-knowledge"
    MULTI_SIGNATURE = "multi-signature"
```

### ChainType

```python
class ChainType(str, Enum):
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    BSC = "bsc"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    AVALANCHE = "avalanche"
    SOLANA = "solana"
    CUSTOM = "custom"
```

## Error Handling

The SDK provides specific exceptions for different error types:

```python
from aitbc_agent_identity_sdk import (
    AgentIdentityError,
    ValidationError,
    NetworkError,
    AuthenticationError,
    RateLimitError,
    WalletError
)

try:
    await client.create_identity(...)
except ValidationError as e:
    print(f"Validation error: {e}")
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
except RateLimitError as e:
    print(f"Rate limit exceeded: {e}")
except NetworkError as e:
    print(f"Network error: {e}")
except AgentIdentityError as e:
    print(f"General error: {e}")
```

## Convenience Functions

The SDK provides convenience functions for common operations:

### Create Identity with Wallets

```python
from aitbc_agent_identity_sdk import create_identity_with_wallets

identity = await create_identity_with_wallets(
    client=client,
    owner_address="0x123...",
    chains=[1, 137],
    display_name="My Agent"
)
```

### Verify Identity on All Chains

```python
from aitbc_agent_identity_sdk import verify_identity_on_all_chains

results = await verify_identity_on_all_chains(
    client=client,
    agent_id="agent_123",
    verifier_address="0xverifier...",
    proof_data_template={"type": "basic"}
)
```

### Get Identity Summary

```python
from aitbc_agent_identity_sdk import get_identity_summary

summary = await get_identity_summary(client, "agent_123")
print(f"Total balance: {summary['metrics']['total_balance']}")
print(f"Verification rate: {summary['metrics']['verification_rate']}")
```

## Configuration

### Client Configuration

```python
client = AgentIdentityClient(
    base_url="http://localhost:8000/v1",  # API base URL
    api_key="your_api_key",                # Optional API key
    timeout=30,                           # Request timeout in seconds
    max_retries=3                         # Maximum retry attempts
)
```

### Supported Chains

The SDK supports the following chains out of the box:

| Chain ID | Name | Type |
|----------|------|------|
| 1 | Ethereum Mainnet | ETHEREUM |
| 137 | Polygon Mainnet | POLYGON |
| 56 | BSC Mainnet | BSC |
| 42161 | Arbitrum One | ARBITRUM |
| 10 | Optimism | OPTIMISM |
| 43114 | Avalanche C-Chain | AVALANCHE |

Additional chains can be configured at runtime.

## Testing

Run the test suite:

```bash
pytest tests/test_agent_identity_sdk.py -v
```

## Examples

### Complete Agent Setup

```python
import asyncio
from aitbc_agent_identity_sdk import AgentIdentityClient, VerificationType

async def setup_agent():
    async with AgentIdentityClient() as client:
        # 1. Create identity
        identity = await client.create_identity(
            owner_address="0x123...",
            chains=[1, 137, 56],
            display_name="Advanced AI Agent",
            description="Multi-chain AI agent for decentralized computing",
            tags=["ai", "computing", "decentralized"]
        )
        
        print(f"Created agent: {identity.agent_id}")
        
        # 2. Verify on all chains
        for chain_id in identity.supported_chains:
            await client.verify_identity(
                agent_id=identity.agent_id,
                chain_id=int(chain_id),
                verifier_address="0xverifier...",
                proof_hash="generated_proof_hash",
                proof_data={"verification_type": "basic"},
                verification_type=VerificationType.BASIC
            )
        
        # 3. Get comprehensive summary
        summary = await client.get_identity(identity.agent_id)
        
        print(f"Reputation: {summary['identity']['reputation_score']}")
        print(f"Verified mappings: {summary['cross_chain']['verified_mappings']}")
        print(f"Total balance: {summary['wallets']['total_balance']}")

if __name__ == "__main__":
    asyncio.run(setup_agent())
```

### Transaction Management

```python
async def manage_transactions():
    async with AgentIdentityClient() as client:
        agent_id = "agent_123"
        
        # Check balances across all chains
        wallets = await client.get_all_wallets(agent_id)
        
        for wallet in wallets['wallets']:
            balance = await client.get_wallet_balance(agent_id, wallet['chain_id'])
            print(f"Chain {wallet['chain_id']}: {balance} tokens")
        
        # Execute transaction on Ethereum
        tx = await client.execute_transaction(
            agent_id=agent_id,
            chain_id=1,
            to_address="0x456...",
            amount=0.1,
            data={"purpose": "payment"}
        )
        
        print(f"Transaction hash: {tx.transaction_hash}")
        
        # Get transaction history
        history = await client.get_transaction_history(agent_id, 1, limit=10)
        for tx in history:
            print(f"TX: {tx.hash} - {tx.amount} to {tx.to_address}")
```

## Best Practices

1. **Use Context Managers**: Always use the client with async context managers
2. **Handle Errors**: Implement proper error handling for different exception types
3. **Batch Operations**: Use batch operations when possible for efficiency
4. **Cache Results**: Cache frequently accessed data like identity summaries
5. **Monitor Health**: Check registry health before critical operations
6. **Verify Identities**: Always verify identities before sensitive operations
7. **Sync Reputation**: Regularly sync reputation across chains

## Support

- **Documentation**: [https://docs.aitbc.io/agent-identity-sdk](https://docs.aitbc.io/agent-identity-sdk)
- **Issues**: [GitHub Issues](https://github.com/aitbc/agent-identity-sdk/issues)
- **Community**: [AITBC Discord](https://discord.gg/aitbc)

## License

MIT License - see LICENSE file for details.
