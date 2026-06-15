"""Tests for aitbc.testing utilities"""

import asyncio

from aitbc.testing import (
    MockCache,
    MockDatabase,
    MockFactory,
    MockResponse,
    TestDataGenerator,
    TestHelpers,
    create_mock_config,
    create_test_scenario,
    mock_async_call,
)


class TestMockFactory:
    def test_generate_string(self):
        s = MockFactory.generate_string(10)
        assert len(s) == 10

    def test_generate_string_with_prefix(self):
        s = MockFactory.generate_string(5, prefix="pre_")
        assert s.startswith("pre_")
        assert len(s) == 9

    def test_generate_email(self):
        email = MockFactory.generate_email()
        assert "@example.com" in email

    def test_generate_url(self):
        url = MockFactory.generate_url()
        assert url.startswith("https://example.com/")

    def test_generate_ip_address(self):
        ip = MockFactory.generate_ip_address()
        assert ip.startswith("192.168.")

    def test_generate_ethereum_address(self):
        addr = MockFactory.generate_ethereum_address()
        assert addr.startswith("0x")
        assert len(addr) == 42

    def test_generate_bitcoin_address(self):
        addr = MockFactory.generate_bitcoin_address()
        assert addr.startswith("1")
        assert len(addr) == 34

    def test_generate_uuid(self):
        uid = MockFactory.generate_uuid()
        assert len(uid) == 36

    def test_generate_hash(self):
        h = MockFactory.generate_hash(64)
        assert len(h) == 64


class TestTestDataGenerator:
    def test_generate_user_data(self):
        data = TestDataGenerator.generate_user_data()
        assert "id" in data
        assert "email" in data
        assert data["is_active"] is True

    def test_generate_user_data_override(self):
        data = TestDataGenerator.generate_user_data(username="testuser")
        assert data["username"] == "testuser"

    def test_generate_transaction_data(self):
        data = TestDataGenerator.generate_transaction_data()
        assert "from_address" in data
        assert "to_address" in data
        assert data["status"] == "pending"

    def test_generate_block_data(self):
        data = TestDataGenerator.generate_block_data()
        assert "number" in data
        assert "hash" in data
        assert "transactions" in data

    def test_generate_api_key_data(self):
        data = TestDataGenerator.generate_api_key_data()
        assert "api_key" in data
        assert "scopes" in data

    def test_generate_wallet_data(self):
        data = TestDataGenerator.generate_wallet_data()
        assert "address" in data
        assert "balance" in data


