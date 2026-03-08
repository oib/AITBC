# Enhanced Services End-to-End Tests

This directory contains comprehensive end-to-end tests for the AITBC enhanced services, validating complete workflows, performance benchmarks, and system integration.

## 📁 Directory Structure

```
tests/e2e/
├── fixtures/                    # Test fixtures and mock data
│   ├── home/                   # Mock agent home directories
│   │   ├── client1/            # Client agent home
│   │   └── miner1/            # Miner agent home
│   └── __init__.py            # Fixture utilities and classes
├── conftest.py                 # Pytest configuration
├── conftest_fixtures.py        # Extended fixture configuration
├── test_*.py                   # Individual test files
└── README.md                   # This file
```

## 🎯 Test Coverage

### Test Suites

#### 1. **Enhanced Services Workflows** (`test_enhanced_services_workflows.py`)
- **Multi-Modal Processing Workflow**: Complete text → image → optimization → learning → edge deployment → marketplace pipeline
- **GPU Acceleration Workflow**: GPU availability, cross-modal attention, multi-modal fusion, performance comparison
- **Marketplace Transaction Workflow**: NFT minting, listing, bidding, execution, royalties, analytics

#### 2. **Client-to-Miner Workflow** (`test_client_miner_workflow.py`)
- **Complete Pipeline**: Client request → agent workflow creation → execution → monitoring → verification → marketplace submission
- **Service Integration**: Tests communication between all enhanced services
- **Real-world Scenarios**: Validates actual usage patterns

#### 3. **Performance Benchmarks** (`test_performance_benchmarks.py`)
- **Multi-Modal Performance**: Text, image, audio, video processing times and accuracy
- **GPU Acceleration**: Speedup validation for CUDA operations
- **Marketplace Performance**: Transaction processing, royalty calculation times
- **Concurrent Performance**: Load testing with multiple concurrent requests

## 🔧 Test Fixtures

### Home Directory Fixtures

The `tests/e2e/fixtures/home/` directory contains mock home directories for testing agent scenarios:

```python
# Using fixture home directories
def test_agent_workflow(test_home_dirs):
    client_home = test_home_dirs / "client1"
    miner_home = test_home_dirs / "miner1"
    
    # Test agent operations using mock home directories
```

### Available Fixtures

- **`test_home_dirs`**: Access to fixture home directories
- **`temp_home_dirs`**: Temporary home directories for isolated testing
- **`home_dir_fixture`**: Manager for creating custom home directory setups
- **`standard_test_agents`**: Pre-configured test agents (client1, client2, miner1, miner2, agent1, agent2)
- **`cross_container_test_setup`**: Agents configured for cross-container testing

### Fixture Usage Examples

```python
def test_with_standard_agents(standard_test_agents):
    """Test using pre-configured agents"""
    client1_home = standard_test_agents["client1"]
    miner1_home = standard_test_agents["miner1"]
    
    # Test logic here

def test_custom_agent_setup(home_dir_fixture):
    """Test with custom agent configuration"""
    agents = home_dir_fixture.create_multi_agent_setup([
        {"name": "custom_client", "type": "client", "initial_balance": 5000},
        {"name": "custom_miner", "type": "miner", "initial_balance": 10000}
    ])
    
    # Test logic here
```

## 🚀 Quick Start

### Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-timeout pytest-xdist httpx psutil

# Ensure enhanced services are running
cd /home/oib/aitbc/apps/coordinator-api
./deploy_services.sh
./check_services.sh
```

### Running Tests

#### Quick Smoke Test
```bash
# Run quick smoke tests (default)
python run_e2e_tests.py

# Or explicitly
python run_e2e_tests.py quick
```

#### Complete Workflow Tests
```bash
# Run all workflow tests
python run_e2e_tests.py workflows -v

# Run with parallel execution
python run_e2e_tests.py workflows --parallel
```

#### Performance Benchmarks
```bash
# Run performance benchmarks
python run_e2e_tests.py performance -v

