---
description: Test and debug workflow for AITBC platform
title: AITBC Testing and Debugging Workflow
version: 2.0
auto_execution_mode: 3
---

# AITBC Testing and Debugging Workflow

This workflow helps you run tests and debug issues in the AITBC platform using the current consolidated project structure.

## Prerequisites

### Required Setup
- Working directory: `/opt/aitbc`
- Virtual environment: `/opt/aitbc/venv`
- CLI wrapper: `/opt/aitbc/aitbc-cli`
- Services running on correct ports (8000, 8001, 8006)

### Environment Setup
```bash
cd /opt/aitbc
source venv/bin/activate
./aitbc-cli --version
```

## Testing Workflow

### 1. Run CLI Tests
```bash
# Run all CLI tests with current structure
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ -v --disable-warnings

# Run specific failing tests
python -m pytest cli/tests/test_cli_basic.py -v --tb=short

# Run with CLI test runner
cd cli/tests
python run_cli_tests.py

# Run marketplace tests
python -m pytest cli/tests/test_marketplace.py -v
```

### 2. Run Integration Tests
```bash
# Run all integration tests
cd /opt/aitbc
source venv/bin/activate
python -m pytest tests/ -v --no-cov

# Run with detailed output
python -m pytest tests/ -v --no-cov -s --tb=short

# Run specific integration test files
python -m pytest tests/integration/ -v --no-cov
```

### 3. Test CLI Commands with Current Structure
```bash
# Test CLI wrapper commands
./aitbc-cli --help
./aitbc-cli wallet --help
./aitbc-cli marketplace --help

# Test wallet commands
./aitbc-cli wallet create test-wallet
./aitbc-cli wallet list
./aitbc-cli wallet switch test-wallet
./aitbc-cli wallet balance

# Test marketplace commands
./aitbc-cli marketplace --action list
./aitbc-cli marketplace --action create --name "Test GPU" --price 0.25
./aitbc-cli marketplace --action search --name "GPU"

# Test blockchain commands
./aitbc-cli chain
./aitbc-cli node status
./aitbc-cli transaction list --limit 5
```

### 4. Run Specific Test Categories
```bash
# Unit tests
python -m pytest tests/unit/ -v

# Integration tests
python -m pytest tests/integration/ -v

# Package tests
python -m pytest packages/ -v

# Smart contract tests
python -m pytest packages/solidity/ -v

# CLI tests specifically
python -m pytest cli/tests/ -v
```

### 5. Debug Test Failures
```bash
# Run with pdb on failure
python -m pytest cli/tests/test_cli_basic.py::test_cli_help -v --pdb

# Run with verbose output and show local variables
python -m pytest cli/tests/ -v --tb=long -s

# Stop on first failure
python -m pytest cli/tests/ -v -x

# Run only failing tests
python -m pytest cli/tests/ -k "not test_cli_help" --disable-warnings
```

### 6. Check Test Coverage
```bash
# Run tests with coverage
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ --cov=cli/aitbc_cli --cov-report=html

# View coverage report
open htmlcov/index.html

# Coverage for specific modules
python -m pytest cli/tests/ --cov=cli.aitbc_cli.commands --cov-report=term-missing
```

### 7. Debug Services with Current Ports
```bash
# Check if coordinator API is running (port 8000)
curl -s http://localhost:8000/health | python3 -m json.tool

# Check if exchange API is running (port 8001)
curl -s http://localhost:8001/api/health | python3 -m json.tool

# Check if blockchain RPC is running (port 8006)
curl -s http://localhost:8006/health | python3 -m json.tool

# Check if marketplace is accessible
curl -s -o /dev/null -w %{http_code} http://aitbc.bubuit.net/marketplace/

# Check Ollama service (port 11434)
curl -s http://localhost:11434/api/tags | python3 -m json.tool
```

### 8. View Logs with Current Services
```bash
# View coordinator API logs
sudo journalctl -u aitbc-coordinator-api.service -f

# View exchange API logs
sudo journalctl -u aitbc-exchange-api.service -f

# View blockchain node logs
sudo journalctl -u aitbc-blockchain-node.service -f

# View blockchain RPC logs
sudo journalctl -u aitbc-blockchain-rpc.service -f

# View all AITBC services
sudo journalctl -u aitbc-* -f
```

### 9. Test Payment Flow Manually
```bash
# Create a job with AITBC payment using current ports
curl -X POST http://localhost:8000/v1/jobs \
  -H "X-Api-Key: client_dev_key_1" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "job_type": "ai_inference",
      "parameters": {"model": "llama3.2:latest", "prompt": "Test"}
    },
    "payment_amount": 100,
    "payment_currency": "AITBC"
  }'

# Check payment status
curl -s http://localhost:8000/v1/jobs/{job_id}/payment \
  -H "X-Api-Key: client_dev_key_1" | python3 -m json.tool
```