class TestTestHelpers:
    def test_assert_dict_contains_true(self):
        assert TestHelpers.assert_dict_contains({"a": 1}, {"a": 1, "b": 2}) is True

    def test_assert_dict_contains_missing_key(self):
        assert TestHelpers.assert_dict_contains({"c": 1}, {"a": 1}) is False

    def test_assert_dict_contains_wrong_value(self):
        assert TestHelpers.assert_dict_contains({"a": 2}, {"a": 1}) is False

    def test_assert_lists_equal_unordered(self):
        assert TestHelpers.assert_lists_equal_unordered([1, 2, 3], [3, 2, 1]) is True

    def test_compare_json_objects(self):
        assert TestHelpers.compare_json_objects({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True

    def test_compare_json_objects_different(self):
        assert TestHelpers.compare_json_objects({"a": 1}, {"a": 2}) is False

    def test_wait_for_condition(self):
        flag = {"ready": True}
        result = TestHelpers.wait_for_condition(lambda: flag["ready"], timeout=0.5)
        assert result is True

    def test_wait_for_condition_timeout(self):
        result = TestHelpers.wait_for_condition(lambda: False, timeout=0.1, interval=0.01)
        assert result is False

    def test_measure_execution_time(self):
        result, elapsed = TestHelpers.measure_execution_time(lambda: 42)
        assert result == 42
        assert elapsed >= 0

    def test_generate_test_file_path(self):
        path = TestHelpers.generate_test_file_path(".txt")
        assert path.startswith("/tmp/test_")
        assert path.endswith(".txt")


class TestMockResponse:
    def test_json(self):
        resp = MockResponse(json_data={"key": "value"})
        assert resp.json() == {"key": "value"}

    def test_json_none(self):
        resp = MockResponse()
        try:
            resp.json()
            assert False
        except ValueError:
            pass

    def test_text(self):
        resp = MockResponse(text="hello")
        assert resp.text() == "hello"

    def test_text_default(self):
        resp = MockResponse()
        assert resp.text() == ""

    def test_raise_for_status_ok(self):
        resp = MockResponse(status_code=200)
        resp.raise_for_status()

    def test_raise_for_status_error(self):
        resp = MockResponse(status_code=500)
        try:
            resp.raise_for_status()
            assert False
        except Exception as e:
            assert "500" in str(e)


class TestMockDatabase:
    def test_create_table(self):
        db = MockDatabase()
        db.create_table("users")
        assert "users" in db.tables

    def test_insert_and_select(self):
        db = MockDatabase()
        db.insert("users", {"name": "Alice"})
        records = db.select("users")
        assert len(records) == 1
        assert records[0]["name"] == "Alice"
        assert "id" in records[0]

    def test_select_with_filter(self):
        db = MockDatabase()
        db.insert("users", {"name": "Alice", "role": "admin"})
        db.insert("users", {"name": "Bob", "role": "user"})
        records = db.select("users", role="admin")
        assert len(records) == 1
        assert records[0]["name"] == "Alice"

    def test_select_empty_table(self):
        db = MockDatabase()
        records = db.select("users")
        assert records == []

    def test_update(self):
        db = MockDatabase()
        rid = db.insert("users", {"name": "Alice"})
        result = db.update("users", rid, {"name": "Alicia"})
        assert result is True
        assert db.select("users")[0]["name"] == "Alicia"

    def test_update_not_found(self):
        db = MockDatabase()
        result = db.update("users", "missing", {"name": "Alicia"})
        assert result is False

    def test_delete(self):
        db = MockDatabase()
        rid = db.insert("users", {"name": "Alice"})
        result = db.delete("users", rid)
        assert result is True
        assert db.select("users") == []

    def test_delete_not_found(self):
        db = MockDatabase()
        result = db.delete("users", "missing")
        assert result is False

    def test_clear(self):
        db = MockDatabase()
        db.insert("users", {"name": "Alice"})
        db.clear()
        assert db.tables == []
        assert db.data == {}


class TestMockCache:
    def test_set_and_get(self):
        cache = MockCache()
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_get_missing(self):
        cache = MockCache()
        assert cache.get("missing") is None

    def test_delete(self):
        cache = MockCache()
        cache.set("key", "value")
        assert cache.delete("key") is True
        assert cache.get("key") is None

    def test_delete_missing(self):
        cache = MockCache()
        assert cache.delete("missing") is False

    def test_clear(self):
        cache = MockCache()
        cache.set("a", 1)
        cache.clear()
        assert cache.size() == 0

    def test_size(self):
        cache = MockCache()
        assert cache.size() == 0
        cache.set("a", 1)
        assert cache.size() == 1

    def test_ttl_expiration(self):
        cache = MockCache(ttl=0)
        cache.set("key", "value")
        assert cache.get("key") is None


class TestMockAsyncCall:
    def test_mock_async_call(self):
        @mock_async_call(return_value=42)
        async def my_func():
            return 0

        result = asyncio.run(my_func())
        assert result == 42


class TestCreateMockConfig:
    def test_default_config(self):
        config = create_mock_config()
        assert config["debug"] is False
        assert config["log_level"] == "INFO"

    def test_override(self):
        config = create_mock_config(debug=True, api_port=9090)
        assert config["debug"] is True
        assert config["api_port"] == 9090


class TestCreateTestScenario:
    def test_scenario_all_pass(self):
        scenario = create_test_scenario("test", [lambda: 1, lambda: 2])
        results = scenario()
        assert len(results) == 2
        assert all(r["status"] == "passed" for r in results)

    def test_scenario_with_failure(self):
        scenario = create_test_scenario("test", [lambda: 1, lambda: (_ for _ in ()).throw(Exception("fail"))])
        results = scenario()
        assert results[1]["status"] == "failed"
