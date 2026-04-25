"""
Testing utilities for AITBC
Provides mock factories, test data generators, and test helpers
"""

import secrets
import json
from typing import Any, Dict, List, Optional, Type, TypeVar, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from decimal import Decimal
import uuid


T = TypeVar('T')


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
    def generate_user_data(**overrides) -> Dict[str, Any]:
        """Generate mock user data"""
        data = {
            "id": MockFactory.generate_uuid(),
            "email": MockFactory.generate_email(),
            "username": MockFactory.generate_string(8),
            "first_name": MockFactory.generate_string(6),
            "last_name": MockFactory.generate_string(6),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "is_active": True,
            "role": "user"
        }
        data.update(overrides)
        return data
    
    @staticmethod
    def generate_transaction_data(**overrides) -> Dict[str, Any]:
        """Generate mock transaction data"""
        data = {
            "id": MockFactory.generate_uuid(),
            "from_address": MockFactory.generate_ethereum_address(),
            "to_address": MockFactory.generate_ethereum_address(),
            "amount": str(secrets.randbelow(1000000000000000000)),
            "gas_price": str(secrets.randbelow(100000000000)),
            "gas_limit": secrets.randbelow(100000),
            "nonce": secrets.randbelow(1000),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "pending"
        }
        data.update(overrides)
        return data
    
    @staticmethod
    def generate_block_data(**overrides) -> Dict[str, Any]:
        """Generate mock block data"""
        data = {
            "number": secrets.randbelow(10000000),
            "hash": MockFactory.generate_hash(),
            "parent_hash": MockFactory.generate_hash(),
            "timestamp": datetime.utcnow().isoformat(),
            "transactions": [],
            "gas_used": str(secrets.randbelow(10000000)),
            "gas_limit": str(15000000),
            "miner": MockFactory.generate_ethereum_address()
        }
        data.update(overrides)
        return data
    
    @staticmethod
    def generate_api_key_data(**overrides) -> Dict[str, Any]:
        """Generate mock API key data"""
        data = {
            "id": MockFactory.generate_uuid(),
            "api_key": f"aitbc_{secrets.token_urlsafe(32)}",
            "user_id": MockFactory.generate_uuid(),
            "name": MockFactory.generate_string(10),
            "scopes": ["read", "write"],
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None,
            "is_active": True
        }
        data.update(overrides)
        return data
    
    @staticmethod
    def generate_wallet_data(**overrides) -> Dict[str, Any]:
        """Generate mock wallet data"""
        data = {
            "id": MockFactory.generate_uuid(),
            "address": MockFactory.generate_ethereum_address(),
            "chain_id": 1,
            "balance": str(secrets.randbelow(1000000000000000000)),
            "created_at": datetime.utcnow().isoformat(),
            "is_active": True
        }
        data.update(overrides)
        return data


