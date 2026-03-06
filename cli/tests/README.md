# AITBC CLI Tests

This directory contains test scripts and utilities for the AITBC CLI tool.

## Test Structure

```
tests/
├── test_level1_commands.py          # Main level 1 commands test script
├── fixtures/                         # Test data and mocks
│   ├── mock_config.py              # Mock configuration data
│   ├── mock_responses.py           # Mock API responses
│   └── test_wallets/               # Test wallet files
├── utils/                           # Test utilities and helpers
│   ├── test_helpers.py             # Common test utilities
│   └── command_tester.py           # Enhanced command tester
├── integration/                     # Integration tests
├── multichain/                      # Multi-chain tests
├── gpu/                            # GPU-related tests
├── ollama/                         # Ollama integration tests
└── [other test files]              # Existing test files
```

## Level 1 Commands Test

The `test_level1_commands.py` script tests core CLI functionality:

### What are Level 1 Commands?
Level 1 commands are the primary command groups and their immediate subcommands:
- **Core groups**: wallet, config, auth, blockchain, client, miner
- **Essential groups**: version, help, test
- **Focus**: Command registration, help accessibility, basic functionality

### Test Categories

1. **Command Registration Tests**
   - Verify all level 1 command groups are registered
   - Test help accessibility for each command group
   - Check basic command structure and argument parsing

2. **Basic Functionality Tests**
   - Test config commands (show, set, get)
   - Test auth commands (login, logout, status)
   - Test wallet commands (create, list, address) in test mode
   - Test blockchain commands (info, status) with mock data

3. **Help System Tests**
   - Verify all subcommands have help text
   - Test argument validation and error messages
   - Check command aliases and shortcuts

### Running the Tests

#### As Standalone Script
```bash
cd /home/oib/windsurf/aitbc/cli
python tests/test_level1_commands.py
```

#### With pytest
```bash
cd /home/oib/windsurf/aitbc/cli
pytest tests/test_level1_commands.py -v
```

#### In Test Mode
```bash
cd /home/oib/windsurf/aitbc/cli
python tests/test_level1_commands.py --test-mode
```

### Test Features

- **Isolated Testing**: Each test runs in clean environment
- **Mock Data**: Safe testing without real blockchain/wallet operations
- **Comprehensive Coverage**: All level 1 commands and subcommands
- **Error Handling**: Test both success and failure scenarios
- **Output Validation**: Verify help text, exit codes, and response formats
- **Progress Indicators**: Detailed progress reporting during test execution
- **CI/CD Ready**: Proper exit codes and reporting for automation

### Expected Output

```
🚀 Starting AITBC CLI Level 1 Commands Test Suite
============================================================

📂 Testing Command Registration
----------------------------------------
✅ wallet: Registered
✅ config: Registered
✅ auth: Registered
...

📂 Testing Help System
----------------------------------------
✅ wallet --help: Help available
✅ config --help: Help available
...

📂 Testing Config Commands
----------------------------------------
✅ config show: Working
✅ config set: Working
...

📂 TESTING RESULTS SUMMARY
============================================================
Total Tests: 45
✅ Passed: 43
❌ Failed: 2
⏭️  Skipped: 0

🎯 Success Rate: 95.6%
🎉 EXCELLENT: CLI Level 1 commands are in great shape!
```

### Mock Data

The tests use comprehensive mock data to ensure safe testing:

- **Mock Configuration**: Test different config environments
- **Mock API Responses**: Simulated blockchain and service responses
- **Mock Wallet Data**: Test wallet operations without real wallets
- **Mock Authentication**: Test auth flows without real API keys

### Test Environment

Each test runs in an isolated environment:
- Temporary directories for config and wallets
- Mocked external dependencies (API calls, file system)
- Clean state between tests
- Automatic cleanup after test completion

### Extending the Tests

To add new tests:

1. Add test methods to the `Level1CommandTester` class
2. Use the provided utilities (`run_command_test`, `TestEnvironment`)
3. Follow the naming convention: `_test_[feature]`
4. Add the test to the appropriate category in `run_all_tests()`

### Troubleshooting

#### Common Issues

1. **Import Errors**: Ensure CLI path is added to sys.path
2. **Permission Errors**: Check temporary directory permissions
3. **Mock Failures**: Verify mock setup and patching
4. **Command Not Found**: Check command registration in main.py

#### Debug Mode

Run tests with verbose output:
```bash
python tests/test_level1_commands.py --debug
```

#### Individual Test Categories

Run specific test categories:
```bash
python -c "
from tests.test_level1_commands import Level1CommandTester
tester = Level1CommandTester()
tester.test_config_commands()
"
```

## Integration with CI/CD

The test script is designed for CI/CD integration:

- **Exit Codes**: 0 for success, 1 for failure
- **JSON Output**: Option for machine-readable results
- **Parallel Execution**: Can run multiple test suites in parallel
- **Docker Compatible**: Works in containerized environments

### GitHub Actions Example

```yaml
- name: Run CLI Level 1 Tests
  run: |
    cd cli
    python tests/test_level1_commands.py
```

## Contributing

When adding new CLI commands:

1. Update the test script to include the new command
2. Add appropriate mock responses
3. Test both success and error scenarios
4. Update this documentation

## Related Files

- `../aitbc_cli/main.py` - Main CLI entry point
- `../aitbc_cli/commands/` - Command implementations
- `docs/10_plan/06_cli/cli-checklist.md` - CLI command checklist
