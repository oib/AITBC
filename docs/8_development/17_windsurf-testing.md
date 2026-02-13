# Windsurf Testing Integration Guide

This guide explains how to use Windsurf's integrated testing features with the AITBC project.

## ✅ What's Been Configured

### 1. VS Code Settings (`.vscode/settings.json`)
- ✅ Pytest enabled (unittest disabled)
- ✅ Test discovery configured
- ✅ Auto-discovery on save enabled
- ✅ Debug port configured

### 2. Debug Configuration (`.vscode/launch.json`)
- ✅ Debug Python Tests
- ✅ Debug All Tests  
- ✅ Debug Current Test File
- ✅ Uses `debugpy` (not deprecated `python`)

### 3. Task Configuration (`.vscode/tasks.json`)
- ✅ Run All Tests
- ✅ Run Tests with Coverage
- ✅ Run Unit Tests Only
- ✅ Run Integration Tests
- ✅ Run Current Test File
- ✅ Run Test Suite Script

### 4. Pytest Configuration
- ✅ `pyproject.toml` - Main configuration with markers
- ✅ `pytest.ini` - Moved to project root with custom markers
- ✅ `tests/conftest.py` - Fixtures with fallback mocks

### 5. Test Scripts (2026-01-29)
- ✅ `scripts/testing/` - All test scripts moved here
- ✅ `test_ollama_blockchain.py` - Complete GPU provider test
- ✅ `test_block_import.py` - Blockchain block import testing

## 🚀 How to Use

### Test Discovery
1. Open Windsurf
2. Click the **Testing panel** (beaker icon in sidebar)
3. Tests will be automatically discovered
4. See all `test_*.py` files listed

### Running Tests

#### Option 1: Testing Panel
- Click the **play button** next to any test
- Click the **play button** at the top to run all tests
- Right-click on a test folder for more options

#### Option 2: Command Palette
- `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
- Search for "Python: Run All Tests"
- Or search for "Python: Run Test File"

#### Option 3: Tasks
- `Ctrl+Shift+P` → "Tasks: Run Test Task"
- Select the desired test task

#### Option 4: Keyboard Shortcuts
- `F5` - Debug current test
- `Ctrl+F5` - Run without debugging

### Debugging Tests
1. Click the **debug button** next to any test
2. Set breakpoints in your test code
3. Press `F5` to start debugging
4. Use the debug panel to inspect variables

### Test Coverage
1. Run the "Run Tests with Coverage" task
2. Open `htmlcov/index.html` in your browser
3. See detailed coverage reports

## 📁 Test Structure

```
tests/
├── test_basic_integration.py    # Basic integration tests
├── test_discovery.py           # Simple discovery tests
├── test_windsurf_integration.py # Windsurf integration tests
├── unit/                       # Unit tests
│   ├── test_coordinator_api.py
│   ├── test_wallet_daemon.py
│   └── test_blockchain_node.py
├── integration/                # Integration tests
│   └── test_full_workflow.py
├── e2e/                       # End-to-end tests
│   └── test_user_scenarios.py
└── security/                  # Security tests
    └── test_security_comprehensive.py
```

## 🏷️ Test Markers

Tests are marked with:
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.security` - Security tests
- `@pytest.mark.performance` - Performance tests

## 🔧 Troubleshooting

### Tests Not Discovered?
1. Check that files start with `test_*.py`
2. Verify pytest is enabled in settings
3. Run `python -m pytest --collect-only` to debug

### Import Errors?
1. The fixtures include fallback mocks
2. Check `tests/conftest.py` for path configuration
3. Use the mock clients if full imports fail

### Debug Not Working?
1. Ensure `debugpy` is installed
2. Check `.vscode/launch.json` uses `type: debugpy`
3. Verify test has a debug configuration

## 📝 Example Test

```python
import pytest
from unittest.mock import patch

@pytest.mark.unit
def test_example_function():
    """Example unit test"""
    result = add(2, 3)
    assert result == 5

@pytest.mark.integration
def test_api_endpoint(coordinator_client):
    """Example integration test using fixture"""
    response = coordinator_client.get("/docs")
    assert response.status_code == 200
```

## 🎯 Best Practices

1. **Use descriptive test names** - `test_specific_behavior`
2. **Add appropriate markers** - `@pytest.mark.unit`
3. **Use fixtures** - Don't repeat setup code
4. **Mock external dependencies** - Keep tests isolated
5. **Test edge cases** - Not just happy paths
6. **Keep tests fast** - Unit tests should be < 1 second

## 📊 Running Specific Tests

```bash
# Run all unit tests
pytest -m unit

# Run specific file
pytest tests/unit/test_coordinator_api.py

# Run with coverage
pytest --cov=apps tests/

# Run in parallel
pytest -n auto tests/
```

## 🎉 Success!

Your Windsurf testing integration is now fully configured! You can:
- Discover tests automatically
- Run tests with a click
- Debug tests visually
- Generate coverage reports
- Use all pytest features

Happy testing! 🚀

---

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
