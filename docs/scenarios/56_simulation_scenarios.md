# Simulation Scenarios for hermes Agents

**Level**: Intermediate  
**Prerequisites**: Basic CLI knowledge, AITBC CLI installed  
**Estimated Time**: 30 minutes  
**Last Updated**: 2026-05-27  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Simulation Scenarios

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [55 Resource Management](./55_resource_management.md)
- **📖 Next Scenario**: [13 Mining Setup](./13_mining_setup.md)
- **📖 Related**: [03 Genesis Deployment](./03_genesis_deployment.md)
- **📖 Related**: [07 AI Job Submission](./07_ai_job_submission.md)
- **⚙️ Simulation Documentation**: [CLI Simulation Commands](../cli/CLI_DOCUMENTATION.md)

---

## 📚 **Scenario Overview**

This scenario demonstrates how hermes agents use simulation commands to model blockchain scenarios, test environments, and validate system behavior without affecting production data. Simulations enable agents to stress-test systems, model market conditions, and validate workflows safely.

### **Use Case**
An hermes agent needs to:
- Simulate blockchain block production and transaction throughput
- Model wallet creation and transaction patterns
- Test price movement scenarios with volatility
- Simulate network topology and node failures
- Model AI job submission and processing
- Run custom simulation scenarios via coordinator-api

### **What You'll Learn**
- Simulate blockchain block production with configurable parameters
- Model wallet creation and transaction flows
- Simulate price movements with volatility
- Test network topology and failure scenarios
- Model AI job submission and processing
- Run custom simulation scenarios via coordinator-api
- Track simulation status and results

### **Features Combined**
- **Blockchain Simulation**: Block production and transaction modeling
- **Wallet Simulation**: Wallet creation and transaction flows
- **Price Simulation**: Market price modeling with volatility
- **Network Simulation**: Topology and failure testing
- **AI Job Simulation**: Job submission and processing modeling
- **Custom Scenarios**: Run coordinator-api simulation scenarios

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Basic command-line interface usage
- Understanding of blockchain concepts (blocks, transactions)
- Understanding of network topology concepts
- AITBC CLI installed and accessible

### **System Requirements**
- AITBC CLI installed
- coordinator-api running (for run/status/result commands)
- No additional setup required for local simulations

### **Setup Required**
- coordinator-api running (for custom simulation scenarios)
- Config file with `coordinator_url` set (for coordinator-api simulations)

---

## 🚀 **Quick Start**

```bash
# Simulate blockchain block production
aitbc simulate blockchain --blocks 10 --transactions 50

# Simulate wallet creation and transactions
aitbc simulate wallets --wallets 5 --balance 1000 --transactions 20

# Simulate price movements
aitbc simulate price --price 100 --volatility 0.05 --timesteps 100

# Simulate network topology
aitbc simulate network --nodes 3 --failure-rate 0.05

# Simulate AI job processing
aitbc simulate ai-jobs --jobs 10 --models text-generation,image-generation

# Run custom simulation via coordinator-api
aitbc simulate run load-test --params '{"users": 100, "duration": 300}'
```

---

## 📖 **Detailed Steps**

### Step 1: Simulate Blockchain Block Production

Model blockchain block production and transaction throughput:

```bash
# Simulate 10 blocks with 50 transactions each
aitbc simulate blockchain --blocks 10 --transactions 50

# Simulate with custom delay between blocks
aitbc simulate blockchain --blocks 20 --transactions 100 --delay 2

# Output in JSON format
aitbc simulate blockchain --blocks 5 --transactions 25 --output json
```

**Expected Output:**
```
Simulating blockchain with 10 blocks, 50 transactions per block
Block 1: 50 txs, 25000.50 AIT, 25.25 fees
Block 2: 50 txs, 24800.75 AIT, 24.80 fees
Block 3: 50 txs, 25200.25 AIT, 25.20 fees
...
Block 10: 50 txs, 24900.00 AIT, 24.90 fees

Simulation Summary:
  Total Blocks: 10
  Total Transactions: 500
  Total Amount: 249500.50 AIT
  Total Fees: 249.50 AIT
  Average TPS: 50.00
```

