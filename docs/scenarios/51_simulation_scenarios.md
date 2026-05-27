# Simulation Scenarios for hermes Agents

**Level**: Intermediate  
**Prerequisites**: Basic CLI knowledge, AITBC CLI installed, coordinator-api running  
**Estimated Time**: 30 minutes  
**Last Updated**: 2026-05-27  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Simulation Scenarios

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [49 Resource Management](./49_resource_management.md)
- **📖 Next Scenario**: [52 Edge Advanced Operations](./52_edge_advanced_operations.md)
- **⚙️ Simulation Documentation**: [CLI Simulation Commands](../cli/CLI_DOCUMENTATION.md)

---

## 📚 **Scenario Overview**

This scenario demonstrates how hermes agents use simulation commands to model and test various AITBC ecosystem scenarios including blockchain operations, wallet behavior, price movements, network topology, and AI job processing. Simulations enable agents to validate strategies and predict outcomes before executing real transactions.

### **Use Case**
An hermes agent needs to:
- Model blockchain behavior under different conditions
- Simulate wallet creation and balance distribution
- Predict price movements with various volatility patterns
- Test network topology and latency scenarios
- Simulate AI job submission and processing workflows
- Validate strategies before real execution

### **What You'll Learn**
- Run blockchain simulations with custom parameters
- Simulate wallet creation and balance distribution
- Model price movements with trends and volatility
- Test network topology and latency scenarios
- Simulate AI job processing workflows
- Run simulations in async mode
- Monitor simulation status and retrieve results

### **Features Combined**
- **Blockchain Simulation**: Model block generation and transaction processing
- **Wallet Simulation**: Create wallets with various balance distributions
- **Price Simulation**: Model price movements with trends and volatility
- **Network Simulation**: Test network topology and latency scenarios
- **AI Jobs Simulation**: Model AI job submission and processing
- **Async Execution**: Run simulations asynchronously
- **Status Tracking**: Monitor simulation progress and results

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Basic command-line interface usage
- Understanding of blockchain concepts
- AITBC CLI installed and accessible
- coordinator-api running (for API-integrated simulations)

