# Cross-Container Multi-Chain Test Scenario

## 📋 Connected Resources

### **Testing Skill**
For comprehensive testing capabilities and automated test execution, see the **AITBC Testing Skill**:
```
/windsurf/skills/test
```

### **Test Workflow**
For step-by-step testing procedures and troubleshooting, see:
```
/windsurf/workflows/test
```

### **Tests Folder**
Complete test suite implementation located at:
```
tests/
├── cli/                    # CLI command testing
├── integration/            # Service integration testing
├── e2e/                   # End-to-end workflow testing
├── unit/                  # Unit component testing
├── contracts/             # Smart contract testing
├── performance/           # Performance and load testing
├── security/              # Security vulnerability testing
├── conftest.py           # Test configuration and fixtures
└── run_all_tests.sh      # Comprehensive test runner
```

## Multi-Chain Registration & Cross-Site Synchronization

### **Objective**
Test the new multi-chain capabilities across the live system where:
1. One single node instance hosts multiple independent chains (`ait-devnet`, `ait-testnet`, `ait-healthchain`)
2. Nodes across `aitbc` and `aitbc1` correctly synchronize independent chains using their `chain_id`

### **Test Architecture**
```
┌─────────────────┐    HTTP/8082     ┌─────────────────┐    HTTP/8082     ┌─────────────────┐
│   localhost     │ ◄──────────────► │     aitbc       │ ◄──────────────► │     aitbc1      │
│  (Test Client)  │   (Direct RPC)   │  (Primary Node) │   (P2P Gossip)   │ (Secondary Node)│
│                 │                  │                 │                  │                 │
│                 │                  │  • ait-devnet   │                  │  • ait-devnet   │
│                 │                  │  • ait-testnet  │                  │  • ait-testnet  │
│                 │                  │  • ait-healthch │                  │  • ait-healthch │
└─────────────────┘                  └─────────────────┘                  └─────────────────┘
```

### **Automated Test Execution**

#### Using the Testing Skill
```bash
# Execute multi-chain tests using the testing skill
skill test

# Run specific multi-chain test scenarios
python -m pytest tests/integration/test_multichain.py -v

# Run all tests including multi-chain scenarios
./scripts/testing/run_all_tests.sh
```

#### Using CLI for Testing
```bash
# Test CLI connectivity to multi-chain endpoints
cd /home/oib/windsurf/aitbc/cli
source venv/bin/activate

# Test health endpoint
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key health

# Test multi-chain status
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain chains
```

### **Test Phase 1: Multi-Chain Live Verification**

#### **1.1 Check Multi-Chain Status on aitbc**
```bash
# Verify multiple chains are active on aitbc node
curl -s "http://127.0.0.1:8000/v1/health" | jq .supported_chains

# Expected response:
# [
#   "ait-devnet",
#   "ait-testnet",
#   "ait-healthchain"
# ]

# Alternative using CLI
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain chains
```

#### **1.2 Verify Independent Genesis Blocks**
```bash
# Get genesis for devnet
curl -s "http://127.0.0.1:8082/rpc/blocks/0?chain_id=ait-devnet" | jq .hash

# Get genesis for testnet (should be different from devnet)
curl -s "http://127.0.0.1:8082/rpc/blocks/0?chain_id=ait-testnet" | jq .hash

# Get genesis for healthchain (should be different from others)
curl -s "http://127.0.0.1:8082/rpc/blocks/0?chain_id=ait-healthchain" | jq .hash

# Alternative using CLI
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain genesis --chain-id ait-devnet
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain genesis --chain-id ait-testnet
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain genesis --chain-id ait-healthchain
```

### **Test Phase 2: Isolated Transaction Processing**

#### **2.1 Submit Transaction to Specific Chain**
```bash
# Submit TX to healthchain
curl -s -X POST "http://127.0.0.1:8082/rpc/sendTx?chain_id=ait-healthchain" \
  -H "Content-Type: application/json" \
  -d '{"sender":"alice","recipient":"bob","payload":{"data":"medical_record"},"nonce":1,"fee":0,"type":"TRANSFER"}'

# Expected response:
# {
#   "tx_hash": "0x..."
# }

# Alternative using CLI
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain send \
  --chain-id ait-healthchain \
  --from alice \
  --to bob \
  --data "medical_record" \
  --nonce 1
```

#### **2.2 Verify Chain Isolation**
```bash
# Check mempool on healthchain (should have 1 tx)
curl -s "http://127.0.0.1:8082/rpc/mempool?chain_id=ait-healthchain"

# Check mempool on devnet (should have 0 tx)
curl -s "http://127.0.0.1:8082/rpc/mempool?chain_id=ait-devnet"

# Alternative using CLI
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain mempool --chain-id ait-healthchain
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain mempool --chain-id ait-devnet
```

### **Test Phase 3: Cross-Site Multi-Chain Synchronization**

