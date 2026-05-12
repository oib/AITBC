"""
Test atomic swap methods with CLI client
"""
import asyncio
import sys
import os
import logging

import pytest

# Setup logging
logging.basicConfig(level=logging.INFO)

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Mock aitbc.aitbc_logging
class MockLogger:
    @staticmethod
    def get_logger(name):
        return logging.getLogger(name)

sys.modules['aitbc'] = type(sys)('aitbc')
sys.modules['aitbc.aitbc_logging'] = MockLogger
sys.modules['aitbc.exceptions'] = type(sys)('aitbc.exceptions')
sys.modules['aitbc.exceptions'].NetworkError = Exception

from aitbc_agent.contract_integration import ContractConfig, create_agent_contract_integration

@pytest.mark.asyncio
async def test_cli_client():
    """Test CLI client atomic swap methods"""
    print("Testing CLI client atomic swap methods...")

    # Create config with use_cli=True
    config = ContractConfig(
        payment_processor="0xpaymentprocessor",
        agent_marketplace="0xagentmarketplace",
        staking_contract="0xstakingcontract",
        treasury_manager="0xtreasurymanager",
        cross_chain_atomic_swap="0xcrosschainatomicswap_1778182201",
        use_cli=True,
        rpc_url="http://localhost:8545"
    )

    # Create integration with CLI client
    integration = create_agent_contract_integration(config, private_key=None)

    print(f"Contract client type: {type(integration.contract_client).__name__}")
    print(f"CLI available: {integration.contract_client.__class__.__name__ == 'CLIContractClient'}")

    # Test initiate_atomic_swap
    try:
        swap_id = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        hashlock = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        result = await integration.initiate_atomic_swap(
            swap_id=swap_id,
            token="AITBC",
            amount=1000,
            participant="test_participant",
            hashlock=hashlock,
            timelock=3600,
            contract_address=config.cross_chain_atomic_swap
        )
        print(f"initiate_atomic_swap result: {result}")
    except Exception as e:
        print(f"initiate_atomic_swap error: {e}")

    # Test complete_atomic_swap
    try:
        secret = "fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321"
        result = await integration.complete_atomic_swap(
            swap_id=swap_id,
            secret=secret,
            contract_address=config.cross_chain_atomic_swap
        )
        print(f"complete_atomic_swap result: {result}")
    except Exception as e:
        print(f"complete_atomic_swap error: {e}")

    # Test get_swap_status
    try:
        result = await integration.get_swap_status(
            swap_id=swap_id,
            contract_address=config.cross_chain_atomic_swap
        )
        print(f"get_swap_status result: {result}")
    except Exception as e:
        print(f"get_swap_status error: {e}")

    # Test refund_atomic_swap
    try:
        result = await integration.refund_atomic_swap(
            swap_id=swap_id,
            contract_address=config.cross_chain_atomic_swap
        )
        print(f"refund_atomic_swap result: {result}")
    except Exception as e:
        print(f"refund_atomic_swap error: {e}")

if __name__ == "__main__":
    asyncio.run(test_cli_client())
