# Edge Advanced Operations for hermes Agents

**Level**: Advanced  
**Prerequisites**: Basic CLI knowledge, AITBC CLI installed, edge-api running  
**Estimated Time**: 35 minutes  
**Last Updated**: 2026-05-27  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Edge Advanced Operations

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [51 Simulation Scenarios](./51_simulation_scenarios.md)
- **📖 Next Scenario**: [01 Wallet Basics](./01_wallet_basics.md)
- **⚙️ Edge Documentation**: [CLI Edge Commands](../cli/CLI_DOCUMENTATION.md)

---

## 📚 **Scenario Overview**

This scenario demonstrates how hermes agents use advanced edge API operations to manage compute islands, GPU resources, databases, serve requests, and metrics. Edge operations enable agents to interact with distributed compute infrastructure at the network edge for low-latency AI workloads.

### **Use Case**
An hermes agent needs to:
- Manage compute island membership and bridging
- Discover and manage GPU resources at the edge
- Initialize and synchronize edge databases
- Submit and track compute serve requests
- Record and query performance metrics
- Monitor edge infrastructure health

### **What You'll Learn**
- Leave and bridge compute islands
- List, get, remove, and scan GPUs
- Initialize, list, get, delete, and sync databases
- Submit, list, get, cancel, and retrieve serve requests
- Record, list, get, and delete metrics
- Use edge API for distributed compute operations

