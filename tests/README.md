# AITBC Mesh Network Test Suite

This directory contains comprehensive tests for the AITBC mesh network transition implementation, covering all 5 phases of the system.

## 🧪 **Test Structure**

### **Core Test Files**

| Test File | Purpose | Coverage |
|-----------|---------|----------|
| **`test_mesh_network_transition.py`** | Complete system tests | All 5 phases |
| **`test_phase_integration.py`** | Cross-phase integration tests | Phase interactions |
| **`test_performance_benchmarks.py`** | Performance and scalability tests | System performance |
| **`test_security_validation.py`** | Security and attack prevention tests | Security requirements |
| **`conftest_mesh_network.py`** | Test configuration and fixtures | Shared test utilities |

---

## 📊 **Test Categories**

### **1. Unit Tests** (`@pytest.mark.unit`)
- Individual component testing
- Mocked dependencies
- Fast execution
- Isolated functionality

### **2. Integration Tests** (`@pytest.mark.integration`)
- Cross-component testing
- Real interactions
- Phase dependencies
- End-to-end workflows

### **3. Performance Tests** (`@pytest.mark.performance`)
- Throughput benchmarks
- Latency measurements
- Scalability limits
- Resource usage

### **4. Security Tests** (`@pytest.mark.security`)
- Attack prevention
- Vulnerability testing
- Access control
- Data integrity

---

## 🚀 **Running Tests**

### **Quick Start**
```bash
# Run all tests
cd /opt/aitbc/tests
python -m pytest -v

# Run specific test file
python -m pytest test_mesh_network_transition.py -v

# Run by category
python -m pytest -m unit -v                    # Unit tests only
python -m pytest -m integration -v             # Integration tests only
python -m pytest -m performance -v            # Performance tests only
python -m pytest -m security -v                # Security tests only
```

### **Advanced Options**
```bash
# Run with coverage
python -m pytest --cov=aitbc_chain --cov-report=html

# Run performance tests with detailed output
python -m pytest test_performance_benchmarks.py -v -s

# Run security tests with strict checking
python -m pytest test_security_validation.py -v --tb=long

# Run integration tests only (slow)
python -m pytest test_phase_integration.py -v -m slow
```

---

## 📋 **Test Coverage**

### **Phase 1: Consensus Layer** (Tests 1-5)
- ✅ Multi-validator PoA initialization
- ✅ Validator rotation mechanisms
- ✅ PBFT consensus phases
- ✅ Slashing condition detection
- ✅ Key management security
- ✅ Byzantine fault tolerance

### **Phase 2: Network Infrastructure** (Tests 6-10)
- ✅ P2P discovery performance
- ✅ Peer health monitoring
- ✅ Dynamic peer management
- ✅ Network topology optimization
- ✅ Partition detection & recovery
- ✅ Message throughput

### **Phase 3: Economic Layer** (Tests 11-15)
- ✅ Staking operation speed
- ✅ Reward calculation accuracy
- ✅ Gas fee dynamics
- ✅ Economic attack prevention
- ✅ Slashing enforcement
- ✅ Token economics

### **Phase 4: Agent Network** (Tests 16-20)
- ✅ Agent registration speed
- ✅ Capability matching accuracy
- ✅ Reputation system integrity
- ✅ Communication protocol security
- ✅ Behavior monitoring
- ✅ Agent lifecycle management

### **Phase 5: Smart Contracts** (Tests 21-25)
- ✅ Escrow contract creation
- ✅ Dispute resolution fairness
- ✅ Contract upgrade security
- ✅ Gas optimization effectiveness
- ✅ Payment processing
- ✅ Contract state integrity

---

## 🔧 **Test Configuration**

### **Environment Variables**
```bash
export AITBC_TEST_MODE=true          # Enable test mode
export AITBC_MOCK_MODE=true          # Use mocks by default
export AITBC_LOG_LEVEL=DEBUG         # Verbose logging
export AITBC_INTEGRATION_TESTS=false  # Skip slow integration tests
```

### **Configuration Files**
- **`conftest_mesh_network.py`**: Global test configuration
- **Mock fixtures**: Pre-configured test data
- **Test utilities**: Helper functions and assertions
- **Performance metrics**: Benchmark data

