---
description: Test and debug workflow for AITBC platform
auto_execution_mode: 3
---

# Test and Debug Workflow

This workflow helps you run tests and debug issues in the AITBC platform.

## Steps

### 1. Run All Integration Tests
```bash
# Run all integration tests
cd /home/oib/windsurf/aitbc
python -m pytest tests/integration/test_full_workflow.py -v --no-cov

# Run with detailed output
python -m pytest tests/integration/test_full_workflow.py -v --no-cov -s --tb=short
```

### 2. Run Specific Test Classes
```bash
# Test wallet payment flow
python -m pytest tests/integration/test_full_workflow.py::TestWalletToCoordinatorIntegration::test_job_payment_flow -v --no-cov -s

# Test marketplace integration
python -m pytest tests/integration/test_full_workflow.py::TestMarketplaceIntegration::test_service_listing_and_booking -v --no-cov -s

# Test security integration
python -m pytest tests/integration/test_full_workflow.py::TestSecurityIntegration::test_end_to_end_encryption -v --no-cov -s
```

### 3. Debug Test Failures
```bash
# Run with pdb on failure
python -m pytest tests/integration/test_full_workflow.py -v --no-cov --pdb

# Run with verbose output and show local variables
python -m pytest tests/integration/test_full_workflow.py -v --no-cov -s --tb=long

# Stop on first failure
python -m pytest tests/integration/test_full_workflow.py -v --no-cov -x
```

### 4. Check Test Coverage
```bash
# Run tests with coverage
python -m pytest tests/integration/test_full_workflow.py --cov=apps/coordinator-api --cov-report=html

# View coverage report
open htmlcov/index.html
```

### 5. Debug Services
```bash
# Check if coordinator API is running
curl http://localhost:18000/v1/health

# Check if wallet daemon is running
curl http://localhost:20000/api/v1/health

# Check if exchange is running
curl http://localhost:23000/api/health

# Check if marketplace is accessible
curl https://aitbc.bubuit.net/marketplace
```

### 6. View Logs
```bash
# View coordinator API logs
docker logs aitbc-coordinator-api -f

# View wallet daemon logs
docker logs aitbc-wallet-daemon -f

# View exchange logs
docker logs aitbc-exchange -f
```

### 7. Test Payment Flow Manually
```bash
# Create a job with AITBC payment
curl -X POST http://localhost:18000/v1/jobs \
  -H "X-Api-Key: REDACTED_CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "job_type": "ai_inference",
      "parameters": {"model": "gpt-4", "prompt": "Test"}
    },
    "payment_amount": 100,
    "payment_currency": "AITBC"
  }'

# Check payment status
curl http://localhost:18000/v1/jobs/{job_id}/payment \
  -H "X-Api-Key: REDACTED_CLIENT_KEY"
```

### 8. Common Debug Commands
```bash
# Check Python environment
python --version
pip list | grep -E "(fastapi|sqlmodel|pytest|httpx)"

# Check database connection
psql -h localhost -U aitbc -d aitbc -c "\dt"

# Check running services
ps aux | grep -E "(coordinator|wallet|exchange)"

# Check network connectivity
netstat -tlnp | grep -E "(18000|20000|23000)"
```

### 9. Performance Testing
```bash
# Run tests with performance profiling
python -m pytest tests/integration/test_full_workflow.py --profile

# Load test payment endpoints
ab -n 100 -c 10 http://localhost:18000/v1/health
```

### 10. Clean Test Environment
```bash
# Clean pytest cache
rm -rf .pytest_cache

# Clean coverage files
rm -rf htmlcov .coverage

# Reset test database
dropdb aitbc_test && createdb aitbc_test
```

## Troubleshooting

### Common Issues

1. **Import Error: No module named 'app.schemas.payments'**
   - The test is using mock client (expected in CI)
   - Real client requires full environment setup

2. **ModuleNotFoundError: No module named 'requests'**
   - Install requests: `pip install requests`
   - Check if in correct Python environment

3. **Connection Refused Errors**
   - Check if services are running on expected ports
   - Verify docker containers are up: `docker ps`

4. **Payment Test Fails**
   - Ensure wallet daemon is running
   - Check exchange API is accessible
   - Verify AITBC token balance

5. **Marketplace Test Fails**
   - Check internet connectivity
   - Verify marketplace URL is accessible
   - May need to skip if network issues

### Debug Tips

1. Use `--pdb` to drop into debugger on failure
2. Use `-s` to see print statements
3. Use `--tb=long` for detailed tracebacks
4. Use `-x` to stop on first failure
5. Check logs for service errors
6. Verify environment variables are set

## Test Categories

### Unit Tests
```bash
# Run unit tests only
python -m pytest tests/unit/ -v
```

### Integration Tests
```bash
# Run integration tests only
python -m pytest tests/integration/ -v
```

### End-to-End Tests
```bash
# Run e2e tests only
python -m pytest tests/e2e/ -v
```

### Security Tests
```bash
# Run security tests
python -m pytest tests/security/ -v
```

## Quick Test Commands

```bash
# Quick test run
pytest tests/ -x -q

# Full test suite
pytest tests/ --cov

# Debug specific test
pytest tests/integration/test_full_workflow.py::TestWalletToCoordinatorIntegration::test_job_payment_flow -v -s
```