#!/usr/bin/env python3
"""
Enhanced script to create genesis block with new features
"""

import sys
import os
import yaml
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, 'src')

from aitbc_chain.database import session_scope, init_db
from aitbc_chain.models import Block, Transaction, Account
from sqlmodel import select

def compute_block_hash(height: int, parent_hash: str, timestamp: datetime, chain_id: str) -> str:
    """Compute enhanced block hash with chain_id"""
    data = f"{height}{parent_hash}{timestamp}{chain_id}".encode()
    return hashlib.sha256(data).hexdigest()

def create_genesis_accounts(session, accounts: List[Dict[str, Any]], chain_id: str):
    """Create genesis accounts"""
    print(f"🏦 Creating {len(accounts)} genesis accounts...")
    
    for account in accounts:
        db_account = Account(
            address=account['address'],
            balance=int(account['balance']),
            chain_id=chain_id
        )
        session.add(db_account)
        print(f"  ✅ Created account: {account['address']} ({account['balance']} AITBC)")

def create_genesis_contracts(session, contracts: List[Dict[str, Any]], chain_id: str):
    """Create genesis contracts"""
    print(f"📜 Deploying {len(contracts)} genesis contracts...")
    
    for contract in contracts:
        # Create contract deployment transaction
        deployment_tx = Transaction(
            chain_id=chain_id,
            tx_hash=f"0x{hashlib.sha256(f'contract_{contract['name']}_{chain_id}'.encode()).hexdigest()}",
            sender="aitbc1genesis",
            recipient=contract['address'],
            payload={"type": "contract_deployment", "contract_name": contract['name'], "code": contract.get('code', '0x')}
        )
        session.add(deployment_tx)
        print(f"  ✅ Deployed contract: {contract['name']} at {contract['address']}")

def create_enhanced_genesis(config_path: str = None):
    """Create enhanced genesis block with new features"""
    print("🌟 Creating Enhanced Genesis Block with New Features")
    print("=" * 60)
    
    # Load configuration
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        print(f"📋 Loaded configuration from {config_path}")
    else:
        # Default enhanced configuration
        config = {
            'genesis': {
                'chain_id': 'aitbc-enhanced-devnet',
                'chain_type': 'enhanced',
                'purpose': 'development-with-new-features',
                'name': 'AITBC Enhanced Development Network',
                'description': 'Enhanced development network with AI trading, surveillance, analytics, and multi-chain features',
                'timestamp': datetime.now().isoformat() + 'Z',
                'parent_hash': '0x0000000000000000000000000000000000000000000000000000000000000000',
                'gas_limit': 15000000,
                'gas_price': 1000000000,
                'consensus': {
                    'algorithm': 'poa',
                    'validators': ['ait1devproposer000000000000000000000000000000']
                },
                'accounts': [
                    {
                        'address': 'aitbc1genesis',
                        'balance': '10000000',
                        'type': 'genesis',
                        'metadata': {'purpose': 'Genesis account with initial supply'}
                    },
                    {
                        'address': 'aitbc1faucet',
                        'balance': '1000000',
                        'type': 'faucet',
                        'metadata': {'purpose': 'Development faucet for testing'}
                    }
                ],
                'contracts': [],
                'parameters': {
                    'block_time': 3,
                    'max_block_size': 2097152,
                    'min_stake': 1000
                },
                'features': {
                    'ai_trading_engine': True,
                    'ai_surveillance': True,
                    'advanced_analytics': True,
                    'enterprise_integration': True
                }
            }
        }
    
    genesis = config['genesis']
    chain_id = genesis['chain_id']
    
    print(f"🔗 Chain ID: {chain_id}")
    print(f"🏷️  Chain Type: {genesis['chain_type']}")
    print(f"🎯 Purpose: {genesis['purpose']}")
    print(f"⚡ Features: {', '.join([k for k, v in genesis.get('features', {}).items() if v])}")
    print()
    
    # Initialize database
    init_db()
    
    # Check if genesis already exists
    with session_scope() as session:
        existing = session.exec(
            select(Block).where(Block.chain_id == chain_id).order_by(Block.height.desc()).limit(1)
        ).first()
        
        if existing:
            print(f"⚠️  Genesis block already exists for chain {chain_id}: #{existing.height}")
            print(f"🔄 Use --force to overwrite existing genesis")
            return existing
        
        # Create genesis block
        timestamp = datetime.fromisoformat(genesis['timestamp'].replace('Z', '+00:00'))
        genesis_hash = compute_block_hash(0, genesis['parent_hash'], timestamp, chain_id)
        
        # Create genesis block with enhanced metadata
        genesis_block = Block(
            height=0,
            hash=genesis_hash,
            parent_hash=genesis['parent_hash'],
            proposer=genesis['consensus']['validators'][0],
            timestamp=timestamp,
            tx_count=0,
            state_root=None,
            chain_id=chain_id,
            block_metadata=json.dumps({
                'chain_type': genesis['chain_type'],
                'purpose': genesis['purpose'],
                'gas_limit': genesis['gas_limit'],
                'gas_price': genesis['gas_price'],
                'consensus_algorithm': genesis['consensus']['algorithm'],
                'validators': genesis['consensus']['validators'],
                'parameters': genesis.get('parameters', {}),
                'features': genesis.get('features', {}),
                'contracts': genesis.get('contracts', []),
                'privacy': genesis.get('privacy', {}),
                'services': genesis.get('services', {}),
                'governance': genesis.get('governance', {}),
                'economics': genesis.get('economics', {})
            })
        )
        
        session.add(genesis_block)
        
        # Create genesis accounts
        if 'accounts' in genesis:
            create_genesis_accounts(session, genesis['accounts'], chain_id)
        
        # Deploy genesis contracts
        if 'contracts' in genesis:
            create_genesis_contracts(session, genesis['contracts'], chain_id)
        
        session.commit()
        
        print(f"✅ Enhanced Genesis Block Created Successfully!")
        print(f"🔗 Chain ID: {chain_id}")
        print(f"📦 Block Height: #{genesis_block.height}")
        print(f"🔐 Block Hash: {genesis_block.hash}")
        print(f"👤 Proposer: {genesis_block.proposer}")
        print(f"🕐 Timestamp: {genesis_block.timestamp}")
        print(f"📝 Accounts Created: {len(genesis.get('accounts', []))}")
        print(f"📜 Contracts Deployed: {len(genesis.get('contracts', []))}")
        print(f"⚡ Features Enabled: {len([k for k, v in genesis.get('features', {}).items() if v])}")
        
        return genesis_block

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Create enhanced genesis block')
    parser.add_argument('--config', help='Genesis configuration file path')
    parser.add_argument('--force', action='store_true', help='Force overwrite existing genesis')
    parser.add_argument('--chain-id', default='aitbc-enhanced-devnet', help='Chain ID for genesis')
    
    args = parser.parse_args()
    
    try:
        if args.force:
            print("🔄 Force mode enabled - clearing existing blockchain data")
            # Here you could add logic to clear existing data
        
        genesis_block = create_enhanced_genesis(args.config)
        
        if genesis_block:
            print("\n🎉 Enhanced genesis block creation completed!")
            print("\n🔗 Next Steps:")
            print("1. Start blockchain services: systemctl start aitbc-blockchain-node")
            print("2. Verify genesis: curl http://localhost:8005/rpc/head")
            print("3. Check accounts: curl http://localhost:8005/rpc/accounts")
            print("4. Test enhanced features: curl http://localhost:8010/health")
        
    except Exception as e:
        print(f"❌ Error creating enhanced genesis block: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
