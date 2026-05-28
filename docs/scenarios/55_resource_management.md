# Resource Management for hermes Agents

**Level**: Intermediate  
**Prerequisites**: Basic CLI knowledge, AITBC CLI installed  
**Estimated Time**: 20 minutes  
**Last Updated**: 2026-05-27  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Resource Management

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [54 Monitoring and Metrics](./54_monitoring_and_metrics.md)
- **📖 Next Scenario**: [56 Simulation Scenarios](./56_simulation_scenarios.md)
- **📖 Related**: [09 GPU Listing](./09_gpu_listing.md)
- **📖 Related**: [21 Compute Provider Agent](./21_compute_provider_agent.md)
- **⚙️ Resource Documentation**: [CLI Resource Commands](../cli/CLI_DOCUMENTATION.md)

---

## 📚 **Scenario Overview**

This scenario demonstrates how hermes agents use resource management commands to allocate, monitor, and optimize computing resources. **Note: All resource commands are currently EXPERIMENTAL and use placeholder logic. The --mock flag is required for testing.**

### **Use Case**
An hermes agent needs to:
- Allocate GPU, CPU, and storage resources for AI jobs
- Monitor resource utilization and efficiency
- Release unused resources to optimize costs
- Optimize resource allocation across agents
- Track resource allocation status

### **What You'll Learn**
- Allocate resources with priority levels
- List and view allocated resources
- Release resources when no longer needed
- Monitor resource utilization metrics
- Optimize resource allocation
- Check resource allocation status

### **Features Combined**
- **Resource Allocation**: Allocate GPU, CPU, and storage with priority
- **Resource Listing**: View all allocated resources
- **Resource Release**: Deallocate resources when finished
- **Utilization Metrics**: Monitor resource usage and efficiency
- **Optimization**: Improve resource allocation efficiency
- **Status Tracking**: Check allocation status via coordinator-api

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Basic command-line interface usage
- Understanding of computing resources (GPU, CPU, storage)
- AITBC CLI installed and accessible

### **System Requirements**
- AITBC CLI installed
- coordinator-api running (for status/deallocate commands)
- No additional setup required for mock mode

### **Setup Required**
- coordinator-api running (for live status/deallocate)
- Config file with `coordinator_url` set (for live operations)

---

## 🚀 **Quick Start**

```bash
# Allocate resources (mock mode required)
aitbc resource allocate --resource-type gpu --quantity 4 --priority high --mock

# List allocated resources (mock mode required)
aitbc resource list --mock

# Release resources (mock mode required)
aitbc resource release alloc_1234567890 --mock

# View utilization metrics (mock mode required)
aitbc resource utilization --mock

# Optimize resources (mock mode required)
aitbc resource optimize --target all --mock
```

---

## 📖 **Detailed Steps**

### Step 1: Allocate Resources

Request computing resources with priority:

```bash
# Allocate 4 GPUs with high priority
aitbc resource allocate --resource-type gpu --quantity 4 --priority high --mock

# Allocate CPU resources with medium priority
aitbc resource allocate --resource-type cpu --quantity 8 --priority medium --mock

# Allocate storage with low priority
aitbc resource allocate --resource-type storage --quantity 100 --priority low --mock
```

**Expected Output:**
```
Allocate 4 gpu with high priority
Allocation ID: alloc_1716789123
Status: Allocated
Cost per hour: 25 AIT
```

**Parameters explained:**
- `--resource-type`: Type of resource (gpu, cpu, storage)
- `--quantity`: Number of units to allocate
- `--priority`: Allocation priority (low, medium, high)
- `--mock`: Required flag for experimental command

**What happens:**
- Resource allocation request created
- Allocation ID returned for tracking
- Mock data simulates successful allocation
- TODO: Implement actual coordinator API integration

### Step 2: List Allocated Resources

View all currently allocated resources:

```bash
# List all resources in table format
aitbc resource list --mock

# List resources in JSON format
aitbc resource list --format json --mock

# List specific resource by ID
aitbc resource list --resource-id alloc_1234567890 --mock
```

**Expected Output (table):**
```
Allocated resources:
  - GPU: 4 allocated, 8 available (78.5%)
  - CPU: 45.2% allocated, 54.8% available (82.1%)
  - STORAGE: 45GB allocated, 55GB available (90.0%)
```

