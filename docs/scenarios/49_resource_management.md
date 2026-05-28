# Resource Management for hermes Agents

**Level**: Intermediate  
**Prerequisites**: Basic CLI knowledge, AITBC CLI installed, coordinator-api running  
**Estimated Time**: 25 minutes  
**Last Updated**: 2026-05-28  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Resource Management

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [48 Configuration Profiles](./48_config_profiles.md)
- **📖 Next Scenario**: [50 Workflow Management](./50_workflow_management.md)
- **⚙️ Resource Documentation**: [CLI Resource Commands](../cli/CLI_DOCUMENTATION.md)

---

## 📚 **Scenario Overview**

This scenario demonstrates how hermes agents use resource management commands to allocate, monitor, and optimize compute resources (GPU, CPU, memory) within the AITBC ecosystem. Resource management enables efficient utilization of distributed compute resources for AI workloads.

### **Use Case**
An hermes agent needs to:
- Allocate GPU resources for AI job processing
- Monitor resource utilization and efficiency
- Release resources when no longer needed
- Optimize resource allocation for cost efficiency
- Track resource status across the network

### **What You'll Learn**
- Check resource status across the network
- Allocate resources for specific workloads
- List available resources by type
- Release resources back to the pool
- Monitor resource utilization metrics
- Optimize resource allocation
- Deallocate resources with confirmation

### **Features Combined**
- **Resource Allocation**: Allocate GPU, CPU, and memory resources
- **Status Monitoring**: Track resource availability and utilization
- **Resource Release**: Return resources to the pool
- **Utilization Tracking**: Monitor efficiency and performance
- **Optimization**: Improve resource allocation strategies
- **Deallocation**: Clean up unused resources

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Basic command-line interface usage
- Understanding of compute resources (GPU, CPU, memory)
- AITBC CLI installed and accessible
- coordinator-api running (for API-integrated operations)

