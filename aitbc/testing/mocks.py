"""
Mock Objects Module
Provides mock implementations for testing
"""

import time
from typing import Any

from .factories import MockFactory


class MockResponse:
    """Mock HTTP response for testing"""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        """Initialize mock response"""
        self.status_code = status_code
        self._json_data = json_data
        self._text = text
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
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
        self.data: dict[str, list[dict[str, Any]]] = {}
        self.tables: list[str] = []

    def create_table(self, table_name: str) -> None:
        """Create a table"""
        if table_name not in self.tables:
            self.tables.append(table_name)
            self.data[table_name] = []

    def insert(self, table_name: str, record: dict[str, Any]) -> str:
        """Insert a record"""
        if table_name not in self.tables:
            self.create_table(table_name)
        record["id"] = record.get("id", MockFactory.generate_uuid())
        self.data[table_name].append(record)
        return record["id"]

    def select(self, table_name: str, **filters) -> list[dict[str, Any]]:
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

    def update(self, table_name: str, record_id: str, updates: dict[str, Any]) -> bool:
        """Update a record"""
        if table_name not in self.tables:
            return False

        for record in self.data[table_name]:
            if record.get("id") == record_id:
                record.update(updates)
                return True
        return False

    def delete(self, table_name: str, record_id: str) -> bool:
        """Delete a record"""
        if table_name not in self.tables:
            return False

        for i, record in enumerate(self.data[table_name]):
            if record.get("id") == record_id:
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
        self.cache: dict[str, tuple[Any, float]] = {}
        self.ttl = ttl

    def get(self, key: str) -> Any | None:
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
