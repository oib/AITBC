# Mock Data and Placeholder System Documentation

This document describes the mock data and placeholder systems in AITBC, including the toggle system for development/testing, data layer abstraction, testing utilities, and chain registry configuration.

## Overview

The AITBC codebase previously contained mock data and placeholders in various locations. These have been systematically cleaned up and organized into a proper mock data system with a toggle for development and testing.

## Data Layer Abstraction

### Purpose

The data layer provides a clean abstraction between mock and real data sources, allowing developers to switch between mock data (for development/testing) and real blockchain data (for production).

### Usage

The data layer is implemented in `aitbc/data_layer.py` and provides three main classes:

- **DataLayer**: Main abstraction layer that switches between mock and real data sources
- **MockDataGenerator**: Generates mock data when mock mode is enabled
- **RealDataFetcher**: Fetches real data from blockchain RPC endpoints

### Configuration

Toggle mock data mode using the `USE_MOCK_DATA` environment variable:

```bash
# Enable mock data mode (for development/testing)
export USE_MOCK_DATA=true

# Disable mock data mode (use real data - default)
export USE_MOCK_DATA=false
```

### Example Usage

```python
from aitbc import get_data_layer

# Get data layer instance (respects USE_MOCK_DATA env var)
data_layer = get_data_layer()

# Get transactions (will use mock or real data based on config)
transactions = await data_layer.get_transactions(
    address="0x123...",
    limit=50,
    chain_id="ait-devnet",
    rpc_url="http://localhost:8025"
)

# Get blocks
blocks = await data_layer.get_blocks(
    validator="0xabc...",
    limit=50,
    chain_id="ait-devnet"
)

# Get analytics
analytics = await data_layer.get_analytics_overview(period="24h")
```

### Force Mode

You can also force a specific mode programmatically:

```python
from aitbc import DataLayer

# Force mock mode
data_layer = DataLayer(use_mock_data=True)

# Force real data mode
data_layer = DataLayer(use_mock_data=False)
```

## Blockchain Explorer Integration

The blockchain explorer (`apps/blockchain-explorer/main.py`) has been updated to use the data layer when available. It falls back to direct RPC calls if the data layer is not available.

### Endpoints Updated

- `/api/search/transactions` - Uses data layer for transaction search
- `/api/search/blocks` - Uses data layer for block search
- `/api/analytics/overview` - Uses data layer for analytics data

## Chain Registry Configuration

### Purpose

The chain registry provides a centralized configuration for blockchain networks, replacing hardcoded chain lists throughout the codebase.

### Location

Configuration file: `cli/config/chains.py`

### Usage

```python
from cli.config.chains import get_chain_registry

# Get global chain registry
registry = get_chain_registry()

# Get all chains
chains = registry.get_chain_ids()

# Get specific chain
chain = registry.get_chain("ait-devnet")

# Get testnet chains only
testnets = registry.get_testnet_chains()

# Get mainnet chains only
mainnets = registry.get_mainnet_chains()
```

### Environment Variable Configuration

You can add custom chains via environment variables:

```bash
export AITBC_CHAIN_MYCHAIN_NAME="My Custom Chain"
export AITBC_CHAIN_MYCHAIN_RPC_URL="http://localhost:8030"
export AITBC_CHAIN_MYCHAIN_EXPLORER_URL="http://localhost:8031"
export AITBC_CHAIN_MYCHAIN_IS_TESTNET="true"
export AITBC_CHAIN_MYCHAIN_NATIVE_CURRENCY="AITBC"
```

### Default Chains

The registry comes with two default chains:

- **ait-devnet**: Development network (localhost:8025)
- **ait-testnet**: Test network (localhost:8027)

## Testing Utilities

### Purpose

The `aitbc.testing` module provides standardized testing utilities for generating mock data across the codebase.

### Components

- **MockFactory**: Generates mock strings, emails, URLs, hashes, and Ethereum addresses
- **TestDataGenerator**: Generates structured test data (users, transactions, wallets, etc.)
- **MockResponse**: Mock HTTP response object for testing
- **MockDatabase**: Mock database for testing
- **MockCache**: Mock cache for testing
- **TestHelpers**: Helper functions for common test scenarios

### Usage in Tests

```python
from aitbc.testing import MockFactory, TestDataGenerator, MockResponse

# Generate mock data
email = MockFactory.generate_email()
url = MockFactory.generate_url()
eth_address = MockFactory.generate_ethereum_address()

# Generate structured test data
user_data = TestDataGenerator.generate_user_data()
transaction_data = TestDataGenerator.generate_transaction_data()
wallet_data = TestDataGenerator.generate_wallet_data()

# Create mock HTTP response
mock_response = MockResponse(
    status_code=200,
    json_data={"result": "success"},
    text="success"
)
```

### Pytest Fixtures

The `tests/conftest.py` file has been updated with reusable fixtures:

```python
@pytest.fixture
def mock_db():
    """Create a mock database for testing"""
    return MockDatabase()

@pytest.fixture
def mock_cache():
    """Create a mock cache for testing"""
    return MockCache()

@pytest.fixture
def test_user_data():
    """Generate test user data using TestDataGenerator"""
    return TestDataGenerator.generate_user_data()

@pytest.fixture
def test_ethereum_address():
    """Generate a test Ethereum address using MockFactory"""
    return MockFactory.generate_ethereum_address()
```

## Agent SDK Implementation

### Compute Consumer

The `compute_consumer.py` module has been updated to use the coordinator API for job submission and status queries:

- `submit_job()`: Submits jobs to coordinator API at `/v1/jobs`
- `get_job_status()`: Queries job status from coordinator API at `/v1/jobs/{job_id}`

### Swarm Coordinator

The `swarm_coordinator.py` module has been updated to use coordinator APIs for various operations:

- `_get_load_balancing_data()`: Fetches from `/v1/load-balancing/metrics`
- `_get_pricing_data()`: Fetches from `/v1/marketplace/pricing/trends`
- `_get_security_data()`: Fetches from `/v1/security/metrics`
- `_register_with_swarm()`: Registers via `/v1/swarm/{swarm_id}/register`
- `_broadcast_to_swarm_network()`: Broadcasts via `/v1/swarm/{swarm_id}/broadcast`
- `_process_swarm_messages()`: Processes messages from `/v1/swarm/{swarm_id}/messages`
- `_participate_in_decisions()`: Participates via `/v1/swarm/{swarm_id}/decisions/participate`
- `_submit_coordination_proposal()`: Submits via `/v1/swarm/coordination/proposals`

All methods include fallback to default data when the coordinator API is unavailable.

## Migration Guide

### For Existing Code

1. **Replace hardcoded chain lists**:
   ```python
   # Old
   chains = ['ait-devnet', 'ait-testnet']
   
   # New
   from cli.config.chains import get_chain_registry
   registry = get_chain_registry()
   chains = registry.get_chain_ids()
   ```

2. **Use data layer for data fetching**:
   ```python
   # Old
   response = await client.get(f"{rpc_url}/rpc/transactions")
   data = response.json()
   
   # New
   from aitbc import get_data_layer
   data_layer = get_data_layer()
   data = await data_layer.get_transactions(rpc_url=rpc_url)
   ```

3. **Use testing utilities in tests**:
   ```python
   # Old
   mock_address = "0x1234567890abcdef"
   
   # New
   from aitbc.testing import MockFactory
   mock_address = MockFactory.generate_ethereum_address()
   ```

### For New Code

1. Always use the chain registry for chain configuration
2. Use the data layer for all data fetching operations
3. Use testing utilities for generating mock data in tests
4. Implement proper error handling with fallbacks when external APIs are unavailable

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer                         │
│  (Blockchain Explorer, CLI, Agent SDK, etc.)                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer Abstraction                     │
│  (aitbc/data_layer.py)                                      │
│  - USE_MOCK_DATA environment variable                        │
│  - Switches between mock and real data sources               │
└──────────┬────────────────────────────┬──────────────────────┘
           │                            │
           ▼                            ▼
┌──────────────────────┐    ┌──────────────────────────┐
│  MockDataGenerator   │    │   RealDataFetcher        │
│  (aitbc/data_layer)   │    │   (aitbc/data_layer)     │
│  - Generates mock     │    │   - Fetches from RPC     │
│    data for testing   │    │   - Blockchain RPC calls  │
└──────────────────────┘    └──────────────────────────┘
```

## Best Practices

1. **Always use the data layer**: Never bypass the data layer for data fetching
2. **Test both modes**: Ensure code works with both mock and real data
3. **Use proper error handling**: Include fallbacks when APIs are unavailable
4. **Document mock data**: Clearly indicate when data is mock vs real
5. **Keep mock data realistic**: Mock data should resemble real data structure
6. **Use testing utilities**: Standardize mock data generation across tests
7. **Configure chains properly**: Use chain registry for all chain configuration

## Troubleshooting

### Mock Data Not Working

- Check `USE_MOCK_DATA` environment variable is set to `true`
- Verify data layer is properly imported
- Check logs for import errors

### Chain Registry Issues

- Verify chain IDs match expected format
- Check environment variable configuration
- Ensure coordinator URL is accessible

### Testing Utilities Not Available

- Verify `aitbc.testing` module is in Python path
- Check imports in `tests/conftest.py`
- Ensure dependencies are installed

## References

- Data layer implementation: `aitbc/data_layer.py`
- Chain registry: `cli/config/chains.py`
- Testing utilities: `aitbc/testing.py`
- Blockchain explorer: `apps/blockchain-explorer/main.py`
- Agent SDK: `packages/py/aitbc-agent-sdk/src/aitbc_agent/`