### 10. Common Debug Commands
```bash
# Check Python environment
cd /opt/aitbc
source venv/bin/activate
python --version
pip list | grep -E "(fastapi|sqlmodel|pytest|httpx|click|yaml)"

# Check database connection
ls -la /var/lib/aitbc/coordinator.db

# Check running services
systemctl status aitbc-coordinator-api.service
systemctl status aitbc-exchange-api.service
systemctl status aitbc-blockchain-node.service

# Check network connectivity
netstat -tlnp | grep -E "(8000|8001|8006|11434)"

# Check CLI functionality
./aitbc-cli --version
./aitbc-cli wallet list
./aitbc-cli chain
```

### 11. Performance Testing
```bash
# Run tests with performance profiling
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ --profile

# Load test coordinator API
ab -n 100 -c 10 http://localhost:8000/health

# Test blockchain RPC performance
time curl -s http://localhost:8006/rpc/head | python3 -m json.tool
```

### 12. Clean Test Environment
```bash
# Clean pytest cache
cd /opt/aitbc
rm -rf .pytest_cache

# Clean coverage files
rm -rf htmlcov .coverage

# Clean temp files
rm -rf temp/.coverage temp/.pytest_cache

# Reset test database (if using SQLite)
rm -f /var/lib/aitbc/test_coordinator.db
```

## Current Test Status

### CLI Tests (Updated Structure)
- **Location**: `cli/tests/`
- **Test Runner**: `run_cli_tests.py`
- **Basic Tests**: `test_cli_basic.py`
- **Marketplace Tests**: Available
- **Coverage**: CLI command testing

### Test Categories

#### Unit Tests
```bash
# Run unit tests only
cd /opt/aitbc
source venv/bin/activate
python -m pytest tests/unit/ -v
```

#### Integration Tests
```bash
# Run integration tests only
python -m pytest tests/integration/ -v --no-cov
```

#### Package Tests
```bash
# Run package tests
python -m pytest packages/ -v

# JavaScript package tests
cd packages/solidity/aitbc-token
npm test
```

#### Smart Contract Tests
```bash
# Run Solidity contract tests
cd packages/solidity/aitbc-token
npx hardhat test
```

## Troubleshooting

### Common Issues

1. **CLI Test Failures**
   - Check virtual environment activation
   - Verify CLI wrapper: `./aitbc-cli --help`
   - Check Python path: `which python`

2. **Service Connection Errors**
   - Check service status: `systemctl status aitbc-coordinator-api.service`
   - Verify correct ports: 8000, 8001, 8006
   - Check firewall settings

3. **Module Import Errors**
   - Activate virtual environment: `source venv/bin/activate`
   - Install dependencies: `pip install -r requirements.txt`
   - Check PYTHONPATH: `echo $PYTHONPATH`

4. **Package Test Failures**
   - JavaScript packages: Check npm and Node.js versions
   - Missing dependencies: Run `npm install`
   - Hardhat issues: Install missing ignition dependencies

### Debug Tips

1. Use `--pdb` to drop into debugger on failure
2. Use `-s` to see print statements
3. Use `--tb=long` for detailed tracebacks
4. Use `-x` to stop on first failure
5. Check service logs for errors
6. Verify environment variables are set

## Quick Test Commands

```bash
# Quick CLI test run
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ -x -q --disable-warnings

# Full test suite
python -m pytest tests/ --cov

# Debug specific test
python -m pytest cli/tests/test_cli_basic.py::test_cli_help -v -s

# Run only failing tests
python -m pytest cli/tests/ -k "not test_cli_help" --disable-warnings
```

## CI/CD Integration

### GitHub Actions Testing
```bash
# Test CLI in CI environment
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ -v --cov=cli/aitbc_cli --cov-report=xml

# Test packages
python -m pytest packages/ -v
cd packages/solidity/aitbc-token && npm test
```

### Local Development Testing
```bash
# Run tests before commits
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ --cov-fail-under=80

# Test specific changes
python -m pytest cli/tests/test_cli_basic.py -v
```

## Recent Updates (v2.0)

### Updated Project Structure
- **Working Directory**: Updated to `/opt/aitbc`
- **Virtual Environment**: Uses `/opt/aitbc/venv`
- **CLI Wrapper**: Uses `./aitbc-cli` for all operations
- **Test Structure**: Updated to `cli/tests/` organization

### Service Port Updates
- **Coordinator API**: Port 8000 (was 18000)
- **Exchange API**: Port 8001 (was 23000)
- **Blockchain RPC**: Port 8006 (was 20000)
- **Ollama**: Port 11434 (GPU operations)

### Enhanced Testing
- **CLI Test Runner**: Added custom test runner
- **Package Tests**: Added JavaScript package testing
- **Service Testing**: Updated service health checks
- **Coverage**: Enhanced coverage reporting

### Current Commands
- **CLI Commands**: Updated to use actual CLI implementation
- **Service Management**: Updated to current systemd services
- **Environment**: Proper venv activation and usage
- **Debugging**: Enhanced troubleshooting for current structure