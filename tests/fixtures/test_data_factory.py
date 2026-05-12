"""
Test Data Factory
Provides comprehensive test data generation utilities for AITBC tests
"""

from datetime import UTC, datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import uuid4
import json


class TestDataFactory:
    """Factory for generating test data across different domains"""
    
    # Common test addresses
    TEST_ADDRESSES = {
        "alice": "aitbc1alice00000000000000000000000000000000000",
        "bob": "aitbc1bob0000000000000000000000000000000000000",
        "charlie": "aitbc1charl0000000000000000000000000000000000",
        "miner1": "aitbc1miner1000000000000000000000000000000000",
        "miner2": "aitbc1miner2000000000000000000000000000000000",
    }
    
    # Common test IDs
    @staticmethod
    def generate_id(prefix: str = "test") -> str:
        """Generate a unique test ID with prefix"""
        return f"{prefix}_{uuid4().hex[:8]}"
    
    @staticmethod
    def generate_timestamp(offset_seconds: int = 0) -> str:
        """Generate ISO timestamp with optional offset"""
        return (datetime.now(UTC) + timedelta(seconds=offset_seconds)).isoformat()
    
    # User/Identity data
    @staticmethod
    def user_data(
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        is_active: bool = True
    ) -> Dict[str, Any]:
        """Generate test user data"""
        return {
            "user_id": user_id or TestDataFactory.generate_id("user"),
            "email": email or "test@example.com",
            "username": "testuser",
            "is_active": is_active,
            "created_at": TestDataFactory.generate_timestamp(),
            "updated_at": TestDataFactory.generate_timestamp()
        }
    
    # Wallet data
    @staticmethod
    def wallet_data(
        address: Optional[str] = None,
        balance: float = 1000.0
    ) -> Dict[str, Any]:
        """Generate test wallet data"""
        return {
            "address": address or TestDataFactory.TEST_ADDRESSES["alice"],
            "balance": balance,
            "currency": "AITBC",
            "nonce": 0,
            "created_at": TestDataFactory.generate_timestamp()
        }
    
    # Job data
    @staticmethod
    def job_data(
        job_type: str = "ai_inference",
        priority: str = "normal",
        timeout: int = 300
    ) -> Dict[str, Any]:
        """Generate test job data"""
        return {
            "job_id": TestDataFactory.generate_id("job"),
            "job_type": job_type,
            "parameters": {
                "model": "gpt-4",
                "prompt": "Test prompt",
                "max_tokens": 100,
                "temperature": 0.7
            },
            "priority": priority,
            "timeout": timeout,
            "created_at": TestDataFactory.generate_timestamp(),
            "expires_at": TestDataFactory.generate_timestamp(offset_seconds=timeout)
        }
    
    # Transaction data
    @staticmethod
    def transaction_data(
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        amount: float = 100.0
    ) -> Dict[str, Any]:
        """Generate test transaction data"""
        return {
            "tx_id": TestDataFactory.generate_id("tx"),
            "sender": sender or TestDataFactory.TEST_ADDRESSES["alice"],
            "recipient": recipient or TestDataFactory.TEST_ADDRESSES["bob"],
            "amount": amount,
            "currency": "AITBC",
            "fee": 0.1,
            "timestamp": TestDataFactory.generate_timestamp(),
            "status": "pending"
        }
    
    # Miner data
    @staticmethod
    def miner_data(
        miner_id: Optional[str] = None,
        status: str = "active"
    ) -> Dict[str, Any]:
        """Generate test miner data"""
        return {
            "miner_id": miner_id or TestDataFactory.TEST_ADDRESSES["miner1"],
            "status": status,
            "total_jobs_completed": 10,
            "successful_jobs": 9,
            "average_accuracy": 95.0,
            "gpu_count": 4,
            "gpu_type": "NVIDIA A100",
            "last_heartbeat": TestDataFactory.generate_timestamp()
        }
    
    # GPU data
    @staticmethod
    def gpu_data(
        gpu_id: Optional[str] = None,
        status: str = "available"
    ) -> Dict[str, Any]:
        """Generate test GPU data"""
        return {
            "gpu_id": gpu_id or TestDataFactory.generate_id("gpu"),
            "status": status,
            "type": "NVIDIA A100",
            "memory_gb": 80,
            "compute_capability": 8.0,
            "price_per_hour": 2.5,
            "location": "us-east-1"
        }
    
    # Staking data
    @staticmethod
    def staking_data(
        amount: float = 1000.0,
        lock_period: int = 30,
        auto_compound: bool = False
    ) -> Dict[str, Any]:
        """Generate test staking data"""
        return {
            "stake_id": TestDataFactory.generate_id("stake"),
            "amount": amount,
            "lock_period": lock_period,
            "auto_compound": auto_compound,
            "apy": 5.0,
            "start_time": TestDataFactory.generate_timestamp(),
            "end_time": TestDataFactory.generate_timestamp(offset_seconds=lock_period * 86400),
            "status": "active"
        }
    
    # Agent data
    @staticmethod
    def agent_data(
        agent_id: Optional[str] = None,
        status: str = "active"
    ) -> Dict[str, Any]:
        """Generate test agent data"""
        return {
            "agent_id": agent_id or TestDataFactory.generate_id("agent"),
            "status": status,
            "type": "general",
            "capabilities": ["text_generation", "code_generation"],
            "performance_tier": "gold",
            "created_at": TestDataFactory.generate_timestamp()
        }
    
    # API request/response data
    @staticmethod
    def api_response(
        status_code: int = 200,
        data: Optional[Dict[str, Any]] = None,
        message: str = "Success"
    ) -> Dict[str, Any]:
        """Generate test API response"""
        return {
            "status_code": status_code,
            "data": data or {},
            "message": message,
            "timestamp": TestDataFactory.generate_timestamp()
        }
    
    # Error data
    @staticmethod
    def error_data(
        error_code: str = "INTERNAL_ERROR",
        error_message: str = "An error occurred",
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate test error data"""
        return {
            "error_code": error_code,
            "error_message": error_message,
            "details": details or {},
            "timestamp": TestDataFactory.generate_timestamp()
        }
    
    # Pagination data
    @staticmethod
    def paginated_response(
        items: List[Dict[str, Any]],
        page: int = 1,
        page_size: int = 10,
        total: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate test paginated response"""
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total or len(items),
            "total_pages": (total or len(items) + page_size - 1) // page_size
        }
    
    # Batch operations
    @staticmethod
    def batch_job_data(count: int = 5) -> List[Dict[str, Any]]:
        """Generate multiple job data for batch operations"""
        return [TestDataFactory.job_data() for _ in range(count)]
    
    @staticmethod
    def batch_transaction_data(count: int = 5) -> List[Dict[str, Any]]:
        """Generate multiple transaction data for batch operations"""
        return [TestDataFactory.transaction_data() for _ in range(count)]
    
    # Domain-specific scenarios
    @staticmethod
    def marketplace_offer_data(
        provider: Optional[str] = None,
        price: float = 1.5
    ) -> Dict[str, Any]:
        """Generate test marketplace offer data"""
        return {
            "offer_id": TestDataFactory.generate_id("offer"),
            "provider": provider or TestDataFactory.TEST_ADDRESSES["miner1"],
            "gpu_type": "NVIDIA A100",
            "memory_gb": 80,
            "price_per_hour": price,
            "availability": "immediate",
            "location": "us-east-1",
            "created_at": TestDataFactory.generate_timestamp()
        }
    
    @staticmethod
    def governance_proposal_data(
        title: str = "Test Proposal",
        description: str = "Test proposal description"
    ) -> Dict[str, Any]:
        """Generate test governance proposal data"""
        return {
            "proposal_id": TestDataFactory.generate_id("proposal"),
            "title": title,
            "description": description,
            "proposer": TestDataFactory.TEST_ADDRESSES["alice"],
            "status": "active",
            "votes_for": 0,
            "votes_against": 0,
            "created_at": TestDataFactory.generate_timestamp(),
            "ends_at": TestDataFactory.generate_timestamp(offset_seconds=86400 * 7)  # 7 days
        }
