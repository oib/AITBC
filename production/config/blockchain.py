import os
from pathlib import Path

# Production Blockchain Configuration
BLOCKCHAIN_CONFIG = {
    'network': {
        'name': 'aitbc-mainnet',
        'chain_id': 1337,
        'consensus': 'proof_of_authority',
        'block_time': 5,  # seconds
        'gas_limit': 8000000,
        'difficulty': 'auto'
    },
    'nodes': {
        'aitbc': {
            'host': 'localhost',
            'port': 8545,
            'rpc_port': 8545,
            'p2p_port': 30303,
            'data_dir': '/var/lib/aitbc/data/blockchain/aitbc'
        },
        'aitbc1': {
            'host': 'aitbc1',
            'port': 8545,
            'rpc_port': 8545,
            'p2p_port': 30303,
            'data_dir': '/var/lib/aitbc/data/blockchain/aitbc1'
        }
    },
    'security': {
        'enable_tls': True,
        'cert_path': '/opt/aitbc/production/config/certs',
        'require_auth': True,
        'api_key': os.getenv('BLOCKCHAIN_API_KEY', 'production-key-change-me')
    }
}
