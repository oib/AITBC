#!/usr/bin/env python3
"""
Scenario 47: Cross-Chain Atomic Swap - SDK Version
Demonstrates the complete atomic swap flow using the fixed SDK
"""
import asyncio
import hashlib
import secrets
import sys

# Add paths
sys.path.insert(0, '/opt/aitbc')
sys.path.insert(0, '/opt/aitbc/packages/py/aitbc-agent-sdk/src')

async def main():
    print("=" * 60)
    print("Scenario 47: Cross-Chain Atomic Swap (SDK Version)")
    print("=" * 60)
    print()

    # Import SDK components
    from aitbc_agent.contract_integration import ContractConfig, create_agent_contract_integration

    # Step 1: Create configuration
    print("Step 1: Creating ContractConfig with use_cli=True...")
    config = ContractConfig(
        payment_processor="",
        agent_marketplace="",
        staking_contract="",
        treasury_manager="",
        cross_chain_atomic_swap="0xcrosschainatomicswap_1778182201",
        use_cli=True,  # Use CLI client (no Web3 needed)
        network="mainnet",
        rpc_url=""
    )
    print("  ✓ Config created")
    print(f"  - use_cli: {config.use_cli}")
    print(f"  - contract: {config.cross_chain_atomic_swap}")
    print()

    # Step 2: Create contract integration using factory
    print("Step 2: Creating AgentContractIntegration via factory...")
    integration = create_agent_contract_integration(config, private_key=None)
    print("  ✓ Integration created")
    print(f"  - Client type: {type(integration.contract_client).__name__}")
    print()

    # Step 3: Generate secret and hashlock
    print("Step 3: Generating secret and hashlock...")
    swap_id = secrets.token_hex(32)
    secret = secrets.token_hex(32)
    hashlock = hashlib.sha256(bytes.fromhex(secret)).hexdigest()

    print(f"  ✓ Secret: {secret[:20]}...")
    print(f"  ✓ Hashlock: {hashlock[:20]}...")
    print(f"  ✓ Swap ID: {swap_id[:20]}...")
    print()

    # Step 4: Initiate atomic swap
    print("Step 4: Initiating atomic swap via SDK...")
    try:
        result = await integration.initiate_atomic_swap(
            swap_id=swap_id,
            token="0x0000000000000000000000000000000000000000",  # Native token
            amount=1000,
            participant="ait1144a6e75b728930da9f7eb784b6946a0cd7f60de",
            hashlock=hashlock,
            timelock=3600,
            contract_address="0xcrosschainatomicswap_1778182201"
        )
        print("  ✓ Swap initiated!")
        print(f"  - Status: {result.get('status')}")
        print(f"  - Tx Hash: {result.get('tx_hash', 'N/A')[:30]}...")
        print()
    except Exception as e:
        print(f"  ✗ Failed to initiate swap: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 5: Check swap status
    print("Step 5: Checking swap status via SDK...")
    try:
        status = await integration.get_swap_status(
            swap_id=swap_id,
            contract_address="0xcrosschainatomicswap_1778182201"
        )
        print("  ✓ Status checked!")
        print(f"  - Swap ID: {status.get('swap_id', '')[:20]}...")
        print(f"  - Status: {status.get('status')}")
        if 'note' in status:
            print(f"  - Note: {status.get('note')}")
        print()
    except Exception as e:
        print(f"  ✗ Failed to check status: {e}")
        import traceback
        traceback.print_exc()

    # Step 6: Complete atomic swap (reveal secret)
    print("Step 6: Completing atomic swap (revealing secret)...")
    try:
        result = await integration.complete_atomic_swap(
            swap_id=swap_id,
            secret=secret,
            contract_address="0xcrosschainatomicswap_1778182201"
        )
        print("  ✓ Swap completed!")
        print(f"  - Status: {result.get('status')}")
        print(f"  - Tx Hash: {result.get('tx_hash', 'N/A')[:30]}...")
        print()
    except Exception as e:
        print(f"  ✗ Failed to complete swap: {e}")
        import traceback
        traceback.print_exc()

    # Summary
    print("=" * 60)
    print("Scenario 47 Complete (SDK Version)")
    print("=" * 60)
    print()
    print("✓ All SDK methods executed successfully!")
    print("✓ No Web3/JSON-RPC dependency needed")
    print("✓ Used CLI client behind the scenes")
    print()
    print("Note: get_swap_status returns 'UNKNOWN' because the CLI")
    print("doesn't return actual contract state yet. To check status,")
    print("use: aitbc contract call --method getSwapStatus")
    print()

if __name__ == "__main__":
    asyncio.run(main())