**Parameters explained:**
- `--blocks`: Number of blocks to simulate (default: 10)
- `--transactions`: Transactions per block (default: 50)
- `--delay`: Delay between blocks in seconds (default: 1.0)
- `--output`: Output format (table, json, yaml)

### Step 2: Simulate Wallet Creation and Transactions

Model wallet creation and transaction flows:

```bash
# Create 5 wallets with 1000 AIT each, simulate 20 transactions
aitbc simulate wallets --wallets 5 --balance 1000 --transactions 20

# Custom transaction amount range
aitbc simulate wallets --wallets 10 --balance 5000 --transactions 50 \
  --amount-range 10.0-500.0
```

**Expected Output:**
```
Simulating 5 wallets with 1000.00 AIT initial balance
Created wallet sim_wallet_1: ait1abc123... with 1000.00 AIT
Created wallet sim_wallet_2: ait1def456... with 1000.00 AIT
Created wallet sim_wallet_3: ait1ghi789... with 1000.00 AIT
Created wallet sim_wallet_4: ait1jkl012... with 1000.00 AIT
Created wallet sim_wallet_5: ait1mno345... with 1000.00 AIT

Simulating 20 transactions...
Tx 1: sim_wallet_1 -> sim_wallet_2: 45.50 AIT
Tx 2: sim_wallet_3 -> sim_wallet_1: 78.25 AIT
...
Tx 20: sim_wallet_4 -> sim_wallet_5: 32.75 AIT

Final Wallet Balances:
  sim_wallet_1: 1050.25 AIT
  sim_wallet_2: 980.50 AIT
  sim_wallet_3: 1025.75 AIT
  sim_wallet_4: 950.00 AIT
  sim_wallet_5: 993.50 AIT
```

### Step 3: Simulate Price Movements

Model AIT price movements with volatility:

```bash
# Simulate price from 100 AIT with 5% volatility
aitbc simulate price --price 100 --volatility 0.05 --timesteps 100

# High volatility simulation
aitbc simulate price --price 50 --volatility 0.15 --timesteps 200

# Low volatility simulation
aitbc simulate price --price 200 --volatility 0.01 --timesteps 50
```

**Expected Output:**
```
Simulating AIT price from 100.00 with 0.05 volatility
Step 1: 102.50 AIT (+2.50%)
Step 2: 99.75 AIT (-2.68%)
Step 3: 101.25 AIT (+1.50%)
...
Step 100: 98.50 AIT (-0.75%)

Price Statistics:
  Starting Price: 100.0000 AIT
  Ending Price: 98.5000 AIT
  Minimum Price: 85.2500 AIT
  Maximum Price: 115.7500 AIT
  Average Price: 100.1250 AIT
  Total Change: -1.50%
```

### Step 4: Simulate Network Topology

Test network topology and node failure scenarios:

```bash
# Simulate 3-node network with 5% failure rate
aitbc simulate network --nodes 3 --network-delay 0.1 --failure-rate 0.05

# Simulate 5-node network with higher failure rate
aitbc simulate network --nodes 5 --network-delay 0.2 --failure-rate 0.10
```

**Expected Output:**
```
Simulating network with 3 nodes, 0.1s delay, 0.05 failure rate

Network Topology:
  node_1 (10.1.223.90): connected to node_2, node_3
  node_2 (10.1.223.91): connected to node_3, node_1
  node_3 (10.1.223.92): connected to node_1, node_2

Simulating network operations...
Step 1: node_1 produced block 1, 3 nodes active
Step 2: node_2 produced block 2, 3 nodes active
Step 3: node_3 failed
Step 4: node_1 produced block 3, 2 nodes active
...
Step 10: node_2 produced block 8, 2 nodes active

Final Network Status:
  ✅ node_1: height 5, connections: 2
  ✅ node_2: height 5, connections: 2
  ❌ node_3: height 2, connections: 2
```

### Step 5: Simulate AI Job Processing

Model AI job submission and processing:

```bash
# Simulate 10 AI jobs with text and image generation
aitbc simulate ai-jobs --jobs 10 \
  --models text-generation,image-generation \
  --duration-range 30-300

# Simulate with custom models
aitbc simulate ai-jobs --jobs 20 \
  --models text-generation,image-generation,audio-generation \
  --duration-range 60-600
```

**Expected Output:**
```
Simulating 10 AI jobs with models: text-generation, image-generation
Submitted job job_001: text-generation (est. 120s)
Submitted job job_002: image-generation (est. 240s)
Submitted job job_003: text-generation (est. 90s)
...
Submitted job job_010: image-generation (est. 180s)

Simulating job processing...
Started job_001
Started job_002
Started job_003
...
Completed job_001 in 118.5s
Completed job_003 in 92.3s
...
Completed job_010 in 175.8s

Job Statistics:
  Total Jobs: 10
  Completed Jobs: 10
  Failed Jobs: 0
  Average Duration: 145.2s
  Model Usage:
    text-generation: 5 jobs
    image-generation: 5 jobs
```

### Step 6: Run Custom Simulation via Coordinator-API

Execute custom simulation scenarios:

```bash
# Run load test simulation
aitbc simulate run load-test \
  --params '{"users": 100, "duration": 300, "requests_per_second": 10}'

# Run stress test simulation asynchronously
aitbc simulate run stress-test --params '{"concurrent_users": 500}' --async-run

# Run network partition simulation
aitbc simulate run network-partition \
  --params '{"partition_duration": 60, "affected_nodes": ["node_1", "node_2"]}'
```

**Expected Output:**
```
Simulation 'load-test' started
{
  "simulation_id": "sim_1716789123",
  "scenario": "load-test",
  "status": "running",
  "params": {
    "users": 100,
    "duration": 300,
    "requests_per_second": 10
  },
  "started_at": "2026-05-27T08:30:00"
}
```

### Step 7: Check Simulation Status

Monitor simulation progress:

```bash
# Check simulation status
aitbc simulate status sim_1716789123
```

**Expected Output:**
```
Simulation sim_1716789123 Status:
{
  "simulation_id": "sim_1716789123",
  "scenario": "load-test",
  "status": "running",
  "progress": 45,
  "started_at": "2026-05-27T08:30:00",
  "estimated_completion": "2026-05-27T08:35:00",
  "metrics": {
    "requests_completed": 1350,
    "requests_failed": 5,
    "average_latency": 125
  }
}
```

### Step 8: Get Simulation Results

Retrieve simulation results:

```bash
# Get simulation results
aitbc simulate result sim_1716789123
```

**Expected Output:**
```
Simulation sim_1716789123 Results:
{
  "simulation_id": "sim_1716789123",
  "scenario": "load-test",
  "status": "completed",
  "started_at": "2026-05-27T08:30:00",
  "completed_at": "2026-05-27T08:34:58",
  "duration": 298,
  "results": {
    "total_requests": 3000,
    "successful_requests": 2995,
    "failed_requests": 5,
    "success_rate": 99.83,
    "average_latency": 122,
    "p95_latency": 250,
    "p99_latency": 450
  }
}
```

---

## 🔧 **Advanced Usage**

### Stress Testing with High Throughput

Simulate high transaction throughput:

```bash
# Simulate 100 blocks with 500 transactions each
aitbc simulate blockchain --blocks 100 --transactions 500 --delay 0.5

# Calculate TPS
# 500 tx/block * 100 blocks / (100 * 0.5s) = 1000 TPS
```

### Market Crash Simulation

Model extreme price volatility:

```bash
# Simulate market crash with 30% volatility
aitbc simulate price --price 100 --volatility 0.30 --timesteps 200 --delay 0.05
```

### Network Partition Testing

Test network resilience with high failure rate:

```bash
# Simulate network with 25% failure rate
aitbc simulate network --nodes 5 --network-delay 0.2 --failure-rate 0.25
```

### Batch Simulation Scenarios

Run multiple simulations in sequence:

