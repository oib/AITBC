# Test Configuration Refactoring - Usage Guide

## 🚀 Quick Start

The AITBC test suite has been refactored to eliminate the shell script smell and use proper pytest configuration in `pyproject.toml`. We standardize on Python 3.13 for all testing and use SQLite exclusively for database testing.

### **Basic Usage**

```bash
# Run all fast tests (default)
pytest

# Run with the convenient test runner
python tests/test_runner.py

# Run all tests including slow ones
python tests/test_runner.py --all

# Run with coverage
python tests/test_runner.py --coverage
```

### **Test Categories**

```bash
# Unit tests only
pytest -m "unit"
python tests/test_runner.py --unit

# Integration tests only
pytest -m "integration"
python tests/test_runner.py --integration

# CLI tests only
pytest -m "cli"
python tests/test_runner.py --cli

# API tests only
pytest -m "api"
python tests/test_runner.py --api

# Blockchain tests only
pytest -m "blockchain"
python tests/test_runner.py --blockchain

# Slow tests only
pytest -m "slow"
python tests/test_runner.py --slow

# Performance tests only
pytest -m "performance"
python tests/test_runner.py --performance

# Security tests only
pytest -m "security"
python tests/test_runner.py --security
```

### **Advanced Usage**

```bash
# Run specific test files
pytest tests/cli/test_agent_commands.py
pytest apps/coordinator-api/tests/test_api.py

# Run with verbose output
pytest -v
python tests/test_runner.py --verbose

# Run with coverage
pytest --cov=aitbc_cli --cov-report=term-missing
python tests/test_runner.py --coverage

# List available tests
pytest --collect-only
python tests/test_runner.py --list

# Show available markers
pytest --markers
python tests/test_runner.py --markers

# Run with specific Python path
pytest --pythonpath=cli

# Run with custom options
pytest -v --tb=short --disable-warnings
```

## 📋 Test Markers

The test suite uses the following markers to categorize tests:

| Marker | Description | Usage |
|--------|-------------|-------|
| `unit` | Unit tests (fast, isolated) | `pytest -m unit` |
| `integration` | Integration tests (may require external services) | `pytest -m integration` |
| `cli` | CLI command tests | `pytest -m cli` |
| `api` | API endpoint tests | `pytest -m api` |
| `blockchain` | Blockchain-related tests | `pytest -m blockchain` |
| `crypto` | Cryptography tests | `pytest -m crypto` |
| `contracts` | Smart contract tests | `pytest -m contracts` |
| `slow` | Slow running tests | `pytest -m slow` |
| `performance` | Performance tests | `pytest -m performance` |
| `security` | Security tests | `pytest -m security` |
| `gpu` | Tests requiring GPU resources | `pytest -m gpu` |
| `e2e` | End-to-end tests | `pytest -m e2e` |

## 🗂️ Test Discovery

The test suite automatically discovers tests in these directories:

- `tests/` - Main test directory
- `apps/*/tests/` - Application tests
- `cli/tests/` - CLI tests
- `contracts/test/` - Smart contract tests
- `packages/*/tests/` - Package tests
- `scripts/test/` - Script tests

## 🔧 Configuration

All test configuration is now in `pyproject.toml` with SQLite as the default database:

```toml
[tool.pytest.ini_options]
python_files = ["test_*.py", "*_test.py"]
testpaths = ["tests", "apps/*/tests", "cli/tests", ...]
addopts = ["--verbose", "--tb=short", "--strict-markers", "--disable-warnings", "-ra"]
env = [
    "DATABASE_URL=sqlite:///./test_coordinator.db",
    "SQLITE_DATABASE=sqlite:///./test_coordinator.db"
]
markers = [
    "unit: Unit tests (fast, isolated)",
    "integration: Integration tests (may require external services)",
    # ... more markers
]
```

## 🚦 CI/CD Integration

The CI workflows now call pytest directly:

```yaml
- name: Run tests
  run: pytest --cov=aitbc_cli --cov-report=xml
```

## 📊 Coverage

```bash
# Run with coverage
pytest --cov=aitbc_cli --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=aitbc_cli --cov-report=html

# Coverage for specific module
pytest --cov=aitbc_cli.commands.agent --cov-report=term-missing
```

## 🐛 Troubleshooting

### **Common Issues**

**Import errors:**
```bash
# Check python path
python -c "import sys; print(sys.path)"

# Run with explicit python path
PYTHONPATH=cli pytest
```

**Test discovery issues:**
```bash
# Check what tests are discovered
pytest --collect-only

# Check configuration
python -c "import pytest; print(pytest.config.getini('testpaths'))"
```

**Coverage issues:**
```bash
# Check coverage configuration
pytest --cov=aitbc_cli --cov-report=term-missing --debug

# Verify coverage source
python -c "import coverage; print(coverage.Coverage().source)"
```

### **Migration from Shell Script**

**Before:**
```bash
./tests/run_all_tests.sh
```

**After:**
```bash
pytest
# or
python tests/test_runner.py
```

## 🎯 Best Practices

### **For Developers**

1. **Use appropriate markers**: Mark your tests with the correct category
2. **Keep unit tests fast**: Unit tests should not depend on external services
3. **Use fixtures**: Leverage pytest fixtures for setup/teardown
4. **Write descriptive tests**: Use clear test names and descriptions

### **Test Writing Example**

```python
import pytest

@pytest.mark.unit
def test_cli_command_help():
    """Test CLI help command."""
    # Test implementation
    
@pytest.mark.integration
@pytest.mark.slow
def test_blockchain_sync():
    """Test blockchain synchronization."""
    # Test implementation
    
@pytest.mark.cli
def test_agent_create_command():
    """Test agent creation CLI command."""
    # Test implementation
```

### **Running Tests During Development**

```bash
# Quick feedback during development
pytest -m "unit" -v

# Run tests for specific module
pytest tests/cli/test_agent_commands.py -v

# Run tests with coverage for your changes
pytest --cov=aitbc_cli --cov-report=term-missing

# Run tests before committing
python tests/test_runner.py --coverage
```

## 📈 Performance Tips

### **Fast Test Execution**

```bash
# Run only unit tests for quick feedback
pytest -m "unit" -v

# Use parallel execution (if pytest-xdist is installed)
pytest -n auto -m "unit"

# Skip slow tests during development
pytest -m "not slow"
```

### **Memory Usage**

```bash
# Run tests with minimal output
pytest -q

# Use specific test paths to reduce discovery overhead
pytest tests/cli/
```

## 🔍 Debugging

### **Debug Mode**

```bash
# Run with debug output
pytest --debug

# Run with pdb on failure
pytest --pdb

# Run with verbose output
pytest -v -s
```

### **Test Selection**

```bash
# Run specific test
pytest tests/cli/test_agent_commands.py::test_agent_create

# Run tests matching pattern
pytest -k "agent_create"

# Run failed tests only
pytest --lf
```

## 📚 Additional Resources

- **pytest documentation**: https://docs.pytest.org/
- **pytest-cov documentation**: https://pytest-cov.readthedocs.io/
- **pytest-mock documentation**: https://pytest-mock.readthedocs.io/
- **AITBC Development Guidelines**: See `docs/DEVELOPMENT_GUIDELINES.md`

---

**Migration completed**: ✅ All test configuration moved to `pyproject.toml`  
**Shell script eliminated**: ✅ No more `run_all_tests.sh` dependency  
**CI/CD updated**: ✅ Direct pytest integration in workflows  
**Developer experience improved**: ✅ Simplified test execution