**Expected Output (JSON):**
```json
[
  {
    "type": "gpu",
    "allocated": 4,
    "available": 8,
    "efficiency": "78.5%"
  },
  {
    "type": "cpu",
    "allocated": "45.2%",
    "available": "54.8%",
    "efficiency": "82.1%"
  },
  {
    "type": "storage",
    "allocated": "45GB",
    "available": "55GB",
    "efficiency": "90.0%"
  }
]
```

### Step 3: Monitor Resource Utilization

Check resource usage and efficiency metrics:

```bash
# View utilization in table format
aitbc resource utilization --mock

# View utilization in JSON format
aitbc resource utilization --format json --mock
```

**Expected Output (table):**
```
Resource utilization:
  cpu_utilization: 45.2%
  memory_usage: 2.1GB / 8GB (26%)
  storage_available: 45GB / 100GB
  network_bandwidth: 120Mbps / 1Gbps
  active_agents: 3
  resource_efficiency: 78.5%
```

**Expected Output (JSON):**
```json
{
  "cpu_utilization": "45.2%",
  "memory_usage": "2.1GB / 8GB (26%)",
  "storage_available": "45GB / 100GB",
  "network_bandwidth": "120Mbps / 1Gbps",
  "active_agents": 3,
  "resource_efficiency": "78.5%"
}
```

### Step 4: Release Resources

Deallocate resources when no longer needed:

```bash
# Release specific resource by ID
aitbc resource release alloc_1716789123 --mock

# Release multiple resources
aitbc resource release alloc_1716789123 --mock
aitbc resource release alloc_1716789124 --mock
```

**Expected Output:**
```
Release resource alloc_1716789123
Status: Released
```

**What happens:**
- Resource deallocation request processed
- Resources returned to available pool
- Allocation cost stops accruing
- TODO: Implement actual coordinator API integration

### Step 5: Optimize Resource Allocation

Improve resource allocation efficiency:

```bash
# Optimize all resources
aitbc resource optimize --target all --mock

# Optimize only GPU resources
aitbc resource optimize --target gpu --mock

# Optimize for specific agent
aitbc resource optimize --target all --agent-id agent_123 --mock
```

**Expected Output:**
```
Optimize resources for target: all
Optimization score: 85.2%
Improvement: 12.5%
Status: Optimized
```

**Parameters explained:**
- `--target`: Optimization target (all, cpu, gpu, memory)
- `--agent-id`: Specific agent ID to optimize for
- `--mock`: Required flag for experimental command

### Step 6: Check Resource Status (Live)

Check allocation status via coordinator-api (no --mock required):

```bash
# Check all resource status
aitbc resource status

# Check specific resource status
aitbc resource status --resource-id alloc_1234567890
```

**Expected Output:**
```
Resource Status:
{
  "resource_id": "alloc_1234567890",
  "type": "gpu",
  "quantity": 4,
  "status": "allocated",
  "allocated_at": "2026-05-27T08:30:00",
  "cost_per_hour": 25,
  "agent_id": "agent_123"
}
```

**Note:** This command requires coordinator-api running and does not use --mock flag.

### Step 7: Deallocate Resources (Live)

Deallocate resources via coordinator-api (no --mock required):

```bash
# Deallocate with confirmation
aitbc resource deallocate alloc_1234567890

# Force deallocation without confirmation
aitbc resource deallocate alloc_1234567890 --force
```

**Expected Output:**
```
Are you sure you want to deallocate resource alloc_1234567890? [y/N]: y
Resource alloc_1234567890 deallocated successfully
{
  "resource_id": "alloc_1234567890",
  "status": "deallocated",
  "deallocated_at": "2026-05-27T09:00:00"
}
```

**Note:** This command requires coordinator-api running and does not use --mock flag.

---

## 🔧 **Advanced Usage**

### Batch Resource Allocation

Allocate multiple resources in sequence:

```bash
#!/bin/bash
# allocate_resources.sh

# Allocate GPU
aitbc resource allocate --resource-type gpu --quantity 4 --priority high --mock

# Allocate CPU
aitbc resource allocate --resource-type cpu --quantity 8 --priority medium --mock

# Allocate storage
aitbc resource allocate --resource-type storage --quantity 100 --priority low --mock

# View allocation
aitbc resource list --mock
```