# Skip health check for faster execution
python run_e2e_tests.py performance --skip-health
```

#### Client-to-Miner Pipeline
```bash
# Run complete pipeline tests
python run_e2e_tests.py client_miner -v
```

#### All Tests
```bash
# Run all end-to-end tests
python run_e2e_tests.py all --parallel

# With verbose output
python run_e2e_tests.py all -v --parallel
```

## 📊 Test Configuration

### Performance Targets

The tests validate performance against the deployment report targets:

| Service | Operation | Target | Validation |
|---------|-----------|--------|------------|
| Multi-Modal | Text Processing | ≤0.02s | ✅ Measured |
| Multi-Modal | Image Processing | ≤0.15s | ✅ Measured |
| GPU Multi-Modal | Cross-Modal Attention | ≥10x speedup | ✅ Measured |
| GPU Multi-Modal | Multi-Modal Fusion | ≥20x speedup | ✅ Measured |
| Marketplace | Transaction Processing | ≤0.03s | ✅ Measured |
| Marketplace | Royalty Calculation | ≤0.01s | ✅ Measured |

### Test Markers

- `@pytest.mark.e2e`: End-to-end tests (all tests in this directory)
- `@pytest.mark.performance`: Performance benchmark tests
- `@pytest.mark.integration`: Service integration tests
- `@pytest.mark.slow`: Long-running tests

### Test Data

Tests use realistic data including:
- **Text Samples**: Product reviews, sentiment analysis examples
- **Image Data**: Mock image URLs and metadata
- **Agent Configurations**: Various algorithm and model settings
- **Marketplace Data**: Model listings, pricing, royalty configurations

## 🔧 Test Architecture

### Test Framework Components

#### 1. **EnhancedServicesWorkflowTester**
```python
class EnhancedServicesWorkflowTester:
    """Test framework for enhanced services workflows"""
    
    async def setup_test_environment() -> bool
    async def test_multimodal_processing_workflow() -> Dict[str, Any]
    async def test_gpu_acceleration_workflow() -> Dict[str, Any]
    async def test_marketplace_transaction_workflow() -> Dict[str, Any]
```

#### 2. **ClientToMinerWorkflowTester**
```python
class ClientToMinerWorkflowTester:
    """Test framework for client-to-miner workflows"""
    
    async def submit_client_request() -> Dict[str, Any]
    async def create_agent_workflow() -> Dict[str, Any]
    async def execute_agent_workflow() -> Dict[str, Any]
    async def monitor_workflow_execution() -> Dict[str, Any]
    async def verify_execution_receipt() -> Dict[str, Any]
    async def submit_to_marketplace() -> Dict[str, Any]
```

#### 3. **PerformanceBenchmarkTester**
```python
class PerformanceBenchmarkTester:
    """Performance testing framework"""
    
    async def benchmark_multimodal_performance() -> Dict[str, Any]
    async def benchmark_gpu_performance() -> Dict[str, Any]
    async def benchmark_marketplace_performance() -> Dict[str, Any]
    async def benchmark_concurrent_performance() -> Dict[str, Any]
```

### Service Health Validation

All tests begin with comprehensive health checks:

```python
async def setup_test_environment() -> bool:
    """Setup test environment and verify all services"""
    
    # Check coordinator API
    # Check all 6 enhanced services
    # Validate service capabilities
    # Return True if sufficient services are healthy
```

## 📈 Test Results Interpretation

### Success Criteria

#### Workflow Tests
- **Success**: ≥80% of workflow steps complete successfully
- **Partial Failure**: 60-79% of steps complete (some services unavailable)
- **Failure**: <60% of steps complete

#### Performance Tests
- **Excellent**: ≥90% of performance targets met
- **Good**: 70-89% of performance targets met
- **Needs Improvement**: <70% of performance targets met

#### Integration Tests
- **Success**: ≥90% of service integrations work
- **Partial**: 70-89% of integrations work
- **Failure**: <70% of integrations work

### Sample Output

```
🎯 Starting Complete Client-to-Miner Workflow
============================================================
📤 Step 1: Submitting client request...
✅ Job submitted: job_12345678
🤖 Step 2: Creating agent workflow...
✅ Agent workflow created: workflow_abcdef
⚡ Step 3: Executing agent workflow...
✅ Workflow execution started: exec_123456
📊 Step 4: Monitoring workflow execution...
   📈 Progress: 4/4 steps, Status: completed
