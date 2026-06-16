# Testing Scripts

This directory contains various test scripts and utilities for testing the AITBC platform.

## Test Scripts

### Block Import Tests
- **test_block_import.py** - Main block import endpoint test
- **test_block_import_complete.py** - Comprehensive block import test suite
- **test_simple_import.py** - Simple block import test
- **test_tx_import.py** - Transaction import test
- **test_tx_model.py** - Transaction model validation test
- **test_minimal.py** - Minimal test case
- **test_model_validation.py** - Model validation test

### Payment Tests
- **test_payment_integration.py** - Payment integration test suite
- **test_payment_local.py** - Local payment testing

### Test Runners
- **run_test_suite.py** - Main test suite runner
- **run_tests.py** - Simple test runner
- **verify_windsurf_tests.py** - Verify Windsurf test configuration
- **register_test_clients.py** - Register test clients for testing

## Usage

Most test scripts can be run directly with Python:
```bash
python3 test_block_import.py
```

Some scripts may require specific environment setup or configuration.