### **Test Data**
```python
# Sample addresses
TEST_ADDRESSES = {
    "validator_1": "0x1111111111111111111111111111111111111111",
    "client_1": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "agent_1": "0xcccccccccccccccccccccccccccccccccccccccccc",
}

# Sample transactions
sample_transactions = [
    {"tx_id": "tx_001", "type": "transfer", "amount": 100.0},
    {"tx_id": "tx_002", "type": "stake", "amount": 1000.0},
    # ... more test data
]
```

---

## 📈 **Performance Benchmarks**

### **Target Metrics**
| Metric | Target | Test |
|--------|--------|------|
| **Block Propagation** | < 5 seconds | `test_block_propagation_time` |
| **Transaction Throughput** | > 100 tx/s | `test_consensus_throughput` |
| **Peer Discovery** | < 1 second | `test_peer_discovery_speed` |
| **Agent Registration** | > 25 agents/s | `test_agent_registration_speed` |
| **Escrow Creation** | > 20 contracts/s | `test_escrow_creation_speed` |

### **Scalability Limits**
| Component | Max Tested | Target |
|-----------|------------|--------|
| **Validators** | 100 | 50+ |
| **Agents** | 10,000 | 100+ |
| **Concurrent Transactions** | 10,000 | 1,000+ |
| **Network Nodes** | 500 | 50+ |

---

## 🔒 **Security Validation**

### **Attack Prevention Tests**
- ✅ **Consensus**: Double signing, key compromise, Byzantine attacks
- ✅ **Network**: Sybil attacks, DDoS, message tampering
- ✅ **Economics**: Reward manipulation, gas price manipulation, staking attacks
- ✅ **Agents**: Authentication bypass, reputation manipulation, communication hijacking
- ✅ **Contracts**: Double spend, escrow manipulation, dispute bias

### **Security Requirements**
```python
# Example security test
def test_double_signing_detection(self):
    """Test detection of validator double signing"""
    # Simulate double signing
    event = mock_slashing.detect_double_sign(
        validator_address, block_hash_1, block_hash_2, block_height
    )
    
    assert event is not None
    assert event.validator_address == validator_address
    mock_slashing.apply_slash.assert_called_once()
```

---

## 🔗 **Integration Testing**

### **Cross-Phase Workflows**
1. **End-to-End Job Execution**
   - Client creates job → Agent matches → Escrow funded → Work completed → Payment released

2. **Consensus with Network**
   - Validators discover peers → Form consensus → Propagate blocks → Handle partitions

3. **Economics with Agents**
   - Agents earn rewards → Stake tokens → Reputation affects earnings → Economic incentives

4. **Contracts with All Layers**
   - Escrow created → Network validates → Economics processes → Agents participate

### **Test Scenarios**
```python
@pytest.mark.asyncio
async def test_end_to_end_job_execution_workflow(self):
    """Test complete job execution workflow across all phases"""
    # 1. Client creates escrow contract
    success, _, contract_id = mock_escrow.create_contract(...)
    
    # 2. Find suitable agent
    agents = mock_agents.find_agents("text_generation")
    
    # 3. Network communication
    success, _, _ = mock_protocol.send_message(...)
    
    # 4. Consensus validation
    valid, _ = mock_consensus.validate_transaction(...)
    
    # 5. Complete workflow
    assert success is True
```

---

## 📊 **Test Reports**

### **HTML Coverage Report**
```bash
python -m pytest --cov=aitbc_chain --cov-report=html
# View: htmlcov/index.html
```

### **Performance Report**
```bash
python -m pytest test_performance_benchmarks.py -v --tb=short
# Output: Performance metrics and benchmark results
```

### **Security Report**
```bash
python -m pytest test_security_validation.py -v --tb=long
# Output: Security validation results and vulnerability assessment
```

---

## 🛠️ **Test Utilities**

### **Helper Functions**
```python
# Performance assertion
def assert_performance_metric(actual, expected, tolerance=0.1):
    """Assert performance metric within tolerance"""
    lower_bound = expected * (1 - tolerance)
    upper_bound = expected * (1 + tolerance)
    assert lower_bound <= actual <= upper_bound

# Async condition waiting
async def async_wait_for_condition(condition, timeout=10.0):
    """Wait for async condition to be true"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition():
            return True
        await asyncio.sleep(0.1)
    raise AssertionError("Timeout waiting for condition")

# Test data generators
def generate_test_transactions(count=100):
    """Generate test transactions"""
    return [create_test_transaction() for _ in range(count)]
```