✅ Workflow completed successfully
🔍 Step 5: Verifying execution receipt...
✅ Execution receipt verified
🏪 Step 6: Submitting to marketplace...
✅ Submitted to marketplace: model_789012

============================================================
  WORKFLOW COMPLETION SUMMARY
============================================================
Total Duration: 12.34s
Successful Steps: 6/6
Success Rate: 100.0%
Overall Status: ✅ SUCCESS
```

## 🛠️ Troubleshooting

### Common Issues

#### Services Not Available
```bash
# Check service status
./check_services.sh

# Start services
./manage_services.sh start

# Check individual service logs
./manage_services.sh logs aitbc-multimodal
```

#### Performance Test Failures
- **GPU Not Available**: GPU service will be skipped
- **High Load**: Reduce concurrent test levels
- **Network Latency**: Check localhost connectivity

#### Test Timeouts
- **Increase Timeout**: Use `--timeout` parameter
- **Skip Health Check**: Use `--skip-health` flag
- **Run Sequentially**: Remove `--parallel` flag

### Debug Mode

```bash
# Run with verbose output
python run_e2e_tests.py workflows -v

# Run specific test file
pytest test_enhanced_services_workflows.py::test_multimodal_processing_workflow -v -s

# Run with Python debugger
python -m pytest test_client_miner_workflow.py::test_client_to_miner_complete_workflow -v -s --pdb
```

## 📋 Test Checklist

### Before Running Tests
- [ ] All enhanced services deployed and healthy
- [ ] Test dependencies installed (`pytest`, `httpx`, `psutil`)
- [ ] Sufficient system resources (CPU, memory, GPU if available)
- [ ] Network connectivity to localhost services

### During Test Execution
- [ ] Monitor service logs for errors
- [ ] Check system resource utilization
- [ ] Validate test output for expected results
- [ ] Record performance metrics for comparison

### After Test Completion
- [ ] Review test results and success rates
- [ ] Analyze any failures or performance issues
- [ ] Update documentation with findings
- [ ] Archive test results for historical comparison

## 🔄 Continuous Integration

### CI/CD Integration

```yaml
# Example GitHub Actions workflow
- name: Run E2E Tests
  run: |
    cd tests/e2e
    python run_e2e_tests.py quick --skip-health
    
- name: Run Performance Benchmarks
  run: |
    cd tests/e2e
    python run_e2e_tests.py performance --parallel
```

### Test Automation

```bash
# Automated test script
#!/bin/bash
cd /home/oib/aitbc/tests/e2e

# Quick smoke test
python run_e2e_tests.py quick --skip-health

# Full test suite (weekly)
python run_e2e_tests.py all --parallel

# Performance benchmarks (daily)
python run_e2e_tests.py performance -v
```

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [HTTPX Documentation](https://www.python-httpx.org/)
- [AITBC Enhanced Services Documentation](../../docs/11_agents/)
- [Deployment Readiness Report](../../DEPLOYMENT_READINESS_REPORT.md)

## 🤝 Contributing

When adding new tests:

1. **Follow Naming Conventions**: Use descriptive test names
2. **Add Markers**: Use appropriate pytest markers
3. **Document Tests**: Include docstrings explaining test purpose
4. **Handle Failures Gracefully**: Provide clear error messages
5. **Update Documentation**: Keep this README current

### Test Template

```python
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_new_feature_workflow():
    """Test new feature end-to-end workflow"""
    tester = EnhancedServicesWorkflowTester()
    
    try:
        if not await tester.setup_test_environment():
            pytest.skip("Services not available")
        
        # Test implementation
        result = await tester.test_new_feature()
        
        # Assertions
        assert result["overall_status"] == "success"
        
    finally:
        await tester.cleanup_test_environment()
```