class TestHelpers:
    """Helper functions for testing"""
    
    @staticmethod
    def assert_dict_contains(subset: Dict[str, Any], superset: Dict[str, Any]) -> bool:
        """Check if superset contains all key-value pairs from subset"""
        for key, value in subset.items():
            if key not in superset:
                return False
            if superset[key] != value:
                return False
        return True
    
    @staticmethod
    def assert_lists_equal_unordered(list1: List[Any], list2: List[Any]) -> bool:
        """Check if two lists contain the same elements regardless of order"""
        return sorted(list1) == sorted(list2)
    
    @staticmethod
    def compare_json_objects(obj1: Any, obj2: Any) -> bool:
        """Compare two JSON-serializable objects"""
        return json.dumps(obj1, sort_keys=True) == json.dumps(obj2, sort_keys=True)
    
    @staticmethod
    def wait_for_condition(
        condition: Callable[[], bool],
        timeout: float = 10.0,
        interval: float = 0.1
    ) -> bool:
        """Wait for a condition to become true"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            if condition():
                return True
            time.sleep(interval)
        return False
    
    @staticmethod
    def measure_execution_time(func: Callable, *args, **kwargs) -> tuple[Any, float]:
        """Measure execution time of a function"""
        import time
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        return result, elapsed
    
    @staticmethod
    def generate_test_file_path(extension: str = ".tmp") -> str:
        """Generate a unique test file path"""
        return f"/tmp/test_{secrets.token_hex(8)}{extension}"
    
    @staticmethod
    def cleanup_test_files(prefix: str = "test_") -> int:
        """Clean up test files in /tmp"""
        import os
        import glob
        count = 0
        for file_path in glob.glob(f"/tmp/{prefix}*"):
            try:
                os.remove(file_path)
                count += 1
            except:
                pass
        return count


class MockResponse:
    """Mock HTTP response for testing"""
    
    def __init__(
        self,
        status_code: int = 200,
        json_data: Optional[Dict[str, Any]] = None,
        text: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        """Initialize mock response"""
        self.status_code = status_code
        self._json_data = json_data
        self._text = text
        self.headers = headers or {}
    
    def json(self) -> Dict[str, Any]:
        """Return JSON data"""
        if self._json_data is None:
            raise ValueError("No JSON data available")
        return self._json_data
    
    def text(self) -> str:
        """Return text data"""
        if self._text is None:
            return ""
        return self._text
    
    def raise_for_status(self) -> None:
        """Raise exception if status code indicates error"""
        if self.status_code >= 400:
            raise Exception(f"HTTP Error: {self.status_code}")


class MockDatabase:
    """Mock database for testing"""
    
    def __init__(self):
        """Initialize mock database"""
        self.data: Dict[str, List[Dict[str, Any]]] = {}
        self.tables: List[str] = []
    
    def create_table(self, table_name: str) -> None:
        """Create a table"""
        if table_name not in self.tables:
            self.tables.append(table_name)
            self.data[table_name] = []
    
    def insert(self, table_name: str, record: Dict[str, Any]) -> None:
        """Insert a record"""
        if table_name not in self.tables:
            self.create_table(table_name)
        record['id'] = record.get('id', MockFactory.generate_uuid())
        self.data[table_name].append(record)
    
    def select(self, table_name: str, **filters) -> List[Dict[str, Any]]:
        """Select records with optional filters"""
        if table_name not in self.tables:
            return []
        
        records = self.data[table_name]
        if not filters:
            return records
        
        filtered = []
        for record in records:
            match = True
            for key, value in filters.items():
                if record.get(key) != value:
                    match = False
                    break
            if match:
                filtered.append(record)
        
        return filtered
    
    def update(self, table_name: str, record_id: str, updates: Dict[str, Any]) -> bool:
        """Update a record"""
        if table_name not in self.tables:
            return False
        
        for record in self.data[table_name]:
            if record.get('id') == record_id:
                record.update(updates)
                return True
        return False
    
    def delete(self, table_name: str, record_id: str) -> bool:
        """Delete a record"""
        if table_name not in self.tables:
            return False
        
        for i, record in enumerate(self.data[table_name]):
            if record.get('id') == record_id:
                del self.data[table_name][i]
                return True
        return False
    
    def clear(self) -> None:
        """Clear all data"""
        self.data.clear()
        self.tables.clear()


class MockCache:
    """Mock cache for testing"""
    
    def __init__(self, ttl: int = 3600):
        """Initialize mock cache"""
        self.cache: Dict[str, tuple[Any, float]] = {}
        self.ttl = ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key not in self.cache:
            return None
        
        value, timestamp = self.cache[key]
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache"""
        self.cache[key] = (value, time.time())
    
    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        if key in self.cache:
            del self.cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear cache"""
        self.cache.clear()
    
    def size(self) -> int:
        """Get cache size"""
        return len(self.cache)


def mock_async_call(return_value: Any = None, delay: float = 0):
    """Decorator to mock async calls with optional delay"""
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            if delay > 0:
                await asyncio.sleep(delay)
            return return_value
        return wrapper
    return decorator


def create_mock_config(**overrides) -> Dict[str, Any]:
    """Create mock configuration"""
    config = {
        "debug": False,
        "log_level": "INFO",
        "database_url": "sqlite:///test.db",
        "redis_url": "redis://localhost:6379",
        "api_host": "localhost",
        "api_port": 8080,
        "secret_key": MockFactory.generate_string(32),
        "max_workers": 4,
        "timeout": 30
    }
    config.update(overrides)
    return config


import time


def create_test_scenario(name: str, steps: List[Callable]) -> Callable:
    """Create a test scenario with multiple steps"""
    def scenario():
        print(f"Running test scenario: {name}")
        results = []
        for i, step in enumerate(steps):
            try:
                result = step()
                results.append({"step": i + 1, "status": "passed", "result": result})
            except Exception as e:
                results.append({"step": i + 1, "status": "failed", "error": str(e)})
        return results
    return scenario
