# Windsurf Test Discovery Setup

## Issue
Unittest discovery errors when using Windsurf's test runner with the `tests/` folder.

## Solution
1. **Updated pyproject.toml** - Added `tests` to the testpaths configuration
2. **Created minimal conftest.py** - Removed complex imports that were causing discovery failures
3. **Test discovery now works** for files matching `test_*.py` pattern

## Current Status
- ✅ Test discovery works for simple tests (e.g., `tests/test_discovery.py`)
- ✅ All `test_*.py` files are discovered by pytest
- ⚠️ Tests with complex imports may fail during execution due to module path issues

## Running Tests

### For test discovery only (Windsurf integration):
```bash
cd /home/oib/windsurf/aitbc
python -m pytest --collect-only tests/
```

### For running all tests (with full setup):
```bash
cd /home/oib/windsurf/aitbc
python run_tests.py tests/
```

## Test Files Found
- `tests/e2e/test_wallet_daemon.py`
- `tests/integration/test_blockchain_node.py`
- `tests/security/test_confidential_transactions.py`
- `tests/unit/test_coordinator_api.py`
- `tests/test_discovery.py` (simple test file)

## Notes
- The original `conftest_full.py` contains complex fixtures requiring full module setup
- To run tests with full functionality, restore `conftest_full.py` and use the wrapper script
- For Windsurf's test discovery, the minimal `conftest.py` provides better experience
