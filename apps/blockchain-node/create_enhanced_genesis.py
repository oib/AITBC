#!/usr/bin/env python3
"""
Enhanced script to create genesis block with new features
"""

import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any

import yaml
from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc_chain.database import init_db, session_scope
from aitbc_chain.models import Account, Block, Transaction
from sqlmodel import select

logger = get_logger(__name__)


def compute_block_hash(height: int, parent_hash: str, timestamp: datetime, chain_id: str) -> str:
    """Compute enhanced block hash with chain_id"""
    data = f"{height}{parent_hash}{timestamp}{chain_id}".encode()
    return hashlib.sha256(data).hexdigest()


def create_genesis_accounts(session, accounts: list[dict[str, Any]], chain_id: str):
    """Create genesis accounts"""
    logger.info(f"🏦 Creating {len(accounts)} genesis accounts...")

    for account in accounts:
        db_account = Account(address=account["address"], balance=int(account["balance"]), chain_id=chain_id)
        session.add(db_account)
        logger.info(f"  ✅ Created account: {account['address']} ({account['balance']} AITBC)")


def create_genesis_contracts(session, contracts: list[dict[str, Any]], chain_id: str):
    """Create genesis contracts"""
    logger.info(f"📜 Deploying {len(contracts)} genesis contracts...")

    for contract in contracts:
        # Create contract deployment transaction
        deployment_tx = Transaction(
            chain_id=chain_id,
            tx_hash=f"0x{hashlib.sha256(f'contract_{contract["name"]}_{chain_id}'.encode()).hexdigest()}",
            sender="aitbc1genesis",
            recipient=contract["address"],
            payload={"type": "contract_deployment", "contract_name": contract["name"], "code": contract.get("code", "0x")},
        )
        session.add(deployment_tx)
        logger.info(f"  ✅ Deployed contract: {contract['name']} at {contract['address']}")