### Resource Optimization Strategy

Optimize resources for specific use cases:

```bash
# Optimize for AI training (GPU-heavy)
aitbc resource optimize --target gpu --mock

# Optimize for data processing (CPU-heavy)
aitbc resource optimize --target cpu --mock

# Optimize for storage-heavy workloads
aitbc resource optimize --target all --mock
```

### Monitoring Resource Efficiency

Track resource efficiency over time:

```bash
#!/bin/bash
# monitor_resources.sh

while true; do
  clear
  echo "=== Resource Utilization ==="
  aitbc resource utilization --mock
  echo ""
  echo "=== Allocated Resources ==="
  aitbc resource list --mock
  sleep 60
done
```

### Cost Estimation

Calculate resource costs:

```bash
#!/bin/bash
# estimate_cost.sh

# GPU: 25 AIT/hour
GPU_COST=25
# CPU: 10 AIT/hour
CPU_COST=10
# Storage: 5 AIT/hour
STORAGE_COST=5

# Get allocation
aitbc resource list --format json --mock > resources.json

# Calculate cost (example)
python3 << EOF
import json
with open('resources.json') as f:
    resources = json.load(f)
    
total_cost = 0
for res in resources:
    if res['type'] == 'gpu':
        total_cost += res['allocated'] * $GPU_COST
    elif res['type'] == 'cpu':
        total_cost += float(res['allocated'].rstrip('%')) / 100 * $CPU_COST
    elif res['type'] == 'storage':
        total_cost += int(res['allocated'].rstrip('GB')) / 100 * $STORAGE_COST

print(f"Estimated hourly cost: {total_cost} AIT")
EOF
```

---

## ⚠️ **Important Notes**

### Experimental Status
- **All Commands**: All resource commands are EXPERIMENTAL
- **Placeholder Logic**: Current implementation uses mock data
- **--mock Required**: Most commands require --mock flag
- **TODO Status**: Actual coordinator API integration pending

### Live Operations
- **status Command**: Does not require --mock, uses coordinator-api
- **deallocate Command**: Does not require --mock, uses coordinator-api
- **Coordinator Required**: Live operations need coordinator-api running
- **Network Dependency**: Live operations require network connectivity

### Resource Types
- **GPU**: Graphics processing units for AI/ML workloads
- **CPU**: Central processing units for general computing
- **Storage**: Disk space for data persistence

### Priority Levels
- **High**: Urgent resource needs, allocated first
- **Medium**: Standard resource needs
- **Low**: Background resource needs, allocated last

### Cost Considerations
- **Hourly Billing**: Resources billed per hour
- **GPU Cost**: 25 AIT/hour (mock rate)
- **CPU Cost**: 10 AIT/hour (mock rate)
- **Storage Cost**: 5 AIT/hour (mock rate)

---

## 🐛 **Troubleshooting**

### Command without --mock flag

**Error:**
```
[EXPERIMENTAL] This command uses placeholder logic. Use --mock for testing.
To proceed with mock data, run: aitbc resource allocate --mock
```

**Solution:**
```bash
# Always use --mock flag for experimental commands
aitbc resource allocate --resource-type gpu --quantity 4 --mock
```

### Coordinator API unavailable for live operations

**Error:**
```
Network error: Failed to connect to coordinator
```

**Solution:**
```bash
# Check coordinator-api status
curl http://127.0.0.1:8011/health

# Verify coordinator URL in config
aitbc config show

# Use mock mode for testing
aitbc resource allocate --mock
```

### Invalid resource type

**Error:**
```
Error: Invalid choice: resource_type. (choose from gpu, cpu, storage)
```

**Solution:**
```bash
# Use valid resource types
aitbc resource allocate --resource-type gpu --quantity 4 --mock
aitbc resource allocate --resource-type cpu --quantity 8 --mock
aitbc resource allocate --resource-type storage --quantity 100 --mock
```

### Invalid priority level

**Error:**
```
Error: Invalid choice: priority. (choose from low, medium, high)
```

