---
description: Test and debug workflow for AITBC platform including OpenClaw agents and AI operations
title: AITBC Testing and Debugging Workflow
version: 3.0
auto_execution_mode: 3
---

# AITBC Testing and Debugging Workflow

This workflow helps you run tests and debug issues in the AITBC platform using the current consolidated project structure, including OpenClaw agents, AI operations, and modular workflows.

## Prerequisites

### Required Setup
- Working directory: `/opt/aitbc`
- Virtual environment: `/opt/aitbc/venv`
- CLI wrapper: `/opt/aitbc/aitbc-cli`
- Services running on correct ports (8000, 8001, 8006)
- OpenClaw 2026.3.24+ installed and gateway running

### Environment Setup
```bash
cd /opt/aitbc
source venv/bin/activate
./aitbc-cli --version
openclaw --version
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

### 2. Run OpenClaw Agent Tests
```bash
# Test OpenClaw gateway status
openclaw status --agent all

# Test basic agent communication
openclaw agent --agent main --message "Test communication" --thinking minimal

# Test session-based workflow
SESSION_ID="test-$(date +%s)"
openclaw agent --agent main --session-id $SESSION_ID --message "Initialize test session" --thinking low
openclaw agent --agent main --session-id $SESSION_ID --message "Continue test session" --thinking medium

# Test multi-agent coordination
openclaw agent --agent coordinator --message "Test coordination" --thinking high &
openclaw agent --agent worker --message "Test worker response" --thinking medium &
wait
```

### 3. Run AI Operations Tests
```bash
# Test AI job submission
cd /opt/aitbc
source venv/bin/activate
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Test AI job" --payment 10

# Monitor AI job status
./aitbc-cli ai-ops --action status --job-id "latest"

# Test resource allocation
./aitbc-cli resource allocate --agent-id test-agent --cpu 2 --memory 4096 --duration 3600

# Test marketplace operations
./aitbc-cli marketplace --action list
./aitbc-cli marketplace --action create --name "Test Service" --price 50 --wallet genesis-ops
```

### 5. Run Modular Workflow Tests
```bash
# Test core setup module
cd /opt/aitbc
source venv/bin/activate
./aitbc-cli chain
./aitbc-cli network

# Test operations module
systemctl status aitbc-blockchain-node.service aitbc-blockchain-rpc.service
python3 /tmp/aitbc1_heartbeat.py

# Test advanced features module
./aitbc-cli contract list
./aitbc-cli marketplace --action list

# Test production module
curl -s http://localhost:8006/health | jq .
ssh aitbc1 'curl -s http://localhost:8006/health | jq .'

# Test marketplace module
./aitbc-cli marketplace --action create --name "Test Service" --price 25 --wallet genesis-ops
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Test marketplace" --payment 25

# Test reference module
./aitbc-cli --help
./aitbc-cli list
./aitbc-cli balance --name genesis-ops
```

### 6. Run Advanced AI Operations Tests
```bash
# Test complex AI pipeline
SESSION_ID="advanced-test-$(date +%s)"
openclaw agent --agent main --session-id $SESSION_ID --message "Design complex AI pipeline for testing" --thinking high

# Test parallel AI operations
./aitbc-cli ai-submit --wallet genesis-ops --type parallel --prompt "Parallel AI test" --payment 100

# Test multi-model ensemble
./aitbc-cli ai-submit --wallet genesis-ops --type ensemble --models "resnet50,vgg16" --payment 200

# Test distributed AI economics
./aitbc-cli ai-submit --wallet genesis-ops --type distributed --nodes "aitbc,aitbc1" --payment 500

# Monitor advanced AI operations
./aitbc-cli ai-ops --action status --job-id "latest"
./aitbc-cli resource status
```

### 7. Run Cross-Node Coordination Tests
```bash
# Test cross-node blockchain sync
GENESIS_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FOLLOWER_HEIGHT=$(ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height)
echo "Height difference: $((FOLLOWER_HEIGHT - GENESIS_HEIGHT))"

# Test cross-node transactions
./aitbc-cli send --from genesis-ops --to follower-addr --amount 100 --password 123
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli balance --name follower-ops'

# Test smart contract messaging
curl -X POST http://localhost:8006/rpc/messaging/topics/create \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test", "agent_address": "address", "title": "Test", "description": "Test"}'

