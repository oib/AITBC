"""
Mock API responses for testing
"""

import json
from typing import Dict, Any


class MockApiResponse:
    """Mock API response generator"""
    
    @staticmethod
    def success_response(data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a successful API response"""
        return {
            "status": "success",
            "data": data,
            "timestamp": "2026-01-01T00:00:00Z"
        }
    
    @staticmethod
    def error_response(message: str, code: int = 400) -> Dict[str, Any]:
        """Generate an error API response"""
        return {
            "status": "error",
            "error": message,
            "code": code,
            "timestamp": "2026-01-01T00:00:00Z"
        }
    
    @staticmethod
    def blockchain_info() -> Dict[str, Any]:
        """Mock blockchain info response"""
        return MockApiResponse.success_response({
            "chain_id": "ait-devnet",
            "height": 1000,
            "hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            "parent_hash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "timestamp": "2026-01-01T00:00:00Z",
            "num_txs": 0,
            "gas_limit": 1000000,
            "gas_used": 0,
            "validator_count": 5,
            "total_supply": 1000000.0
        })
    
    @staticmethod
    def blockchain_status() -> Dict[str, Any]:
        """Mock blockchain status response"""
        return MockApiResponse.success_response({
            "status": "syncing",
            "height": 1000,
            "target_height": 1200,
            "sync_progress": 83.33,
            "peers": 5,
            "is_syncing": True,
            "last_block_time": "2026-01-01T00:00:00Z",
            "version": "1.0.0",
            "network_id": "testnet-1"
        })
    
    @staticmethod
    def wallet_balance() -> Dict[str, Any]:
        """Mock wallet balance response"""
        return MockApiResponse.success_response({
            "address": "aitbc1test1234567890abcdef",
            "balance": 1000.0,
            "unlocked": 800.0,
            "staked": 200.0,
            "rewards": 50.0,
            "last_updated": "2026-01-01T00:00:00Z"
        })
    
    @staticmethod
    def wallet_list() -> Dict[str, Any]:
        """Mock wallet list response"""
        return MockApiResponse.success_response({
            "wallets": [
                {
                    "name": "test-wallet-1",
                    "address": "aitbc1test1234567890abcdef",
                    "balance": 1000.0,
                    "type": "hd",
                    "created_at": "2026-01-01T00:00:00Z"
                },
                {
                    "name": "test-wallet-2",
                    "address": "aitbc1test0987654321fedcba",
                    "balance": 500.0,
                    "type": "simple",
                    "created_at": "2026-01-02T00:00:00Z"
                }
            ]
        })
    
    @staticmethod
    def auth_status() -> Dict[str, Any]:
        """Mock auth status response"""
        return MockApiResponse.success_response({
            "authenticated": True,
            "api_key": "test-api-key-12345",
            "environment": "default",
            "role": "client",
            "expires_at": "2026-12-31T23:59:59Z"
        })
    
    @staticmethod
    def node_info() -> Dict[str, Any]:
        """Mock node info response"""
        return MockApiResponse.success_response({
            "id": "test-node-1",
            "address": "localhost:8006",
            "status": "active",
            "version": "1.0.0",
            "chains": ["ait-devnet"],
            "last_seen": "2026-01-01T00:00:00Z",
            "capabilities": ["rpc", "consensus", "mempool"],
            "uptime": 86400,
            "memory_usage": "256MB",
            "cpu_usage": "15%"
        })
    
    @staticmethod
    def job_submitted() -> Dict[str, Any]:
        """Mock job submitted response"""
        return MockApiResponse.success_response({
            "job_id": "job_1234567890abcdef",
            "status": "pending",
            "submitted_at": "2026-01-01T00:00:00Z",
            "type": "inference",
            "prompt": "What is machine learning?",
            "model": "gemma3:1b",
            "estimated_cost": 0.25,
            "queue_position": 1
        })
    
    @staticmethod
    def job_result() -> Dict[str, Any]:
        """Mock job result response"""
        return MockApiResponse.success_response({
            "job_id": "job_1234567890abcdef",
            "status": "completed",
            "result": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.",
            "completed_at": "2026-01-01T00:05:00Z",
            "duration": 300.0,
            "miner_id": "miner_123",
            "cost": 0.25,
            "receipt_id": "receipt_789",
            "tokens_generated": 150
        })
    
    @staticmethod
    def miner_status() -> Dict[str, Any]:
        """Mock miner status response"""
        return MockApiResponse.success_response({
            "miner_id": "miner_123",
            "address": "aitbc1miner1234567890abcdef",
            "status": "active",
            "registered_at": "2026-01-01T00:00:00Z",
            "capabilities": {
                "gpu": True,
                "models": ["gemma3:1b", "llama3.2:latest"],
                "max_concurrent_jobs": 2,
                "memory_gb": 8,
                "gpu_memory_gb": 6
            },
            "current_jobs": 1,
            "earnings": {
                "total": 100.0,
                "today": 5.0,
                "jobs_completed": 25,
                "average_per_job": 4.0
            },
            "last_heartbeat": "2026-01-01T00:00:00Z"
        })


# Response mapping for easy lookup
MOCK_RESPONSES = {
    "blockchain_info": MockApiResponse.blockchain_info,
    "blockchain_status": MockApiResponse.blockchain_status,
    "wallet_balance": MockApiResponse.wallet_balance,
    "wallet_list": MockApiResponse.wallet_list,
    "auth_status": MockApiResponse.auth_status,
    "node_info": MockApiResponse.node_info,
    "job_submitted": MockApiResponse.job_submitted,
    "job_result": MockApiResponse.job_result,
    "miner_status": MockApiResponse.miner_status
}


def get_mock_response(response_type: str) -> Dict[str, Any]:
    """Get a mock response by type"""
    if response_type in MOCK_RESPONSES:
        return MOCK_RESPONSES[response_type]()
    else:
        return MockApiResponse.error_response(f"Unknown response type: {response_type}")


def create_mock_http_response(response_data: Dict[str, Any], status_code: int = 200):
    """Create a mock HTTP response object"""
    class MockHttpResponse:
        def __init__(self, data, status):
            self.status_code = status
            self._data = data
        
        def json(self):
            return self._data
        
        @property
        def text(self):
            return json.dumps(self._data)
    
    return MockHttpResponse(response_data, status_code)
