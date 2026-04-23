# Test Infrastructure Documentation

## Overview

The AITBC project uses pytest-based testing with comprehensive coverage across all applications. The test infrastructure is organized by application complexity phases, with each app having unit, integration, and edge case tests.

## Test Structure

### Directory Organization

```
/opt/aitbc/
├── tests/
│   └── conftest.py                 # Global pytest configuration
└── apps/
    ├── <app-name>/
    │   └── tests/
    │       ├── __init__.py         # Test package marker
    │       ├── test_unit_<app>.py  # Unit tests (app-specific naming)
    │       ├── test_integration_<app>.py  # Integration tests (app-specific naming)
    │       └── test_edge_cases_<app>.py  # Edge case tests (app-specific naming)
```

### Test Types

1. **Unit Tests** (`test_unit_<app>.py`)
   - Test Pydantic models and data validation
   - Test app initialization
   - Test individual functions in isolation
   - Mock external dependencies

2. **Integration Tests** (`test_integration_<app>.py`)
   - Test API endpoints using FastAPI TestClient
   - Test database operations
   - Test component interactions
   - Use fixtures for state management

3. **Edge Case Tests** (`test_edge_cases_<app>.py`)
   - Test unusual inputs and boundary conditions
   - Test error handling
   - Test empty/invalid data scenarios
   - Test negative values and special characters

## Configuration

### Global Configuration (`tests/conftest.py`)

The global `conftest.py` manages:
- **Import paths**: Adds app source directories to `sys.path` for test discovery
- **Environment variables**: Sets `TEST_MODE=true`, `AUDIT_LOG_DIR`, `TEST_DATABASE_URL`
- **Mock dependencies**: Mocks optional dependencies like `slowapi`

```python
# Example import path configuration
sys.path.insert(0, str(project_root / "apps" / "app-name"))
```

### Per-App Fixtures

Each app can define fixtures in its test files:
- **Database reset**: For apps with databases (SQLite, PostgreSQL)
- **State cleanup**: For apps with in-memory state
- **Mock setup**: For external service dependencies

## Running Tests

### Run All Tests
```bash
python3 -m pytest apps/ -v
```

### Run Specific App Tests
```bash
python3 -m pytest apps/<app-name>/tests/ -v
```

### Run Specific Test File
```bash
python3 -m pytest apps/<app-name>/tests/test_unit_<app>.py -v
```

### Run Specific Test
```bash
python3 -m pytest apps/<app-name>/tests/test_unit_<app>.py::test_function_name -v
```

## Test Patterns

### Unit Test Pattern

```python
@pytest.mark.unit
def test_model_validation():
    """Test Pydantic model with valid data"""
    model = Model(field1="value", field2=123)
    assert model.field1 == "value"
    assert model.field2 == 123
```

### Integration Test Pattern

```python
@pytest.mark.integration
def test_api_endpoint():
    """Test API endpoint with TestClient"""
    from app import app
    client = TestClient(app)
    response = client.get("/api/endpoint")
    assert response.status_code == 200
    data = response.json()
    assert data["field"] == "expected_value"
```

### Edge Case Test Pattern

```python
@pytest.mark.unit
def test_model_empty_field():
    """Test model with empty field"""
    model = Model(field1="", field2=123)
    assert model.field1 == ""
```

## Mocking External Dependencies

### HTTP Requests

```python
from unittest.mock import patch, Mock

@pytest.mark.integration
@patch('app.httpx.get')
def test_external_api_call(mock_get):
    """Test with mocked HTTP request"""
    mock_get.return_value = Mock(status_code=200, json=lambda: {"data": "value"})
    result = function_that_calls_http()
    assert result is not None
```

### Subprocess Calls

```python
@patch('app.subprocess.run')
def test_subprocess_command(mock_run):
    """Test with mocked subprocess"""
    mock_run.return_value = Mock(stdout="output", returncode=0)
    result = function_that_calls_subprocess()
    assert result is not None
```

### Time Delays