### **System Requirements**
- AITBC CLI installed
- coordinator-api running (http://127.0.0.1:18000)
- Sufficient system resources for simulations

---

## 🚀 **Quick Start**

```bash
# Blockchain simulation
aitbc simulate blockchain --blocks 10 --transactions 50

# Wallets simulation
aitbc simulate wallets --count 5 --balance 1000

# Price simulation
aitbc simulate price --days 30 --volatility 0.1

# Network simulation
aitbc simulate network --nodes 10 --latency 50

# AI jobs simulation
aitbc simulate ai-jobs --jobs 20 --duration 300
```

---

## 📖 **Detailed Steps**

### Step 1: Blockchain Simulation

Simulate blockchain block generation and transaction processing:

```bash
aitbc simulate blockchain --blocks 10 --transactions 50
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716789123",
  "blocks": 10,
  "transactions": 50,
  "status": "completed",
  "block_time_avg": "2.5s"
}
```

**What happens:**
- Blockchain simulation executed
- Blocks generated with transactions
- Performance metrics collected

### Step 2: Blockchain with Custom Parameters

Simulate blockchain with difficulty and custom parameters:

```bash
aitbc simulate blockchain --blocks 100 --transactions 500 --difficulty 5
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716789234",
  "blocks": 100,
  "transactions": 500,
  "difficulty": 5,
  "status": "completed"
}
```

### Step 3: Wallets Simulation

Simulate wallet creation with balance distribution:

```bash
aitbc simulate wallets --count 5 --balance 1000
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716789345",
  "wallets": 5,
  "balance": 1000,
  "distribution": "uniform",
  "status": "completed"
}
```

### Step 4: Wallets with Exponential Distribution

Simulate wallets with exponential balance distribution:

```bash
aitbc simulate wallets --count 10 --distribution exponential
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716789456",
  "wallets": 10,
  "distribution": "exponential",
  "status": "completed"
}
```

### Step 5: Price Simulation

Simulate price movements with volatility:

```bash
aitbc simulate price --days 30 --volatility 0.1
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716789567",
  "days": 30,
  "volatility": 0.1,
  "prices": [100.0, 105.2, 98.7, ...],
  "status": "completed"
}
```

### Step 6: Price with Trend

Simulate price movements with bullish trend:

```bash
aitbc simulate price --days 90 --trend bullish --volatility 0.15
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716789678",
  "days": 90,
  "trend": "bullish",
  "volatility": 0.15,
  "status": "completed"
}
```

### Step 7: Network Simulation

Simulate network topology and latency:

```bash
aitbc simulate network --nodes 10 --latency 50
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716789789",
  "nodes": 10,
  "latency": 50,
  "topology": "random",
  "status": "completed"
}
```

### Step 8: Network with Custom Topology

Simulate network with mesh topology:

```bash
aitbc simulate network --nodes 20 --topology mesh --latency 100
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716789890",
  "nodes": 20,
  "topology": "mesh",
  "latency": 100,
  "status": "completed"
}
```

### Step 9: AI Jobs Simulation

Simulate AI job submission and processing:

```bash
aitbc simulate ai-jobs --jobs 20 --duration 300
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716790001",
  "jobs": 20,
  "duration": 300,
  "status": "completed"
}
```

### Step 10: AI Jobs with GPU Requirements

Simulate AI jobs with GPU requirements:

```bash
aitbc simulate ai-jobs --jobs 30 --gpu-required --duration 600
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716790112",
  "jobs": 30,
  "gpu_required": true,
  "duration": 600,
  "status": "completed"
}
```

### Step 11: Run Simulation

Run a simulation with type and duration:

```bash
aitbc simulate run --type blockchain --duration 60
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716790223",
  "type": "blockchain",
  "duration": 60,
  "status": "started"
}
```

### Step 12: Run Async Simulation

Run simulation in async mode:

```bash
aitbc simulate run --type network --async --duration 120
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716790334",
  "type": "network",
  "async": true,
  "status": "started"
}
```

### Step 13: Check Simulation Status

Monitor simulation progress:

```bash
aitbc simulate status sim_1716790223
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716790223",
  "status": "running",
  "progress": "75%",
  "elapsed_time": "45s"
}
```

### Step 14: Get Simulation Results

Retrieve simulation results:

```bash
aitbc simulate result sim_1716790223
```

**Expected Output:**
```json
{
  "simulation_id": "sim_1716790223",
  "status": "completed",
  "results": {
    "blocks_generated": 10,
    "transactions_processed": 50,
    "avg_block_time": "2.5s"
  }
}
```

---

## 🔧 **Advanced Usage**

### Custom Simulation Scenarios

Create complex simulation scenarios by combining parameters:

```bash
# High-volume blockchain simulation
aitbc simulate blockchain --blocks 1000 --transactions 10000 --difficulty 8

# Large-scale wallet simulation
aitbc simulate wallets --count 1000 --distribution power-law --balance 10000

# Long-term price simulation
aitbc simulate price --days 365 --trend bearish --volatility 0.25

# Complex network topology
aitbc simulate network --nodes 50 --topology hierarchical --latency 200

# Complex AI job workflow
aitbc simulate ai-jobs --jobs 100 --gpu-required --multi-gpu --duration 3600
```

### Batch Simulations

Run multiple simulations sequentially:

```bash
#!/bin/bash
# run_simulations.sh

sim_types=("blockchain" "wallets" "price" "network" "ai-jobs")

for sim in "${sim_types[@]}"; do
    echo "Running simulation: $sim"
    aitbc simulate run --type "$sim" --duration 60
    
    # Wait for completion
    sleep 5
done
```

### Simulation Comparison

Compare results from different simulations:

```bash
# Run simulation A
aitbc simulate blockchain --blocks 100 --transactions 500 --difficulty 3
sim_id_a=$(aitbc simulate run --type blockchain --duration 60 | jq -r '.simulation_id')

# Run simulation B
aitbc simulate blockchain --blocks 100 --transactions 500 --difficulty 7
sim_id_b=$(aitbc simulate run --type blockchain --duration 60 | jq -r '.simulation_id')

# Compare results
aitbc simulate result $sim_id_a > result_a.json
aitbc simulate result $sim_id_b > result_b.json
diff result_a.json result_b.json
```

---

## ⚠️ **Important Notes**

### Simulation IDs
- Each simulation gets a unique ID: `sim_<timestamp>`
- Use simulation IDs for tracking and result retrieval
- IDs are generated automatically

### Simulation States
- **Started**: Simulation initialized
- **Running**: Simulation in progress
- **Completed**: Simulation finished successfully
- **Failed**: Simulation encountered an error

### Resource Requirements
- Large simulations may require significant CPU/memory
- Async mode recommended for long-running simulations
- Monitor system resources during simulations

### Output Formats
- JSON format for programmatic processing
- Table format for human-readable output
- Use `--format json` or `--format table` to specify

---

## 🐛 **Troubleshooting**

### Simulation not found

**Error:**
```
Error: Simulation 'sim_123' not found
```

**Solution:**
```bash
# Check simulation ID
aitbc simulate status sim_123

# List recent simulations (if available)
aitbc simulate list
```

### Coordinator-api unavailable

**Error:**
```
Error: coordinator-api not available
```

**Solution:**
```bash
# Check coordinator-api status
curl http://127.0.0.1:18000/health

# Start coordinator-api if needed
systemctl start aitbc-coordinator-api
```

### Simulation stuck in running state

**Issue:**
Simulation status shows "Running" but not progressing

**Solution:**
```bash
# Check coordinator-api status
curl http://127.0.0.1:18000/health

# Review simulation logs
# (Location depends on implementation)

# Cancel simulation if needed
aitbc simulate cancel sim_123
```

### Invalid simulation parameters

**Error:**
```
Error: Invalid parameter value
```

**Solution:**
```bash
# Check parameter ranges
aitbc simulate blockchain --help

# Use valid parameter values
aitbc simulate blockchain --blocks 10  # Valid
aitbc simulate blockchain --blocks -5  # Invalid
```

---

## 📊 **Testing**

Run the integration test script to verify simulation operations:

```bash
# Run pytest tests
cd /opt/aitbc
pytest tests/cli/test_simulate_integration.py -v

# Run bash integration test
scripts/testing/test_simulate.sh
```

**Expected test output:**
```
tests/cli/test_simulate_integration.py::TestSimulateCommandsIntegration::test_simulate_blockchain PASSED
tests/cli/test_simulate_integration.py::TestSimulateCommandsIntegration::test_simulate_wallets PASSED
tests/cli/test_simulate_integration.py::TestSimulateCommandsIntegration::test_simulate_price PASSED
...
```

---

## 🎓 **Summary**

In this scenario, you learned:
- How to run blockchain simulations with custom parameters
- How to simulate wallet creation and balance distribution
- How to model price movements with trends and volatility
- How to test network topology and latency scenarios
- How to simulate AI job processing workflows
- How to run simulations in async mode
- How to monitor simulation status and retrieve results

**Key Takeaways:**
- Simulations enable strategy validation before real execution
- Each simulation gets a unique ID for tracking
- Async mode recommended for long-running simulations
- Custom parameters enable realistic scenario modeling
- Status monitoring enables simulation control
- Results retrieval enables analysis and comparison

---

## 🔄 **Related Scenarios**
- **Scenario 03**: [Genesis Deployment](./03_genesis_deployment.md) - Blockchain operations
- **Scenario 07**: [AI Job Submission](./07_ai_job_submission.md) - AI job operations
- **Scenario 09**: [GPU Listing](./09_gpu_listing.md) - GPU marketplace operations
- **Scenario 49**: [Resource Management](./49_resource_management.md) - Resource allocation