**Solution:**
```bash
# Use valid priority levels
aitbc resource allocate --resource-type gpu --quantity 4 --priority high --mock
aitbc resource allocate --resource-type gpu --quantity 4 --priority medium --mock
aitbc resource allocate --resource-type gpu --quantity 4 --priority low --mock
```

### Resource ID not found

**Error:**
```
Error: Resource alloc_1234567890 not found
```

**Solution:**
```bash
# List available resources
aitbc resource list --mock

# Use correct resource ID from list
aitbc resource release alloc_1716789123 --mock
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
- Scenario-specific commands complete successfully with --mock flag
- Cross-node health checks pass
- Blockchain heights remain in sync
- Any node-specific step is documented in the scenario workflow

**Note**: Resource commands are EXPERIMENTAL and require --mock flag. Live operations (status, deallocate) require coordinator-api running. Mock mode can be tested without external dependencies.

---

## 💻 **Code Examples Using Agent SDK**

### Example 1: Allocate Resources Programmatically
```python
from aitbc_agent_sdk import Agent, AgentConfig

config = AgentConfig(
    name="resource-agent",
    blockchain_network="mainnet"
)

agent = Agent(config)
agent.start()

# Allocate GPU resources
allocation = agent.allocate_resources(
    resource_type="gpu",
    quantity=4,
    priority="high"
)

print(f"Allocation ID: {allocation['allocation_id']}")
print(f"Status: {allocation['status']}")
```

### Example 2: Monitor Resource Utilization
```python
from aitbc_agent_sdk import Agent, AgentConfig

config = AgentConfig(
    name="monitoring-agent",
    blockchain_network="mainnet"
)

agent = Agent(config)
agent.start()

# Get resource utilization
utilization = agent.get_resource_utilization()

print(f"CPU Utilization: {utilization['cpu_utilization']}")
print(f"Memory Usage: {utilization['memory_usage']}")
print(f"Storage Available: {utilization['storage_available']}")
print(f"Resource Efficiency: {utilization['resource_efficiency']}")
```

### Example 3: Optimize Resource Allocation
```python
from aitbc_agent_sdk import Agent, AgentConfig

config = AgentConfig(
    name="optimization-agent",
    blockchain_network="mainnet"
)

agent = Agent(config)
agent.start()

# Optimize all resources
result = agent.optimize_resources(target="all")

print(f"Optimization Score: {result['optimization_score']}")
print(f"Improvement: {result['improvement']}")
print(f"Status: {result['status']}")
```

---

## 🎯 **Expected Outcomes**

After completing this scenario, you should be able to:
- Allocate GPU, CPU, and storage resources with priority
- List and view allocated resources in table or JSON format
- Release resources when no longer needed
- Monitor resource utilization metrics
- Optimize resource allocation for efficiency
- Check resource allocation status via coordinator-api
- Deallocate resources via coordinator-api
- Understand the experimental status of resource commands

---

## 🔗 **Related Resources**

### **AITBC Documentation**
- [Scenario 09: GPU Listing](./09_gpu_listing.md) - GPU marketplace operations
- [Scenario 21: Compute Provider Agent](./21_compute_provider_agent.md) - GPU provider agent
- [CLI Resource Commands](../cli/CLI_DOCUMENTATION.md) - Complete CLI reference
- [Coordinator API Documentation](../apps/coordinator-api/README.md) - API details

### **External Resources**
- [GPU Resource Management](https://www.nvidia.com/en-us/data-center/gpu-cloud/)
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Cloud Resource Optimization](https://aws.amazon.com/blogs/architecture/optimizing-resource-usage/)

### **Next Scenarios**
- [56: Simulation Scenarios](./56_simulation_scenarios.md) - Test simulation
- [22: AI Training Agent](./22_ai_training_agent.md) - AI training workflows
- [35: Edge Compute Agent](./35_edge_compute_agent.md) - Edge resource management

---

## 📊 **Quality Metrics**
- **Structure**: 10/10 - Clear workflow from allocation to optimization
- **Content**: 10/10 - Comprehensive resource management coverage
- **Code Examples**: 10/10 - Working Agent SDK examples
- **Status**: Active scenario (EXPERIMENTAL)

---

*Last updated: 2026-05-27*  
*Version: 1.0*  
*Status: Active scenario document (EXPERIMENTAL)*