# Test cross-node AI coordination
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli ai-submit --wallet follower-ops --type inference --prompt "Cross-node test" --payment 50'
```

### 8. Run Integration Tests
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

### 12. Common Debug Commands
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

# Check OpenClaw functionality
openclaw --version
openclaw status --agent all

# Check AI operations
./aitbc-cli ai-ops --action status --job-id "latest"
./aitbc-cli resource status

# Check modular workflow status
curl -s http://localhost:8006/health | jq .
ssh aitbc1 'curl -s http://localhost:8006/health | jq .'
```

### 13. OpenClaw Agent Debugging
```bash
# Test OpenClaw gateway connectivity
openclaw status --agent all

# Debug agent communication
openclaw agent --agent main --message "Debug test" --thinking high

# Test session management
SESSION_ID="debug-$(date +%s)"
openclaw agent --agent main --session-id $SESSION_ID --message "Session debug test" --thinking medium

# Test multi-agent coordination
openclaw agent --agent coordinator --message "Debug coordination test" --thinking high &
openclaw agent --agent worker --message "Debug worker response" --thinking medium &
wait

# Check agent workspace
openclaw workspace --status
```

### 14. AI Operations Debugging
```bash
# Debug AI job submission
cd /opt/aitbc
source venv/bin/activate
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Debug test" --payment 10

# Monitor AI job execution
./aitbc-cli ai-ops --action status --job-id "latest"

# Debug resource allocation
./aitbc-cli resource allocate --agent-id debug-agent --cpu 1 --memory 2048 --duration 1800

# Debug marketplace operations
./aitbc-cli marketplace --action list
./aitbc-cli marketplace --action create --name "Debug Service" --price 5 --wallet genesis-ops
```

### 15. Performance Testing
```bash
# Run tests with performance profiling
cd /opt/aitbc
source venv/bin/activate
python -m pytest cli/tests/ --profile

# Load test coordinator API
ab -n 100 -c 10 http://localhost:8000/health

# Test blockchain RPC performance
time curl -s http://localhost:8006/rpc/head | python3 -m json.tool

# Test OpenClaw agent performance
time openclaw agent --agent main --message "Performance test" --thinking high

# Test AI operations performance
time ./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Performance test" --payment 10
```

### 16. Clean Test Environment
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

## Recent Updates (v3.0)

### New Testing Capabilities
- **OpenClaw Agent Testing**: Added comprehensive agent communication and coordination tests
- **AI Operations Testing**: Added AI job submission, resource allocation, and marketplace testing
- **Modular Workflow Testing**: Added testing for all 6 modular workflow components
- **Advanced AI Operations**: Added testing for complex AI pipelines and cross-node coordination
- **Cross-Node Coordination**: Added testing for distributed AI operations and blockchain messaging

### Enhanced Testing Structure
- **Multi-Agent Workflows**: Session-based agent coordination testing
- **AI Pipeline Testing**: Complex AI workflow orchestration testing
- **Distributed Testing**: Cross-node blockchain and AI operations testing
- **Performance Testing**: Added OpenClaw and AI operations performance benchmarks
- **Debugging Tools**: Enhanced troubleshooting for agent and AI operations

### Updated Project Structure
- **Working Directory**: `/opt/aitbc`
- **Virtual Environment**: `/opt/aitbc/venv`
- **CLI Wrapper**: `./aitbc-cli`
- **OpenClaw Integration**: OpenClaw 2026.3.24+ gateway and agents
- **Modular Workflows**: 6 focused workflow modules
- **Test Structure**: Updated to include agent and AI testing

### Service Port Updates
- **Coordinator API**: Port 8000
- **Exchange API**: Port 8001
- **Blockchain RPC**: Port 8006
- **Ollama**: Port 11434 (GPU operations)
- **OpenClaw Gateway**: Default port (configured in OpenClaw)

### Enhanced Testing Features
- **Agent Testing**: Multi-agent communication and coordination
- **AI Testing**: Job submission, monitoring, resource allocation
- **Workflow Testing**: Modular workflow component testing
- **Cross-Node Testing**: Distributed operations and coordination
- **Performance Testing**: Comprehensive performance benchmarking
- **Debugging**: Enhanced troubleshooting for all components

### Current Commands
- **CLI Commands**: Updated to use actual CLI implementation
- **OpenClaw Commands**: Agent communication and coordination
- **AI Operations**: Job submission, monitoring, marketplace
- **Service Management**: Updated to current systemd services
- **Modular Workflows**: Testing for all workflow modules
- **Environment**: Proper venv activation and usage

## Previous Updates (v2.0)

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