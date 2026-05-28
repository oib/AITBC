# Workflow Management for hermes Agents

**Level**: Intermediate  
**Prerequisites**: Basic CLI knowledge, AITBC CLI installed, coordinator-api running  
**Estimated Time**: 20 minutes  
**Last Updated**: 2026-05-27  
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../README.md)** → **🎭 [Agent Scenarios](./README.md)** → *You are here*

**breadcrumb**: Home → Scenarios → Workflow Management

---

## 🎯 **See Also:**
- **📖 Previous Scenario**: [48 Configuration Profiles](./48_config_profiles.md)
- **📖 Next Scenario**: [51 Simulation Scenarios](./51_simulation_scenarios.md)
- **⚙️ Workflow Documentation**: [CLI Workflow Commands](../cli/CLI_DOCUMENTATION.md)

---

## 📚 **Scenario Overview**

This scenario demonstrates how hermes agents use workflow management to orchestrate complex multi-step operations. Workflows enable agents to execute predefined sequences of tasks such as GPU marketplace operations, AI job processing, and mining optimization.

### **Use Case**
An hermes agent needs to:
- Execute complex multi-step operations automatically
- Track workflow execution status and progress
- Stop running workflows when needed
- Manage multiple concurrent workflows
- Use dry-run mode to validate workflows before execution

### **What You'll Learn**
- List available workflows
- Run workflows with configuration
- Check workflow execution status
- Stop running workflows
- Use dry-run mode for validation
- Create custom workflow configurations

### **Features Combined**
- **Workflow Execution**: Run predefined and custom workflows
- **Status Tracking**: Monitor workflow progress and state
- **Workflow Control**: Start, stop, and manage workflows
- **Configuration Support**: Use config files for workflow parameters
- **Dry-Run Mode**: Validate workflows without execution

---

## 📋 **Prerequisites**

### **Knowledge Required**
- Basic command-line interface usage
- Understanding of YAML configuration files
- AITBC CLI installed and accessible
- coordinator-api running (for API-integrated workflows)