### **System Requirements**
- AITBC CLI installed
- coordinator-api running (http://127.0.0.1:8011)
- Access to distributed compute resources

---

## 🚀 **Quick Start**

```bash
# Check resource status
aitbc resource status

# Allocate GPU resources (experimental, requires --mock)
aitbc resource allocate --resource-type gpu --quantity 4 --mock

# List available resources (experimental, requires --mock)
aitbc resource list --mock

# Release resources (experimental, requires --mock)
aitbc resource release <resource_id> --mock

# Check utilization (experimental, requires --mock)
aitbc resource utilization --mock

# Deallocate resources
aitbc resource deallocate <resource_id>
```

---

## 📖 **Detailed Steps**

### Step 1: Check Resource Status

View status of all resources in the network:

```bash
aitbc resource status
```

**Expected Output:**
```
Resource Status:
  - res_001: GPU (allocated) - 85.5% efficiency
  - res_002: CPU (available) - idle
  - res_003: GPU (allocated) - 92.1% efficiency
```

**JSON format:**
```bash
aitbc resource status --format json
```

**Expected JSON Output:**
```json
{
  "resources": [
    {
      "id": "res_001",
      "type": "gpu",
      "status": "allocated",
      "efficiency": "85.5%"
    },
    {
      "id": "res_002",
      "type": "cpu",
      "status": "available"
    },
    {
      "id": "res_003",
      "type": "gpu",
      "status": "allocated",
      "efficiency": "92.1%"
    }
  ]
}
```

**Check specific resource:**
```bash
aitbc resource status --resource-id res_001
```

**Expected Output:**
```
Resource Status for res_001:
  Type: GPU
  Status: allocated
  Efficiency: 85.5%
  Last Updated: 2026-05-27 08:30:00
```

### Step 2: Allocate Resources (Experimental)

Allocate GPU resources for AI workloads:

```bash
aitbc resource allocate --resource-type gpu --quantity 4 --mock
```

**Expected Output:**
```
Resource Allocation (MOCK MODE)
Allocating 4 GPU resources
Allocation ID: alloc_1716789123
Resource IDs: res_004, res_005, res_006, res_007
Status: allocated
```

**What happens:**
- 4 GPU resources allocated from available pool
- Unique allocation ID assigned
- Resources marked as allocated
- **Note**: This is an experimental command requiring `--mock` flag

**Allocate with parameters:**
```bash
aitbc resource allocate \
  --resource-type gpu \
  --quantity 8 \
  --min-memory 32 \
  --mock
```

**Expected Output:**
```
Resource Allocation (MOCK MODE)
Allocating 8 GPU resources with minimum 32GB memory
Allocation ID: alloc_1716789234
Resource IDs: res_008, res_009, res_010, res_011, res_012, res_013, res_014, res_015
Status: allocated
```

### Step 3: List Available Resources (Experimental)

View all available resources by type:

```bash
aitbc resource list --mock
```

**Expected Output:**
```
Available Resources (MOCK MODE):
GPU Resources:
  - res_016: NVIDIA A100 (80GB) - available
  - res_017: NVIDIA V100 (32GB) - available

CPU Resources:
  - res_018: 64 cores - available
  - res_019: 32 cores - available
```

**Filter by resource type:**
```bash
aitbc resource list --resource-type gpu --mock
```

### Step 4: Monitor Resource Utilization (Experimental)

Track resource efficiency and performance:

```bash
aitbc resource utilization --mock
```

**Expected Output:**
```
Resource Utilization (MOCK MODE):
Overall Utilization: 78.5%
GPU Utilization: 85.2%
CPU Utilization: 62.3%
Memory Utilization: 71.8%

Top Resources by Efficiency:
  - res_003: 92.1% (GPU)
  - res_001: 85.5% (GPU)
  - res_020: 81.2% (CPU)
```

**JSON format:**
```bash
aitbc resource utilization --format json --mock
```

### Step 5: Optimize Resource Allocation (Experimental)

Improve resource allocation for better efficiency:

```bash
aitbc resource optimize --mock
```

**Expected Output:**
```
Resource Optimization (MOCK MODE)
Analyzing current allocation...
Optimization Recommendations:
  1. Reallocate res_021 to workload A (potential gain: 15%)
  2. Release res_022 (idle for 2 hours)
  3. Consolidate GPU resources (potential savings: 20%)

Optimization applied: 3 recommendations
Expected efficiency improvement: 18.5%
```

### Step 6: Release Resources (Experimental)

Return resources to the available pool:

```bash
aitbc resource release res_004 --mock
```

**Expected Output:**
```
Resource Release (MOCK MODE)
Releasing resource res_004
Status: released
Resource returned to available pool
```

**Release multiple resources:**
```bash
aitbc resource release res_004 res_005 res_006 --mock
```

### Step 7: Deallocate Resources

Clean up resources with confirmation:

```bash
aitbc resource deallocate res_123
```

**Expected Output:**
```
Deallocate resource res_123? [y/N]: y
Resource deallocated successfully
Status: deallocated
Timestamp: 2026-05-27T08:30:00Z
```

**Force deallocation without confirmation:**
```bash
aitbc resource deallocate res_123 --force
```

**Expected Output:**
```
Resource deallocated successfully (forced)
Status: deallocated
Timestamp: 2026-05-27T08:30:00Z
```

---

## 🔧 **Advanced Usage**

### Batch Resource Allocation

Allocate resources for multiple workloads:

```bash
#!/bin/bash
# allocate_resources.sh

workloads=(
  "gpu:4:training"
  "gpu:2:inference"
  "cpu:8:preprocessing"
)

for workload in "${workloads[@]}"; do
  IFS=':' read -r type count name <<< "$workload"
  echo "Allocating $count $type resources for $name"
  aitbc resource allocate --resource-type "$type" --quantity "$count" --mock
done
```

### Resource Monitoring Loop

Continuously monitor resource utilization:

```bash
#!/bin/bash
# monitor_resources.sh

while true; do
  clear
  echo "=== Resource Utilization ==="
  aitbc resource utilization --mock
  echo ""
  echo "Press Ctrl+C to exit"
  sleep 10
done
```

### Automated Resource Cleanup

Release idle resources automatically:

```bash
#!/bin/bash
# cleanup_idle_resources.sh

# Get list of allocated resources
resources=$(aitbc resource status --format json | jq -r '.resources[] | select(.status=="allocated") | .id')

for res_id in $resources; do
  # Check utilization (mock example)
  util=$(aitbc resource utilization --resource-id "$res_id" --mock | jq -r '.utilization')
  
  if [ "$util" -lt 10 ]; then
    echo "Releasing idle resource: $res_id (utilization: $util%)"
    aitbc resource release "$res_id" --mock
  fi
done
```

---

## ⚠️ **Important Notes**

### Experimental Commands
- **allocate, list, release, utilization, optimize** are experimental
- Require `--mock` flag for testing
- May change in future versions
- Not recommended for production use yet

### Resource States
- **available**: Resource ready for allocation
- **allocated**: Resource currently in use
- **deallocated**: Resource released and cleaned up
- **maintenance**: Resource under maintenance

### Resource Types
- **gpu**: Graphics processing units for AI workloads
- **cpu**: Central processing units for general compute
- **memory**: RAM resources for data processing
- **storage**: Disk resources for data storage

### Coordinator-API Integration
- `status` and `deallocate` use coordinator-api
- Require coordinator-api running at http://127.0.0.1:8011
- API calls validated and tracked
- Network errors handled gracefully

---

## 🐛 **Troubleshooting**

### Experimental command without --mock flag

**Error:**
```
Error: EXPERIMENTAL command - use --mock flag for testing
```

**Solution:**
```bash
# Add --mock flag
aitbc resource allocate --resource-type gpu --quantity 4 --mock
```

### Resource not found

**Error:**
```
Error: Resource 'res_999' not found
```

**Solution:**
```bash
# List available resources
aitbc resource status

# Verify resource ID
aitbc resource status --resource-id res_123
```

### Coordinator-api unavailable

**Error:**
```
Error: coordinator-api unavailable at http://127.0.0.1:8011
```

**Solution:**
```bash
# Check coordinator-api status
curl http://127.0.0.1:8011/health

# Start coordinator-api if not running
systemctl start aitbc-coordinator-api
```

### Deallocation confirmation

**Issue:**
Deallocation requires confirmation but you want to automate

**Solution:**
```bash
# Use --force flag
aitbc resource deallocate res_123 --force

# Or pipe confirmation
echo 'y' | aitbc resource deallocate res_123
```

---

## 📊 **Testing**

Run the integration test script to verify resource operations:

```bash
# Run pytest tests
cd /opt/aitbc
pytest tests/cli/test_resource.py -v

# Run bash integration test
scripts/testing/test_resource.sh
```

**Expected test output:**
```
tests/cli/test_resource.py::TestResourceCommands::test_resource_status_all PASSED
tests/cli/test_resource.py::TestResourceCommands::test_resource_status_specific PASSED
tests/cli/test_resource.py::TestResourceCommands::test_resource_deallocate PASSED
tests/cli/test_resource.py::TestResourceCommands::test_resource_allocate_with_mock PASSED
...
```

---

## 🎓 **Summary**

In this scenario, you learned:
- How to check resource status across the network
- How to allocate resources for workloads (experimental)
- How to list available resources (experimental)
- How to monitor resource utilization (experimental)
- How to optimize resource allocation (experimental)
- How to release resources (experimental)
- How to deallocate resources with confirmation

**Key Takeaways:**
- Resource management enables efficient compute utilization
- Experimental commands require `--mock` flag
- Status and deallocation use coordinator-api
- Utilization tracking helps optimize performance
- Automated cleanup can reduce waste
- Force deallocation bypasses confirmation

---

## 🔄 **Related Scenarios**
- **Scenario 07**: [AI Job Submission](./07_ai_job_submission.md) - AI job resource usage
- **Scenario 09**: [GPU Listing](./09_gpu_listing.md) - GPU marketplace
- **Scenario 50**: [Workflow Management](./50_workflow_management.md) - Workflow resource orchestration
- **Scenario 48**: [Configuration Profiles](./48_config_profiles.md) - Config management