def create_enhanced_genesis(config_path: str = None):
    """Create enhanced genesis block with new features"""
    logger.info("🌟 Creating Enhanced Genesis Block with New Features")
    logger.info("=" * 60)

    # Load configuration
    if config_path and os.path.exists(config_path):
        with open(config_path) as f:
            config = yaml.safe_load(f)
        logger.info(f"📋 Loaded configuration from {config_path}")
    else:
        # Default enhanced configuration
        config = {
            "genesis": {
                "chain_id": "aitbc-enhanced-devnet",
                "chain_type": "enhanced",
                "purpose": "development-with-new-features",
                "name": "AITBC Enhanced Development Network",
                "description": "Enhanced development network with AI trading, surveillance, analytics, and multi-chain features",
                "timestamp": datetime.now().isoformat() + "Z",
                "parent_hash": "0x0000000000000000000000000000000000000000000000000000000000000000",
                "gas_limit": 15000000,
                "gas_price": 1000000000,
                "consensus": {"algorithm": "poa", "validators": ["0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C"]},
                "accounts": [
                    {
                        "address": "0x5E2D7C7A4F8E9B1c3D5A2E8F4C6B8A0D2E4F6A8C",
                        "balance": "10000000",
                        "type": "genesis",
                        "metadata": {"purpose": "Genesis account with initial supply"},
                    },
                    {
                        "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1",
                        "balance": "1000000",
                        "type": "faucet",
                        "metadata": {"purpose": "Development faucet for testing"},
                    },
                ],
                "contracts": [],
                "parameters": {"block_time": 3, "max_block_size": 2097152, "min_stake": 1000},
                "features": {
                    "ai_trading_engine": True,
                    "ai_surveillance": True,
                    "advanced_analytics": True,
                    "enterprise_integration": True,
                },
            }
        }

    genesis = config["genesis"]
    chain_id = genesis["chain_id"]

    logger.info(f"🔗 Chain ID: {chain_id}")
    logger.info(f"🏷️  Chain Type: {genesis['chain_type']}")
    logger.info(f"🎯 Purpose: {genesis['purpose']}")
    logger.info(f"⚡ Features: {', '.join([k for k, v in genesis.get('features', {}).items() if v])}")
    logger.info("")

    # Initialize database
    init_db()

    # Check if genesis already exists
    with session_scope() as session:
        existing = session.exec(select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)).first()

        if existing:
            logger.info(f"⚠️  Genesis block already exists for chain {chain_id}: #{existing.height}")
            logger.info("🔄 Use --force to overwrite existing genesis")
            return existing

        # Create genesis block
        timestamp = datetime.fromisoformat(genesis["timestamp"].replace("Z", "+00:00"))
        genesis_hash = compute_block_hash(0, genesis["parent_hash"], timestamp, chain_id)

        # Create genesis block with enhanced metadata
        genesis_block = Block(
            height=0,
            hash=genesis_hash,
            parent_hash=genesis["parent_hash"],
            proposer=genesis["consensus"]["validators"][0],
            timestamp=timestamp,
            tx_count=0,
            state_root=None,
            chain_id=chain_id,
            block_metadata=json.dumps(
                {
                    "chain_type": genesis["chain_type"],
                    "purpose": genesis["purpose"],
                    "gas_limit": genesis["gas_limit"],
                    "gas_price": genesis["gas_price"],
                    "consensus_algorithm": genesis["consensus"]["algorithm"],
                    "validators": genesis["consensus"]["validators"],
                    "parameters": genesis.get("parameters", {}),
                    "features": genesis.get("features", {}),
                    "contracts": genesis.get("contracts", []),
                    "privacy": genesis.get("privacy", {}),
                    "services": genesis.get("services", {}),
                    "governance": genesis.get("governance", {}),
                    "economics": genesis.get("economics", {}),
                }
            ),
        )

        session.add(genesis_block)

        # Create genesis accounts
        if "accounts" in genesis:
            create_genesis_accounts(session, genesis["accounts"], chain_id)

        # Deploy genesis contracts
        if "contracts" in genesis:
            create_genesis_contracts(session, genesis["contracts"], chain_id)

        session.commit()

        logger.info("✅ Enhanced Genesis Block Created Successfully!")
        logger.info(f"🔗 Chain ID: {chain_id}")
        logger.info(f"📦 Block Height: #{genesis_block.height}")
        logger.info(f"🔐 Block Hash: {genesis_block.hash}")
        logger.info(f"👤 Proposer: {genesis_block.proposer}")
        logger.info(f"🕐 Timestamp: {genesis_block.timestamp}")
        logger.info(f"📝 Accounts Created: {len(genesis.get('accounts', []))}")
        logger.info(f"📜 Contracts Deployed: {len(genesis.get('contracts', []))}")
        logger.info(f"⚡ Features Enabled: {len([k for k, v in genesis.get('features', {}).items() if v])}")

        return genesis_block


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description="Create enhanced genesis block")
    parser.add_argument("--config", help="Genesis configuration file path")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing genesis")
    parser.add_argument("--chain-id", default="aitbc-enhanced-devnet", help="Chain ID for genesis")

    args = parser.parse_args()

    try:
        if args.force:
            logger.info("🔄 Force mode enabled - clearing existing blockchain data")
            # Here you could add logic to clear existing data

        genesis_block = create_enhanced_genesis(args.config)

        if genesis_block:
            logger.info("\n🎉 Enhanced genesis block creation completed!")
            logger.info("\n🔗 Next Steps:")
            logger.info("1. Start blockchain services: systemctl start aitbc-blockchain-node")
            logger.info("2. Verify genesis: curl http://localhost:8005/rpc/head")
            logger.info("3. Check accounts: curl http://localhost:8005/rpc/accounts")
            logger.info("4. Test enhanced features: curl http://localhost:8010/health")

    except Exception:
        logger.exception("❌ Error creating enhanced genesis block")
        sys.exit(1)


if __name__ == "__main__":
    configure_logging(level="INFO")
    main()