### **Features Combined**
- **Island Management**: Leave islands and bridge between islands
- **GPU Operations**: Discover and manage GPU resources
- **Database Operations**: Initialize and sync edge databases
- **Serve Operations**: Submit and track compute requests
- **Metrics Operations**: Record and query performance metrics
- **Edge API Integration**: Direct API calls to edge-api service

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Basic command-line interface usage
- Understanding of distributed compute concepts
- AITBC CLI installed and accessible
- edge-api running (http://127.0.0.1:8200)

### **System Requirements**
- AITBC CLI installed
- edge-api running (http://127.0.0.1:8200)
- Network connectivity to edge nodes
- Appropriate permissions for edge operations

---

## 🚀 **Quick Start**

```bash
# List available GPUs
aitbc edge gpu list_gpus

# Leave an island
aitbc edge island leave --island-id my_island

# Initialize a database
aitbc edge database init_db --db-name my_db

# Submit a serve request
aitbc edge serve submit_request --request-type compute --parameters '{"gpu_count": 2}'

# Record a metric
aitbc edge metrics record --metric-name gpu_utilization --value 85.5
```

---

## 📖 **Detailed Steps**

### Step 1: Island Advanced Operations

#### Leave an Island

```bash
aitbc edge island leave --island-id test_island_123
```

**Expected Output:**
```json
{
  "island_id": "test_island_123",
  "status": "left",
  "timestamp": "2026-05-27T09:00:00Z"
}
```

**What happens:**
- Agent removes itself from the specified island
- Island membership updated
- Resources deallocated from island

#### Bridge Between Islands

```bash
aitbc edge island bridge --source island_a --target island_b
```

**Expected Output:**
```json
{
  "bridge_id": "bridge_abc123",
  "source": "island_a",
  "target": "island_b",
  "status": "established"
}
```

**What happens:**
- Network bridge created between islands
- Resources can be shared across islands
- Latency-optimized routing enabled

### Step 2: GPU Operations

#### List Available GPUs

```bash
aitbc edge gpu list_gpus
```

**Expected Output:**
```json
{
  "gpus": [
    {
      "id": "gpu_1",
      "type": "NVIDIA",
      "memory_gb": 16,
      "status": "available"
    },
    {
      "id": "gpu_2",
      "type": "NVIDIA",
      "memory_gb": 32,
      "status": "allocated"
    }
  ]
}
```

#### Get Specific GPU Info

```bash
aitbc edge gpu get_gpu --gpu-id gpu_1
```

**Expected Output:**
```json
{
  "gpu_id": "gpu_1",
  "type": "NVIDIA",
  "memory_gb": 16,
  "status": "available",
  "utilization": 0.0,
  "temperature": 45
}
```

#### Remove a GPU

```bash
aitbc edge gpu remove_gpu --gpu-id gpu_1
```

**Expected Output:**
```json
{
  "gpu_id": "gpu_1",
  "status": "removed",
  "timestamp": "2026-05-27T09:05:00Z"
}
```

#### Scan for Available GPUs

```bash
aitbc edge gpu scan_gpus
```

**Expected Output:**
```json
{
  "scan_results": {
    "found": 4,
    "gpus": [
      {"id": "gpu_1", "type": "NVIDIA", "memory": 16},
      {"id": "gpu_2", "type": "NVIDIA", "memory": 32}
    ]
  }
}
```

#### Get GPU Metrics

```bash
aitbc edge gpu gpu_metrics --gpu-id gpu_1
```

**Expected Output:**
```json
{
  "gpu_id": "gpu_1",
  "metrics": {
    "utilization": 85.5,
    "memory_used": 12.5,
    "temperature": 72,
    "power_usage": 250
  }
}
```

### Step 3: Database Operations

#### Initialize a Database

```bash
aitbc edge database init_db --db-name test_db
```

**Expected Output:**
```json
{
  "db_id": "db_123",
  "db_name": "test_db",
  "status": "initialized",
  "location": "/edge/data/test_db"
}
```

#### List Databases

```bash
aitbc edge database list_dbs
```

**Expected Output:**
```json
{
  "databases": [
    {
      "db_id": "db_123",
      "db_name": "test_db",
      "status": "active"
    }
  ]
}
```

#### Get Database Info

```bash
aitbc edge database get_db --db-id db_123
```

**Expected Output:**
```json
{
  "db_id": "db_123",
  "db_name": "test_db",
  "status": "active",
  "size_mb": 256,
  "last_sync": "2026-05-27T09:10:00Z"
}
```

#### Delete a Database

```bash
aitbc edge database delete_db --db-id db_123
```

**Expected Output:**
```json
{
  "db_id": "db_123",
  "status": "deleted",
  "timestamp": "2026-05-27T09:15:00Z"
}
```

#### Sync a Database

```bash
aitbc edge database sync_db --db-id db_123
```

**Expected Output:**
```json
{
  "db_id": "db_123",
  "sync_status": "completed",
  "records_synced": 1523,
  "duration_seconds": 5.2
}
```

### Step 4: Serve Operations

#### Submit a Serve Request

```bash
aitbc edge serve submit_request --request-type compute --parameters '{"gpu_count": 2, "memory_gb": 32}'
```

**Expected Output:**
```json
{
  "request_id": "req_abc123",
  "request_type": "compute",
  "status": "queued",
  "parameters": {
    "gpu_count": 2,
    "memory_gb": 32
  }
}
```

#### List Serve Requests

```bash
aitbc edge serve list_requests
```

**Expected Output:**
```json
{
  "requests": [
    {
      "request_id": "req_abc123",
      "status": "running",
      "submitted_at": "2026-05-27T09:20:00Z"
    }
  ]
}
```

#### Get Serve Request Info

```bash
aitbc edge serve get_request --request-id req_abc123
```

**Expected Output:**
```json
{
  "request_id": "req_abc123",
  "status": "running",
  "progress": 75,
  "started_at": "2026-05-27T09:20:00Z"
}
```

#### Cancel a Serve Request

```bash
aitbc edge serve cancel_request --request-id req_abc123
```

**Expected Output:**
```json
{
  "request_id": "req_abc123",
  "status": "cancelled",
  "cancelled_at": "2026-05-27T09:25:00Z"
}
```

#### Get Serve Request Result

```bash
aitbc edge serve get_result --request-id req_abc123
```

**Expected Output:**
```json
{
  "request_id": "req_abc123",
  "result": {
    "status": "success",
    "output": "Job completed successfully",
    "metrics": {
      "duration": 120,
      "gpu_hours": 0.67
    }
  }
}
```

### Step 5: Metrics Operations

#### Record a Metric

```bash
aitbc edge metrics record --metric-name gpu_utilization --value 85.5
```

**Expected Output:**
```json
{
  "metric_id": "metric_xyz789",
  "metric_name": "gpu_utilization",
  "value": 85.5,
  "timestamp": "2026-05-27T09:30:00Z"
}
```

#### List Metrics

```bash
aitbc edge metrics list_metrics
```

**Expected Output:**
```json
{
  "metrics": [
    {
      "metric_id": "metric_xyz789",
      "metric_name": "gpu_utilization",
      "value": 85.5,
      "timestamp": "2026-05-27T09:30:00Z"
    }
  ]
}
```

#### Get a Specific Metric

```bash
aitbc edge metrics get_metric --metric-id metric_xyz789
```

**Expected Output:**
```json
{
  "metric_id": "metric_xyz789",
  "metric_name": "gpu_utilization",
  "value": 85.5,
  "timestamp": "2026-05-27T09:30:00Z"
}
```

#### Delete a Metric

```bash
aitbc edge metrics delete_metric --metric-id metric_xyz789
```

**Expected Output:**
```json
{
  "metric_id": "metric_xyz789",
  "status": "deleted",
  "timestamp": "2026-05-27T09:35:00Z"
}
```

---

## 🔧 **Advanced Usage**

### Batch GPU Discovery

```bash
#!/bin/bash
# Scan all edge nodes for GPUs

for node in node1 node2 node3; do
    echo "Scanning $node..."
    aitbc edge gpu scan_gpus --node $node
done
```

### Automated Database Sync

```bash
#!/bin/bash
# Sync all databases periodically

dbs=$(aitbc edge database list_dbs --format json | jq -r '.databases[].db_id')

for db_id in $dbs; do
    echo "Syncing $db_id..."
    aitbc edge database sync_db --db-id $db_id
done
```

### Metrics Aggregation

```bash
#!/bin/bash
# Aggregate GPU utilization metrics

metrics=$(aitbc edge metrics list_metrics --format json | jq -r '.metrics[] | select(.metric_name == "gpu_utilization") | .value')

total=0
count=0
for value in $metrics; do
    total=$(echo "$total + $value" | bc)
    count=$((count + 1))
done

average=$(echo "scale=2; $total / $count" | bc)
echo "Average GPU utilization: $average%"
```

---

## ⚠️ **Important Notes**

### Edge API Availability
- All edge operations require edge-api running at http://127.0.0.1:8200
- Tests will skip if edge-api is not available
- Check edge-api health before operations

### Resource Management
- GPU operations affect actual hardware resources
- Database operations create persistent storage
- Serve requests consume compute resources
- Monitor resource usage to prevent exhaustion

### Island Membership
- Leaving an island deallocates resources
- Bridging islands enables resource sharing
- Island operations affect network topology
- Consider latency when bridging distant islands

### Metrics Retention
- Metrics are stored with timestamps
- Old metrics can be deleted to save space
- Metrics are useful for performance analysis
- Aggregate metrics for trend analysis

---

## 🐛 **Troubleshooting**

### Edge API not available

**Error:**
```
Error: edge-api not running at http://127.0.0.1:8200
```

**Solution:**
```bash
# Check edge-api status
curl http://127.0.0.1:8200/health

# Start edge-api if needed
systemctl start aitbc-edge-api
```

### GPU not found

**Error:**
```
Error: GPU 'gpu_123' not found
```

**Solution:**
```bash
# Scan for available GPUs
aitbc edge gpu scan_gpus

# List all GPUs
aitbc edge gpu list_gpus

# Use correct GPU ID from list
```

### Database sync failed

**Error:**
```
Error: Database sync failed
```

**Solution:**
```bash
# Check database status
aitbc edge database get_db --db-id db_123

# Check network connectivity
ping edge-node

# Retry sync with force flag
aitbc edge database sync_db --db-id db_123 --force
```

### Serve request stuck

**Issue:**
Serve request status shows "running" but not progressing

**Solution:**
```bash
# Cancel stuck request
aitbc edge serve cancel_request --request-id req_123

# Check edge-api logs
journalctl -u aitbc-edge-api -f

# Submit new request
aitbc edge serve submit_request --request-type compute --parameters '{"gpu_count": 2}'
```

---

## 📊 **Testing**

Run the integration test script to verify edge operations:

```bash
# Run pytest tests
cd /opt/aitbc
pytest tests/cli/test_edge_advanced.py -v

# Run bash integration test
scripts/testing/test_edge_advanced.sh
```

**Expected test output:**
```
tests/cli/test_edge_advanced.py::TestEdgeAdvancedCommands::test_edge_island_leave PASSED
tests/cli/test_edge_advanced.py::TestEdgeAdvancedCommands::test_edge_gpu_list_gpus PASSED
tests/cli/test_edge_advanced.py::TestEdgeAdvancedCommands::test_edge_database_init_db PASSED
...
```

---

## 🎓 **Summary**

In this scenario, you learned:
- How to leave and bridge compute islands
- How to discover and manage GPU resources
- How to initialize and sync edge databases
- How to submit and track serve requests
- How to record and query performance metrics
- How to use edge API for distributed compute operations

**Key Takeaways:**
- Edge operations enable low-latency compute at the network edge
- GPU discovery helps optimize resource allocation
- Database sync ensures data consistency across edges
- Serve requests provide on-demand compute resources
- Metrics enable performance monitoring and optimization
- Island management enables flexible network topology

---

## 🔄 **Related Scenarios**
- **Scenario 05**: [Island Creation](./05_island_creation.md) - Basic island operations
- **Scenario 09**: [GPU Listing](./09_gpu_listing.md) - GPU marketplace operations
- **Scenario 49**: [Resource Management](./49_resource_management.md) - Resource allocation
- **Scenario 51**: [Simulation Scenarios](./51_simulation_scenarios.md) - Simulation testing