### **System Requirements**
- AITBC CLI installed
- coordinator-api running (http://127.0.0.1:8011)
- Write access to current directory for config files

---

## 🚀 **Quick Start**

```bash
# List available workflows
aitbc workflow list

# Run a workflow
aitbc workflow run gpu-marketplace

# Check workflow status
aitbc workflow status gpu-marketplace

# Stop a running workflow
aitbc workflow stop gpu-marketplace
```

---

## 📖 **Detailed Steps**

### Step 1: List Available Workflows

View all available workflows and their status:

```bash
aitbc workflow list
```

**Expected Output:**
```
Available workflows:
  - gpu-marketplace: active (5 steps)
  - ai-job-processing: active (3 steps)
  - mining-optimization: inactive (4 steps)
```

**JSON format:**
```bash
aitbc workflow list --format json
```

**Expected JSON Output:**
```json
[
  {
    "name": "gpu-marketplace",
    "status": "active",
    "steps": 5
  },
  {
    "name": "ai-job-processing",
    "status": "active",
    "steps": 3
  },
  {
    "name": "mining-optimization",
    "status": "inactive",
    "steps": 4
  }
]
```

### Step 2: Run Workflow (Dry Run)

Validate a workflow without executing it:

```bash
aitbc workflow run gpu-marketplace --dry-run
```

**Expected Output:**
```
Dry run for workflow gpu-marketplace
Would execute workflow without making changes
```

**What happens:**
- Workflow validation performed
- No actual execution
- Useful for testing workflow configuration

### Step 3: Run Workflow with Configuration

Create a workflow configuration file:

```bash
cat > workflow_config.yaml << EOF
gpu_count: 4
max_price: 100.0
min_memory_gb: 16
timeout: 300
EOF
```

Run workflow with configuration:

```bash
aitbc workflow run gpu-marketplace --config workflow_config.yaml
```

**Expected Output:**
```
Run workflow gpu-marketplace
Using config: workflow_config.yaml
Execution ID: wf_exec_1716789123
Status: Running
```

**What happens:**
- Workflow started with configuration
- Unique execution ID assigned
- Workflow begins executing steps

### Step 4: Check Workflow Status

Monitor workflow execution:

```bash
aitbc workflow status gpu-marketplace
```

**Expected Output:**
```
Get status for workflow gpu-marketplace
Status: Running
Last execution: 2026-05-27 08:30:45
Current step: 2/5
Progress: 40%
```

**What happens:**
- Current workflow state retrieved
- Execution progress displayed
- Step-by-step status shown

### Step 5: Stop Running Workflow

Terminate a running workflow:

```bash
aitbc workflow stop gpu-marketplace
```

**Expected Output:**
```
Stop workflow gpu-marketplace
Workflow stopped successfully
```

**What happens:**
- Workflow execution terminated
- Resources cleaned up
- Status updated to stopped

### Step 6: Run AI Job Processing Workflow

Execute AI job workflow:

```bash
aitbc workflow run ai-job-processing
```

**Expected Output:**
```
Run workflow ai-job-processing
Execution ID: wf_exec_1716789234
Status: Running
```

Check status:

```bash
aitbc workflow status ai-job-processing
```

**Expected Output:**
```
Get status for workflow ai-job-processing
Status: Completed
Last execution: 2026-05-27 08:35:12
Duration: 45 seconds
Jobs processed: 10
```

---

## 🔧 **Advanced Usage**

### Custom Workflow Names

Use custom workflow names with various formats:

```bash
# With dashes
aitbc workflow run my-custom-workflow

# With underscores
aitbc workflow run my_custom_workflow

# With dots
aitbc workflow run my.workflow

# CamelCase
aitbc workflow run MyWorkflow
```

### Workflow Configuration Parameters

Create detailed configuration files:

```yaml
# gpu_workflow_config.yaml
workflow:
  name: gpu-marketplace
  parallel: true
  
resources:
  gpu:
    count: 4
    min_memory_gb: 16
    architecture: "NVIDIA"
    edge_optimized: true
  
pricing:
  max_price: 100.0
  bid_strategy: "aggressive"
  
execution:
  timeout: 300
  retry_count: 3
  on_failure: "continue"
```

Run with detailed config:

```bash
aitbc workflow run gpu-marketplace --config gpu_workflow_config.yaml
```

### Batch Workflow Execution

Run multiple workflows sequentially:

```bash
#!/bin/bash
# run_workflows.sh

workflows=("gpu-marketplace" "ai-job-processing" "mining-optimization")

for wf in "${workflows[@]}"; do
    echo "Running workflow: $wf"
    aitbc workflow run "$wf"
    
    # Wait for completion
    while true; do
        status=$(aitbc workflow status "$wf" --format json | jq -r '.status')
        if [ "$status" = "Completed" ] || [ "$status" = "Failed" ]; then
            break
        fi
        sleep 5
    done
done
```

### Workflow Monitoring

Monitor workflow with continuous status checks:

```bash
#!/bin/bash
# monitor_workflow.sh

workflow_name=$1

while true; do
    clear
    aitbc workflow status "$workflow_name"
    sleep 2
done
```

Usage:

```bash
./monitor_workflow.sh gpu-marketplace
```

---

## ⚠️ **Important Notes**

### Workflow Execution IDs
- Each workflow execution gets a unique ID: `wf_exec_<timestamp>`
- Use execution IDs for tracking and debugging
- IDs are generated automatically

### Workflow States
- **Running**: Workflow currently executing
- **Completed**: Workflow finished successfully
- **Failed**: Workflow encountered an error
- **Stopped**: Workflow manually terminated
- **Pending**: Workflow queued for execution

### Configuration File Format
- YAML format supported
- JSON format supported
- Must be valid YAML/JSON syntax
- Parameters depend on workflow type

### Dry-Run Limitations
- No actual execution
- No side effects
- Validation only
- Useful for testing

---

## 🐛 **Troubleshooting**

### Workflow not found

**Error:**
```
Error: Workflow 'my_workflow' not found
```

**Solution:**
```bash
# List available workflows
aitbc workflow list

# Check workflow name spelling
aitbc workflow run gpu-marketplace  # Correct
aitbc workflow run gpu_marketplace  # Incorrect
```

### Configuration file error

**Error:**
```
Error: Invalid configuration file
```

**Solution:**
```bash
# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('workflow_config.yaml'))"

# Check file path
ls -la workflow_config.yaml

# Use absolute path
aitbc workflow run gpu-marketplace --config /full/path/to/config.yaml
```

### Workflow stuck in running state

**Issue:**
Workflow status shows "Running" but not progressing

**Solution:**
```bash
# Stop the workflow
aitbc workflow stop stuck_workflow

# Check coordinator-api status
curl http://127.0.0.1:8011/health

# Review workflow logs
# (Location depends on workflow implementation)
```

### Permission denied on config file

**Error:**
```
Error: Permission denied reading config file
```

**Solution:**
```bash
# Check file permissions
ls -la workflow_config.yaml

# Fix permissions
chmod 644 workflow_config.yaml

# Use different location
aitbc workflow run gpu-marketplace --config ~/configs/workflow.yaml
```

---

## 📊 **Testing**

Run the integration test script to verify workflow operations:

```bash
# Run pytest tests
cd /opt/aitbc
pytest tests/cli/test_workflow.py -v

# Run bash integration test
scripts/testing/test_workflow_cli.sh
```

**Expected test output:**
```
tests/cli/test_workflow.py::TestWorkflowCommands::test_workflow_run_basic PASSED
tests/cli/test_workflow.py::TestWorkflowCommands::test_workflow_list PASSED
tests/cli/test_workflow.py::TestWorkflowCommands::test_workflow_status PASSED
tests/cli/test_workflow.py::TestWorkflowCommands::test_workflow_stop PASSED
...
```

---

## 🎓 **Summary**

In this scenario, you learned:
- How to list available workflows
- How to run workflows with and without configuration
- How to check workflow execution status
- How to stop running workflows
- How to use dry-run mode for validation
- How to create custom workflow configurations

**Key Takeaways:**
- Workflows orchestrate complex multi-step operations
- Each execution gets a unique ID for tracking
- Dry-run mode validates without execution
- Configuration files customize workflow behavior
- Status monitoring enables workflow control

---

## 🔄 **Related Scenarios**
- **Scenario 07**: [AI Job Submission](./07_ai_job_submission.md) - AI job operations
- **Scenario 09**: [GPU Listing](./09_gpu_listing.md) - GPU marketplace operations
- **Scenario 13**: [Mining Setup](./13_mining_setup.md) - Mining operations
- **Scenario 48**: [Configuration Profiles](./48_config_profiles.md) - Config management