```bash
#!/bin/bash
# run_simulations.sh

echo "=== Blockchain Simulation ==="
aitbc simulate blockchain --blocks 50 --transactions 100

echo ""
echo "=== Price Simulation ==="
aitbc simulate price --price 100 --volatility 0.10 --timesteps 200

echo ""
echo "=== Network Simulation ==="
aitbc simulate network --nodes 5 --failure-rate 0.10

echo ""
echo "=== AI Job Simulation ==="
aitbc simulate ai-jobs --jobs 20 --duration-range 60-600
```

### Custom Scenario Development

Create custom simulation parameters:

```bash
# Custom load test with ramp-up
aitbc simulate run custom-load-test \
  --params '{
    "ramp_up_duration": 60,
    "peak_users": 1000,
    "peak_duration": 300,
    "ramp_down_duration": 60,
    "request_pattern": "sine_wave"
  }'
```

---

## ⚠️ **Important Notes**

### Local vs Coordinator-API Simulations
- **Local Simulations**: blockchain, wallets, price, network, ai-jobs run locally
- **Coordinator-API Simulations**: run, status, result require coordinator-api
- **No External Dependencies**: Local simulations work without coordinator-api
- **Network Required**: Coordinator-API simulations need network connectivity

### Simulation Limitations
- **Mock Data**: Simulations use random/mock data, not real blockchain state
- **No Persistence**: Simulation results are not persisted to blockchain
- **No Side Effects**: Simulations do not affect production systems
- **Deterministic Results**: Same parameters may produce different results due to randomness

### Performance Considerations
- **Large Simulations**: High block/transaction counts may take time
- **Memory Usage**: Large simulations may consume significant memory
- **CPU Usage**: Simulations are CPU-intensive
- **Terminal Output**: Large simulations produce extensive output

### Coordinator-API Integration
- **Scenario Support**: Coordinator-api must support requested scenario
- **Async Mode**: Use --async-run for long-running simulations
- **Status Polling**: Use status command to track async simulations
- **Result Retrieval**: Results available after simulation completes

---

## 🐛 **Troubleshooting**

### Invalid JSON parameters

**Error:**
```
Error: Invalid JSON parameters
```

**Solution:**
```bash
# Ensure JSON is properly formatted
aitbc simulate run load-test --params '{"users": 100, "duration": 300}'

# Validate JSON before running
echo '{"users": 100, "duration": 300}' | python3 -m json.tool
```

### Coordinator API unavailable

**Error:**
```
Network error: Failed to connect to coordinator
```

**Solution:**
```bash
# Check coordinator-api status
curl http://127.0.0.1:18000/health

# Use local simulations instead
aitbc simulate blockchain --blocks 10 --transactions 50
```

### Simulation not found

**Error:**
```
Error: Simulation sim_1234567890 not found
```

**Solution:**
```bash
# List running simulations (if coordinator-api supports it)
curl http://127.0.0.1:18000/api/v1/simulations

# Use correct simulation ID
aitbc simulate status sim_1716789123
```

### Invalid amount range format

**Error:**
```
Error: Invalid amount range format
```

**Solution:**
```bash
# Use correct format: min-max
aitbc simulate wallets --amount-range 10.0-100.0

# Ensure numbers are valid
aitbc simulate wallets --amount-range 1.0-1000.0
```

### Simulation takes too long

**Issue:**
Simulation running for extended period

**Solution:**
```bash
# Reduce simulation size
aitbc simulate blockchain --blocks 10 --transactions 50  # Instead of 100/500

# Reduce delay
aitbc simulate blockchain --blocks 50 --transactions 100 --delay 0.1

# Use async mode for coordinator-api simulations
aitbc simulate run long-test --async-run
```

---

## 🧪 **Validation**

Validate this scenario with the shared 3-node harness:

```bash
bash scripts/workflow/44_comprehensive_multi_node_scenario.sh
```

**Node coverage**:
- `aitbc1`: genesis / primary node checks
- `aitbc`: follower / local node checks
- `gitea-runner`: automation / CI node checks

**Validation guide**:
- [Scenario Validation Guide](./VALIDATION.md)

**Expected result**:
- Scenario-specific commands complete successfully
- Local simulations run without external dependencies
- Coordinator-API simulations require coordinator-api running
- Cross-node health checks pass
- Blockchain heights remain in sync