```python
@patch('app.time.sleep')
def test_with_delay(mock_sleep):
    """Test without actual delay"""
    mock_sleep.return_value = None
    result = function_with_delay()
    assert result is not None
```

## Database Handling

### SQLite Apps

For apps using SQLite:
- Use in-memory databases for tests
- Delete database file before/after tests
- Use fixtures to reset state

```python
@pytest.fixture(autouse=True)
def reset_db():
    """Reset database before each test"""
    db_path = Path("database.db")
    if db_path.exists():
        db_path.unlink()
    
    init_db()
    yield
    
    if db_path.exists():
        db_path.unlink()
```

### PostgreSQL Apps

For apps using PostgreSQL:
- Set `TEST_DATABASE_URL` to use test database
- Use transactions and rollback
- Clean up test data

## Coverage Summary

### Phase 1: Simple Apps (7 apps, 201 tests)
- monitor, ai-engine, simple-explorer, zk-circuits
- exchange-integration, compliance-service, plugin-registry
- Test files renamed with app-specific suffixes (e.g., test_unit_monitor.py)

### Phase 2: Medium Apps (7 apps, 260 tests)
- trading-engine, plugin-security, plugin-analytics
- global-infrastructure, plugin-marketplace
- multi-region-load-balancer, global-ai-agents
- Test files renamed with app-specific suffixes (e.g., test_unit_trading_engine.py)

### Phase 3: Complex Apps (4 apps)
- miner (44 tests) - GPU miner with coordinator communication
- marketplace (49 tests) - Agent-first GPU marketplace
- agent-services (22 tests) - Agent registry and coordination
- blockchain-explorer (46 tests) - Blockchain exploration UI
- Test files renamed with app-specific suffixes (e.g., test_unit_miner.py)

### Phase 4: Most Complex App (1 app, 27 tests)
- exchange - Full trading exchange with database
- Test files renamed with app-specific suffixes (e.g., test_unit_exchange.py)

## Best Practices

1. **Use descriptive test names**: `test_function_scenario_expected_result`
2. **Group related tests**: Use pytest markers (`@pytest.mark.unit`, `@pytest.mark.integration`)
3. **Mock external dependencies**: Never call external services in tests
4. **Clean up state**: Use fixtures to reset state between tests
5. **Test error cases**: Test both success and failure scenarios
6. **Keep tests isolated**: Each test should be independent
7. **Use type hints**: Improve test readability and IDE support
8. **Document edge cases**: Explain why a particular edge case is being tested

## Common Issues and Solutions

### Import Errors

**Problem**: Module not found when running tests
**Solution**: Add app path to `sys.path` in `tests/conftest.py`

```python
sys.path.insert(0, str(project_root / "apps" / "app-name"))
```

### Import File Conflicts

**Problem**: Pytest import conflicts when running all apps together due to identical test file names
**Solution**: Test files renamed with app-specific suffixes (e.g., `test_unit_marketplace.py`) to avoid module naming collisions

### Database Lock Issues

**Problem**: Tests fail due to database locks
**Solution**: Use in-memory databases or delete database files in fixtures

### Async Function Errors

**Problem**: Tests fail when calling async functions
**Solution**: Use `TestClient` for FastAPI apps, or mark tests with `@pytest.mark.asyncio`

### Stuck Tests

**Problem**: Test hangs indefinitely
**Solution**: Mock `time.sleep` or reduce retry delays in tests

```python
@patch('app.time.sleep')
def test_with_delay(mock_sleep):
    mock_sleep.return_value = None
    # test code
```

## Pydantic v2 Compatibility

For apps using Pydantic v2:
- Replace `.dict()` with `.model_dump()`
- Use `from_attributes = True` in model Config
- Update validation patterns as needed

## Continuous Integration

Tests are integrated into CI workflows:
- `python-tests.yml` - Generic Python test runner
- `api-endpoint-tests.yml` - API endpoint testing
- Tests run on every pull request
- Coverage reports are generated

## Future Enhancements

- Add performance benchmarking tests
- Add load testing for API endpoints
- Add contract testing for external service integrations
- Increase code coverage targets
- Add property-based testing with Hypothesis
