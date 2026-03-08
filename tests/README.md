# AITBC Test Suite

This directory contains the comprehensive test suite for the AITBC platform, including unit tests, integration tests, end-to-end tests, security tests, and load tests.

## Table of Contents

1. [Test Structure](#test-structure)
2. [Prerequisites](#prerequisites)
3. [Running Tests](#running-tests)
4. [Test Types](#test-types)
5. [Configuration](#configuration)
6. [CI/CD Integration](#cicd-integration)
7. [Troubleshooting](#troubleshooting)

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── conftest_fixtures.py     # Comprehensive test fixtures
├── pytest.ini              # Pytest configuration
├── README.md               # This file
├── run_test_suite.py       # Test suite runner script
├── unit/                   # Unit tests
│   ├── test_coordinator_api.py
│   ├── test_wallet_daemon.py
│   └── test_blockchain_node.py
├── integration/            # Integration tests
│   ├── test_blockchain_node.py
│   └── test_full_workflow.py
├── e2e/                    # End-to-end tests
│   ├── test_wallet_daemon.py
│   └── test_user_scenarios.py
├── security/               # Security tests
│   ├── test_confidential_transactions.py
│   └── test_security_comprehensive.py
├── load/                   # Load tests
│   └── locustfile.py
└── fixtures/               # Test data and fixtures
    ├── sample_receipts.json
    └── test_transactions.json
```

## Prerequisites

### Required Dependencies

```bash
# Core testing framework
pip install pytest pytest-asyncio pytest-cov pytest-mock pytest-xdist

# Security testing
pip install bandit safety

# Load testing
pip install locust

# Additional testing tools
pip install requests-mock websockets psutil
```

### System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y postgresql redis-server

# macOS
brew install postgresql redis

# Docker (for isolated testing)
docker --version
```

### Environment Setup

1. Clone the repository:
```bash
git clone https://github.com/aitbc/aitbc.git
cd aitbc
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-test.txt
```

4. Set up test databases:
```bash
# PostgreSQL
createdb aitbc_test

# Redis (use test database 1)
redis-cli -n 1 FLUSHDB
```

5. Environment variables:
```bash
export DATABASE_URL="postgresql://localhost/aitbc_test"
export REDIS_URL="redis://localhost:6379/1"
export TEST_MODE="true"
```

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run using the test suite script (recommended)
python run_test_suite.py

# Run with coverage
python run_test_suite.py --coverage

# Run specific suite
python run_test_suite.py --suite unit
python run_test_suite.py --suite integration
python run_test_suite.py --suite e2e
python run_test_suite.py --suite security

# Run specific test file
pytest tests/unit/test_coordinator_api.py

# Run specific test class
pytest tests/unit/test_coordinator_api.py::TestJobEndpoints

# Run specific test method
pytest tests/unit/test_coordinator_api.py::TestJobEndpoints::test_create_job_success
```

### Running by Test Type

```bash
# Unit tests only (fast)
pytest -m unit

# Integration tests (require services)
pytest -m integration

# End-to-end tests (full system)
pytest -m e2e

# Security tests
pytest -m security

# Load tests (requires Locust)
locust -f tests/load/locustfile.py

# Performance tests
pytest -m performance

# GPU tests (requires GPU)
pytest -m gpu
```

### Parallel Execution

```bash
# Run with multiple workers
pytest -n auto

# Specify number of workers
pytest -n 4

# Distribute by test file
pytest --dist=loadfile
```

### Filtering Tests

```bash
# Run tests matching pattern
pytest -k "test_create_job"

# Run tests not matching pattern
pytest -k "not slow"

# Run tests with multiple markers
pytest -m "unit and not slow"

# Run tests with any of multiple markers
pytest -m "unit or integration"
```

## Test Types

### Unit Tests (`tests/unit/`)

Fast, isolated tests that test individual components:

- **Purpose**: Test individual functions and classes
- **Speed**: < 1 second per test
- **Dependencies**: Mocked external services
- **Database**: In-memory SQLite
- **Examples**:
  ```bash
  pytest tests/unit/ -v
  ```

### Integration Tests (`tests/integration/`)

Tests that verify multiple components work together:

- **Purpose**: Test component interactions
- **Speed**: 1-10 seconds per test
- **Dependencies**: Real services required
- **Database**: Test PostgreSQL instance
- **Examples**:
  ```bash
  # Start required services first
  docker-compose up -d postgres redis
  
  # Run integration tests
  pytest tests/integration/ -v
  ```

### End-to-End Tests (`tests/e2e/`)

Full system tests that simulate real user workflows:

- **Purpose**: Test complete user journeys
- **Speed**: 10-60 seconds per test
- **Dependencies**: Full system running
- **Database**: Production-like setup
- **Examples**:
  ```bash
  # Start full system
  docker-compose up -d
  
  # Run E2E tests
  pytest tests/e2e/ -v -s
  ```

### Security Tests (`tests/security/`)

Tests that verify security properties and vulnerability resistance:

- **Purpose**: Test security controls
- **Speed**: Variable (some are slow)
- **Dependencies**: May require special setup
- **Tools**: Bandit, Safety, Custom security tests
- **Examples**:
  ```bash
  # Run security scanner
  bandit -r apps/ -f json -o bandit-report.json
  
  # Run security tests
  pytest tests/security/ -v
  ```

### Load Tests (`tests/load/`)

Performance and scalability tests:

- **Purpose**: Test system under load
- **Speed**: Long-running (minutes)
- **Dependencies**: Locust, staging environment
- **Examples**:
  ```bash
  # Run Locust web UI
  locust -f tests/load/locustfile.py --web-host 127.0.0.1
  
  # Run headless
  locust -f tests/load/locustfile.py --headless -u 100 -r 10 -t 5m
  ```

## Configuration

### Pytest Configuration (`pytest.ini`)

Key configuration options:

```ini
[tool:pytest]
# Test paths
testpaths = tests
python_files = test_*.py

# Coverage settings
addopts = --cov=apps --cov=packages --cov-report=html

# Markers
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    security: Security tests
    slow: Slow tests
```

### Environment Variables

```bash
# Test configuration
export TEST_MODE=true
export TEST_DATABASE_URL="postgresql://localhost/aitbc_test"
export TEST_REDIS_URL="redis://localhost:6379/1"

# Service URLs for integration tests
export COORDINATOR_URL="http://localhost:8001"
export WALLET_URL="http://localhost:8002"
export BLOCKCHAIN_URL="http://localhost:8545"

# Security test configuration
export TEST_HSM_ENDPOINT="http://localhost:9999"
export TEST_ZK_CIRCUITS_PATH="./apps/zk-circuits"
```

### Test Data Management

```python
# Using fixtures in conftest.py
@pytest.fixture
def test_data():
    return {
        "sample_job": {...},
        "sample_receipt": {...},
    }

# Custom test configuration
@pytest.fixture(scope="session")
def test_config():
    return TestConfig(
        database_url="sqlite:///:memory:",
        redis_url="redis://localhost:6379/1",
    )
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python: "3.11"
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run unit tests
        run: |
          pytest tests/unit/ -v --cov=apps --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python: "3.11"
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run integration tests
        run: |
          pytest tests/integration/ -v
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost/postgres
          REDIS_URL: redis://localhost:6379/0
```

### Docker Compose for Testing

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: aitbc_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test"]
      interval: 5s
      timeout: 5s
      retries: 5
  
  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
  
  coordinator:
    build: ./apps/coordinator-api
    environment:
      DATABASE_URL: postgresql://test:test@postgres:5432/aitbc_test
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8001:8000"
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure PYTHONPATH is set
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   
   # Or install in development mode
   pip install -e .
   ```

2. **Database Connection Errors**
   ```bash
   # Check if PostgreSQL is running
   pg_isready -h localhost -p 5432
   
   # Create test database
   createdb -h localhost -p 5432 aitbc_test
   ```

3. **Redis Connection Errors**
   ```bash
   # Check if Redis is running
   redis-cli ping
   
   # Use correct database
   redis-cli -n 1 FLUSHDB
   ```

4. **Test Timeouts**
   ```bash
   # Increase timeout for slow tests
   pytest --timeout=600
   
   # Run tests sequentially
   pytest -n 0
   ```

5. **Port Conflicts**
   ```bash
   # Kill processes using ports
   lsof -ti:8001 | xargs kill -9
   lsof -ti:8002 | xargs kill -9
   ```

### Debugging Tests

```bash
# Run with verbose output
pytest -v -s

# Stop on first failure
pytest -x

# Run with pdb on failure
pytest --pdb

# Print local variables on failure
pytest --tb=long

# Run specific test with debugging
pytest tests/unit/test_coordinator_api.py::TestJobEndpoints::test_create_job_success -v -s --pdb
```

### Performance Issues

```bash
# Profile test execution
pytest --profile

# Find slowest tests
pytest --durations=10

# Run with memory profiling
pytest --memprof
```

### Test Data Issues

```bash
# Clean test database
psql -h localhost -U test -d aitbc_test -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Reset Redis
redis-cli -n 1 FLUSHALL

# Regenerate test fixtures
python tests/generate_fixtures.py
```

## Best Practices

1. **Write Isolated Tests**: Each test should be independent
2. **Use Descriptive Names**: Test names should describe what they test
3. **Mock External Dependencies**: Use mocks for external services
4. **Clean Up Resources**: Use fixtures for setup/teardown
5. **Test Edge Cases**: Don't just test happy paths
6. **Use Type Hints**: Makes tests more maintainable
7. **Document Complex Tests**: Add comments for complex logic

## Contributing

When adding new tests:

1. Follow the existing structure and naming conventions
2. Add appropriate markers (`@pytest.mark.unit`, etc.)
3. Update this README if adding new test types
4. Ensure tests pass on CI before submitting PR
5. Add coverage for new features

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Locust Documentation](https://docs.locust.io/)
- [Security Testing Guide](https://owasp.org/www-project-security-testing-guide/)
- [Load Testing Best Practices](https://docs.locust.io/en/stable/writing-a-locustfile.html)