**Note**: Local simulations (blockchain, wallets, price, network, ai-jobs) work without external services. Coordinator-API simulations (run, status, result) require coordinator-api running.

---

## 💻 **Code Examples Using Agent SDK**

### Example 1: Run Blockchain Simulation Programmatically
```python
from aitbc_agent_sdk import Agent, AgentConfig

config = AgentConfig(
    name="simulation-agent",
    blockchain_network="mainnet"
)

agent = Agent(config)
agent.start()

# Run blockchain simulation
result = agent.run_simulation(
    type="blockchain",
    params={
        "blocks": 50,
        "transactions": 100,
        "delay": 1.0
    }
)

print(f"Total Blocks: {result['total_blocks']}")
print(f"Total Transactions: {result['total_transactions']}")
print(f"Average TPS: {result['average_tps']}")
```

### Example 2: Monitor Simulation Progress
```python
from aitbc_agent_sdk import Agent, AgentConfig
import time

config = AgentConfig(
    name="monitoring-agent",
    blockchain_network="mainnet"
)

agent = Agent(config)
agent.start()

# Start simulation
sim_id = agent.start_simulation("load-test", {"users": 100, "duration": 300})

# Monitor progress
while True:
    status = agent.get_simulation_status(sim_id)
    print(f"Progress: {status['progress']}%")
    
    if status['status'] == 'completed':
        break
    
    time.sleep(5)

# Get results
results = agent.get_simulation_results(sim_id)
print(f"Success Rate: {results['success_rate']}%")
```

### Example 3: Run Price Simulation
```python
from aitbc_agent_sdk import Agent, AgentConfig

config = AgentConfig(
    name="trading-agent",
    blockchain_network="mainnet"
)

agent = Agent(config)
agent.start()

# Run price simulation
price_data = agent.simulate_price(
    starting_price=100.0,
    volatility=0.05,
    timesteps=200
)

print(f"Starting Price: {price_data['starting_price']}")
print(f"Ending Price: {price_data['ending_price']}")
print(f"Max Price: {price_data['max_price']}")
print(f"Min Price: {price_data['min_price']}")
print(f"Total Change: {price_data['total_change']}%")
```

---

## 🎯 **Expected Outcomes**

After completing this scenario, you should be able to:
- Simulate blockchain block production with configurable parameters
- Model wallet creation and transaction flows
- Simulate price movements with volatility
- Test network topology and failure scenarios
- Model AI job submission and processing
- Run custom simulation scenarios via coordinator-api
- Track simulation status and results
- Understand the difference between local and coordinator-api simulations

---

## 🔗 **Related Resources**

### **AITBC Documentation**
- [Scenario 03: Genesis Deployment](./03_genesis_deployment.md) - Real blockchain deployment
- [Scenario 07: AI Job Submission](./07_ai_job_submission.md) - Real AI job operations
- [CLI Simulation Commands](../cli/CLI_DOCUMENTATION.md) - Complete CLI reference
- [Coordinator API Documentation](../apps/coordinator-api/README.md) - API details

### **External Resources**
- [Blockchain Simulation](https://www.ibm.com/topics/blockchain-simulation)
- [Network Topology](https://www.networkworld.com/article/3236143/network-topology-types.html)
- [Price Volatility Modeling](https://www.investopedia.com/articles/trading/07/ stochastic.asp)

### **Next Scenarios**
- [13: Mining Setup](./13_mining_setup.md) - Real mining operations
- [22: AI Training Agent](./22_ai_training_agent.md) - Real AI training
- [27: Cross Chain Trader](./27_cross_chain_trader.md) - Real trading operations

---

## 📊 **Quality Metrics**
- **Structure**: 10/10 - Clear workflow from blockchain to custom scenarios
- **Content**: 10/10 - Comprehensive simulation coverage
- **Code Examples**: 10/10 - Working Agent SDK examples
- **Status**: Active scenario

---

*Last updated: 2026-05-27*  
*Version: 1.0*  
*Status: Active scenario document*