#### **3.1 Verify Sync to aitbc1**
```bash
# Wait for block proposal (interval is 2s)
sleep 5

# Check block on aitbc (Primary)
curl -s "http://127.0.0.1:8082/rpc/head?chain_id=ait-healthchain" | jq .

# Check block on aitbc1 (Secondary) - Should match exactly
ssh aitbc1-cascade "curl -s \"http://127.0.0.1:8082/rpc/head?chain_id=ait-healthchain\"" | jq .

# Alternative using CLI
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key blockchain head --chain-id ait-healthchain
```

### **Test Phase 4: Automated Test Suite Execution**

#### **4.1 Run Complete Test Suite**
```bash
# Execute all tests including multi-chain scenarios
./scripts/testing/run_all_tests.sh

# Run specific multi-chain integration tests
python -m pytest tests/integration/test_multichain.py -v

# Run CLI tests with multi-chain support
python -m pytest tests/cli/test_cli_integration.py -v
```

#### **4.2 Test Result Validation**
```bash
# Generate test coverage report
python -m pytest tests/ --cov=. --cov-report=html

# View test results
open htmlcov/index.html

# Check specific test results
python -m pytest tests/integration/test_multichain.py::TestMultiChain::test_chain_isolation -v
```

## Integration with Test Framework

### **Test Configuration**
The multi-chain tests integrate with the main test framework through:

- **conftest.py**: Shared test fixtures and configuration
- **test_cli_integration.py**: CLI integration testing
- **test_integration/**: Service integration tests
- **run_all_tests.sh**: Comprehensive test execution

### **Environment Setup**
```bash
# Set up test environment for multi-chain testing
export PYTHONPATH="/home/oib/windsurf/aitbc/cli:/home/oib/windsurf/aitbc/packages/py/aitbc-core/src:/home/oib/windsurf/aitbc/packages/py/aitbc-crypto/src:/home/oib/windsurf/aitbc/packages/py/aitbc-sdk/src:/home/oib/windsurf/aitbc/apps/coordinator-api/src:$PYTHONPATH"
export TEST_MODE=true
export TEST_DATABASE_URL="sqlite:///:memory:"
export _AITBC_NO_RICH=1
```

### **Mock Services**
The test framework provides comprehensive mocking for:

- **HTTP Clients**: httpx.Client mocking for API calls
- **Blockchain Services**: Mock blockchain responses
- **Multi-Chain Coordination**: Mock chain synchronization
- **Cross-Site Communication**: Mock P2P gossip

## Test Automation

### **Continuous Integration**
```bash
# Automated test execution in CI/CD
name: Multi-Chain Tests
on: [push, pull_request]
jobs:
  multichain:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run Multi-Chain Tests
        run: |
          python -m pytest tests/integration/test_multichain.py -v
          python -m pytest tests/cli/test_cli_integration.py -v
```

### **Scheduled Testing**
```bash
# Regular multi-chain test execution
0 2 * * * cd /home/oib/windsurf/aitbc && ./scripts/testing/run_all_tests.sh
```

## Troubleshooting

### **Common Issues**
- **Connection Refused**: Check if coordinator API is running
- **Chain Not Found**: Verify chain configuration
- **Sync Failures**: Check P2P network connectivity
- **Test Failures**: Review test logs and configuration

### **Debug Mode**
```bash
# Run tests with debug output
python -m pytest tests/integration/test_multichain.py -v -s --tb=long

# Run specific test with debugging
python -m pytest tests/integration/test_multichain.py::TestMultiChain::test_chain_isolation -v -s --pdb
```

### **Service Status**
```bash
# Check coordinator API status
curl -s "http://127.0.0.1:8000/v1/health"

# Check blockchain node status
curl -s "http://127.0.0.1:8082/rpc/status"

# Check CLI connectivity
python -m aitbc_cli --url http://127.0.0.1:8000 --api-key test-key health
```

## Test Results and Reporting

### **Success Criteria**
- ✅ All chains are active and accessible
- ✅ Independent genesis blocks for each chain
- ✅ Chain isolation is maintained
- ✅ Cross-site synchronization works correctly
- ✅ CLI commands work with multi-chain setup

### **Failure Analysis**
- **Connection Issues**: Network connectivity problems
- **Configuration Errors**: Incorrect chain setup
- **Synchronization Failures**: P2P network issues
- **CLI Errors**: Command-line interface problems

### **Performance Metrics**
- **Test Execution Time**: <5 minutes for full suite
- **Chain Sync Time**: <10 seconds for block propagation
- **CLI Response Time**: <200ms for command execution
- **API Response Time**: <100ms for health checks

## Future Enhancements

### **Planned Improvements**
- **Visual Testing**: Multi-chain visualization
- **Load Testing**: High-volume transaction testing
- **Chaos Testing**: Network partition testing
- **Performance Testing**: Scalability testing

### **Integration Points**
- **Monitoring**: Real-time test monitoring
- **Alerting**: Test failure notifications
- **Dashboard**: Test result visualization
- **Analytics**: Test trend analysis
