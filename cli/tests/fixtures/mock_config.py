"""
Mock configuration data for testing
"""

MOCK_CONFIG_DATA = {
    "default": {
        "coordinator_url": "http://localhost:8000",
        "api_key": "test-api-key-12345",
        "timeout": 30,
        "blockchain_rpc_url": "http://localhost:8006",
        "wallet_url": "http://localhost:8002",
        "role": None,
        "output_format": "table"
    },
    "test_mode": {
        "coordinator_url": "http://localhost:8000",
        "api_key": "test-mode-key",
        "timeout": 30,
        "blockchain_rpc_url": "http://localhost:8006",
        "wallet_url": "http://localhost:8002",
        "role": "test",
        "output_format": "table"
    },
    "production": {
        "coordinator_url": "http://localhost:8000",
        "api_key": "prod-api-key",
        "timeout": 60,
        "blockchain_rpc_url": "http://localhost:8006",
        "wallet_url": "http://localhost:8002",
        "role": "client",
        "output_format": "json"
    }
}

MOCK_WALLET_DATA = {
    "test_wallet_1": {
        "name": "test-wallet-1",
        "address": "aitbc1test1234567890abcdef",
        "balance": 1000.0,
        "unlocked": 800.0,
        "staked": 200.0,
        "created_at": "2026-01-01T00:00:00Z",
        "encrypted": False,
        "type": "hd"
    },
    "test_wallet_2": {
        "name": "test-wallet-2",
        "address": "aitbc1test0987654321fedcba",
        "balance": 500.0,
        "unlocked": 500.0,
        "staked": 0.0,
        "created_at": "2026-01-02T00:00:00Z",
        "encrypted": True,
        "type": "simple"
    }
}

MOCK_AUTH_DATA = {
    "stored_credentials": {
        "client": {
            "default": "test-api-key-12345",
            "dev": "dev-api-key-67890",
            "staging": "staging-api-key-11111"
        },
        "miner": {
            "default": "miner-api-key-22222",
            "dev": "miner-dev-key-33333"
        },
        "admin": {
            "default": "admin-api-key-44444"
        }
    }
}

MOCK_BLOCKCHAIN_DATA = {
    "chain_info": {
        "chain_id": "ait-devnet",
        "height": 1000,
        "hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "parent_hash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "timestamp": "2026-01-01T00:00:00Z",
        "num_txs": 0,
        "gas_limit": 1000000,
        "gas_used": 0
    },
    "chain_status": {
        "status": "syncing",
        "height": 1000,
        "target_height": 1200,
        "sync_progress": 83.33,
        "peers": 5,
        "is_syncing": True,
        "last_block_time": "2026-01-01T00:00:00Z",
        "version": "1.0.0"
    },
    "genesis": {
        "chain_id": "ait-devnet",
        "height": 0,
        "hash": "0xc39391c65f000000000000000000000000000000000000000000000000000000",
        "parent_hash": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "timestamp": "2025-12-01T00:00:00Z",
        "num_txs": 0
    },
    "block": {
        "height": 1000,
        "hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "parent_hash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "timestamp": "2026-01-01T00:00:00Z",
        "num_txs": 3,
        "gas_limit": 1000000,
        "gas_used": 150000,
        "transactions": [
            {
                "hash": "0x1111111111111111111111111111111111111111111111111111111111111111",
                "from": "aitbc1test111111111111111111111111111111111111111111111111111111111",
                "to": "aitbc1test222222222222222222222222222222222222222222222222222222222",
                "amount": 100.0,
                "gas": 50000,
                "status": "success"
            },
            {
                "hash": "0x2222222222222222222222222222222222222222222222222222222222222222",
                "from": "aitbc1test333333333333333333333333333333333333333333333333333333333",
                "to": "aitbc1test444444444444444444444444444444444444444444444444444444444444",
                "amount": 50.0,
                "gas": 45000,
                "status": "success"
            },
            {
                "hash": "0x3333333333333333333333333333333333333333333333333333333333333333",
                "from": "aitbc1test555555555555555555555555555555555555555555555555555555555555",
                "to": "aitbc1test666666666666666666666666666666666666666666666666666666666666",
                "amount": 25.0,
                "gas": 55000,
                "status": "pending"
            }
        ]
    }
}

MOCK_NODE_DATA = {
    "node_info": {
        "id": "test-node-1",
        "address": "localhost:8006",
        "status": "active",
        "version": "1.0.0",
        "chains": ["ait-devnet"],
        "last_seen": "2026-01-01T00:00:00Z",
        "capabilities": ["rpc", "consensus", "mempool"]
    },
    "node_list": [
        {
            "id": "test-node-1",
            "address": "localhost:8006",
            "status": "active",
            "chains": ["ait-devnet"],
            "height": 1000
        },
        {
            "id": "test-node-2", 
            "address": "localhost:8007",
            "status": "syncing",
            "chains": ["ait-devnet"],
            "height": 950
        }
    ]
}

MOCK_CLIENT_DATA = {
    "job_submission": {
        "job_id": "job_1234567890abcdef",
        "status": "pending",
        "submitted_at": "2026-01-01T00:00:00Z",
        "type": "inference",
        "prompt": "What is machine learning?",
        "model": "gemma3:1b"
    },
    "job_result": {
        "job_id": "job_1234567890abcdef",
        "status": "completed",
        "result": "Machine learning is a subset of artificial intelligence...",
        "completed_at": "2026-01-01T00:05:00Z",
        "duration": 300.0,
        "miner_id": "miner_123",
        "cost": 0.25
    }
}

MOCK_MINER_DATA = {
    "miner_info": {
        "miner_id": "miner_123",
        "address": "aitbc1miner1234567890abcdef",
        "status": "active",
        "capabilities": {
            "gpu": True,
            "models": ["gemma3:1b", "llama3.2:latest"],
            "max_concurrent_jobs": 2
        },
        "earnings": {
            "total": 100.0,
            "today": 5.0,
            "jobs_completed": 25
        }
    },
    "miner_jobs": [
        {
            "job_id": "job_1111111111111111",
            "status": "completed",
            "submitted_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T00:02:00Z",
            "earnings": 0.10
        },
        {
            "job_id": "job_2222222222222222",
            "status": "running",
            "submitted_at": "2026-01-01T00:03:00Z",
            "started_at": "2026-01-01T00:03:30Z"
        }
    ]
}