### **Mock Decorators**
```python
@mock_integration_test
def test_cross_phase_functionality():
    """Integration test with mocked dependencies"""
    pass

@mock_performance_test
def test_system_performance():
    """Performance test with benchmarking"""
    pass

@mock_security_test
def test_attack_prevention():
    """Security test with attack simulation"""
    pass
```

---

## 📝 **Writing New Tests**

### **Test Structure Template**
```python
class TestNewFeature:
    """Test new feature implementation"""
    
    @pytest.fixture
    def new_feature_instance(self):
        """Create test instance"""
        return NewFeature()
    
    @pytest.mark.asyncio
    async def test_basic_functionality(self, new_feature_instance):
        """Test basic functionality"""
        # Arrange
        test_data = create_test_data()
        
        # Act
        result = await new_feature_instance.process(test_data)
        
        # Assert
        assert result is not None
        assert result.success is True
    
    @pytest.mark.integration
    def test_integration_with_existing_system(self, new_feature_instance):
        """Test integration with existing system"""
        # Integration test logic
        pass
    
    @pytest.mark.performance
    def test_performance_requirements(self, new_feature_instance):
        """Test performance meets requirements"""
        # Performance test logic
        pass
```

### **Best Practices**
1. **Use descriptive test names**
2. **Arrange-Act-Assert pattern**
3. **Test both success and failure cases**
4. **Mock external dependencies**
5. **Use fixtures for shared setup**
6. **Add performance assertions**
7. **Include security edge cases**
8. **Document test purpose**

---

## 🚨 **Troubleshooting**

### **Common Issues**

#### **Import Errors**
```bash
# Add missing paths to sys.path
export PYTHONPATH="/opt/aitbc/apps/blockchain-node/src:$PYTHONPATH"
```

#### **Mock Mode Issues**
```bash
# Disable mock mode for integration tests
export AITBC_MOCK_MODE=false
python -m pytest test_phase_integration.py -v
```

#### **Performance Test Timeouts**
```bash
# Increase timeout for slow tests
python -m pytest test_performance_benchmarks.py -v --timeout=300
```

#### **Security Test Failures**
```bash
# Run security tests with verbose output
python -m pytest test_security_validation.py -v -s --tb=long
```

### **Debug Mode**
```bash
# Run with debug logging
export AITBC_LOG_LEVEL=DEBUG
python -m pytest test_mesh_network_transition.py::test_consensus_initialization -v -s
```

---

## 📈 **Continuous Integration**

### **CI/CD Pipeline**
```yaml
# Example GitHub Actions workflow
name: AITBC Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - name: Install dependencies
        run: pip install -r requirements-test.txt
      - name: Run unit tests
        run: python -m pytest -m unit --cov=aitbc_chain
      - name: Run integration tests
        run: python -m pytest -m integration
      - name: Run performance tests
        run: python -m pytest -m performance
      - name: Run security tests
        run: python -m pytest -m security
```

### **Quality Gates**
- ✅ **Unit Tests**: 95%+ coverage, all pass
- ✅ **Integration Tests**: All critical paths pass
- ✅ **Performance Tests**: Meet all benchmarks
- ✅ **Security Tests**: No critical vulnerabilities
- ✅ **Code Quality**: Pass linting and formatting

---

## 📚 **Documentation**

### **Test Documentation**
- **Inline comments**: Explain complex test logic
- **Docstrings**: Document test purpose and setup
- **README files**: Explain test structure and usage
- **Examples**: Provide usage examples

### **API Documentation**
```python
def test_consensus_initialization(self):
    """Test consensus layer initialization
    
    Verifies that:
    - Multi-validator PoA initializes correctly
    - Default configuration is applied
    - Validators can be added
    - Round-robin selection works
    
    Args:
        mock_consensus: Mock consensus instance
    
    Returns:
        None
    """
    # Test implementation
```

---

## 🎯 **Success Criteria**

### **Test Coverage Goals**
- **Unit Tests**: 95%+ code coverage
- **Integration Tests**: All critical workflows
- **Performance Tests**: All benchmarks met
- **Security Tests**: All attack vectors covered

### **Quality Metrics**
- **Test Reliability**: < 1% flaky tests
- **Execution Time**: < 10 minutes for full suite
- **Maintainability**: Clear, well-documented tests
- **Reproducibility**: Consistent results across environments

---

**🎉 This comprehensive test suite ensures the AITBC mesh network implementation meets all functional, performance, and security requirements before production deployment!**
