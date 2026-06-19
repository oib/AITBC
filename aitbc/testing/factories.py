"""
Test Data Factories Module
Provides mock factories and test data generators
"""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class MockFactory:
    """Factory for creating mock objects for testing"""

    @staticmethod
    def generate_string(length: int = 10, prefix: str = "") -> str:
        """Generate a random string"""
        random_part = secrets.token_urlsafe(length)[:length]
        return f"{prefix}{random_part}"

    @staticmethod
    def generate_email() -> str:
        """Generate a random email address"""
        return f"{MockFactory.generate_string(8)}@example.com"

    @staticmethod
    def generate_url() -> str:
        """Generate a random URL"""
        return f"https://example.com/{MockFactory.generate_string(8)}"

    @staticmethod
    def generate_ip_address() -> str:
        """Generate a random IP address"""
        return f"192.168.{secrets.randbelow(256)}.{secrets.randbelow(256)}"

    @staticmethod
    def generate_ethereum_address() -> str:
        """Generate a random Ethereum address"""
        return f"0x{''.join(secrets.choice('0123456789abcdef') for _ in range(40))}"

    @staticmethod
    def generate_bitcoin_address() -> str:
        """Generate a random Bitcoin-like address"""
        return f"1{''.join(secrets.choice('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz') for _ in range(33))}"

    @staticmethod
    def generate_uuid() -> str:
        """Generate a UUID"""
        return str(uuid.uuid4())

    @staticmethod
    def generate_hash(length: int = 64) -> str:
        """Generate a random hash string"""
        return secrets.token_hex(length)[:length]


class TestDataGenerator:
    """Generate test data for various use cases"""

    @staticmethod
    def generate_user_data(**overrides) -> dict[str, Any]:
        """Generate mock user data"""
        data = {
            "id": MockFactory.generate_uuid(),
            "email": MockFactory.generate_email(),
            "username": MockFactory.generate_string(8),
            "first_name": MockFactory.generate_string(6),
            "last_name": MockFactory.generate_string(6),
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "is_active": True,
            "role": "user",
        }
        data.update(overrides)
        return data

    @staticmethod
    def generate_transaction_data(**overrides) -> dict[str, Any]:
        """Generate mock transaction data"""
        data = {
            "id": MockFactory.generate_uuid(),
            "from_address": MockFactory.generate_ethereum_address(),
            "to_address": MockFactory.generate_ethereum_address(),
            "amount": str(secrets.randbelow(1000000000000000000)),
            "gas_price": str(secrets.randbelow(100000000000)),
            "gas_limit": secrets.randbelow(100000),
            "nonce": secrets.randbelow(1000),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "pending",
        }
        data.update(overrides)
        return data

    @staticmethod
    def generate_block_data(**overrides) -> dict[str, Any]:
        """Generate mock block data"""
        data = {
            "number": secrets.randbelow(10000000),
            "hash": MockFactory.generate_hash(),
            "parent_hash": MockFactory.generate_hash(),
            "timestamp": datetime.now(UTC).isoformat(),
            "transactions": [],
            "gas_used": str(secrets.randbelow(10000000)),
            "gas_limit": str(15000000),
            "miner": MockFactory.generate_ethereum_address(),
        }
        data.update(overrides)
        return data

    @staticmethod
    def generate_api_key_data(**overrides) -> dict[str, Any]:
        """Generate mock API key data"""
        data = {
            "id": MockFactory.generate_uuid(),
            "api_key": f"aitbc_{secrets.token_urlsafe(32)}",
            "user_id": MockFactory.generate_uuid(),
            "name": MockFactory.generate_string(10),
            "scopes": ["read", "write"],
            "created_at": datetime.now(UTC).isoformat(),
            "last_used": None,
            "is_active": True,
        }
        data.update(overrides)
        return data

    @staticmethod
    def generate_wallet_data(**overrides) -> dict[str, Any]:
        """Generate mock wallet data"""
        data = {
            "id": MockFactory.generate_uuid(),
            "address": MockFactory.generate_ethereum_address(),
            "chain_id": 1,
            "balance": str(secrets.randbelow(1000000000000000000)),
            "created_at": datetime.now(UTC).isoformat(),
            "is_active": True,
        }
        data.update(overrides)
        return data
