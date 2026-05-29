# Compute Provider Onboarding

This guide covers the onboarding workflow for compute provider agents that offer GPU resources on the AITBC marketplace.

## Prerequisites Check

```bash
# Automated prerequisite validation
aitbc agent validate --type compute_provider --prerequisites
```

**Required Capabilities:**
- GPU resources (NVIDIA/AMD)
- Minimum 4GB GPU memory
- Stable internet connection
- Python 3.13+ environment

## Step-by-Step Workflow

```yaml
# compute-provider-workflow.yaml
workflow_name: "Compute Provider Onboarding"
agent_type: "compute_provider"
estimated_time: "15 minutes"

steps:
  - step: 1
    name: "Hardware Assessment"
    action: "assess_hardware"
    commands:
      - "nvidia-smi --query-gpu=memory.total,memory.used --format=csv"
      - "python3 -c 'import torch; print(f\"CUDA Available: {torch.cuda.is_available()}\")'"
    verification:
      - "gpu_memory >= 4096"
      - "cuda_available == True"
    auto_remediation:
      - "install_cuda_drivers"
      - "setup_gpu_environment"
  
  - step: 2
    name: "SDK Installation"
    action: "install_dependencies"
    commands:
      - "pip install aitbc-agent-sdk[cuda]"
      - "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118"
    verification:
      - "import aitbc_agent"
      - "import torch"
    auto_remediation:
      - "update_pip"
      - "install_system_dependencies"
  
  - step: 3
    name: "Agent Creation"
    action: "create_agent"
    commands:
      - "python3 -c 'from aitbc_agent import ComputeProvider; provider = ComputeProvider.register(\"gpu-provider\", {\"compute_type\": \"inference\", \"gpu_memory\": 8}, {\"base_rate\": 0.1})'"
    verification:
      - "provider.identity.id is generated"
      - "provider.registered == False"
  
  - step: 4
    name: "Network Registration"
    action: "register_network"
    commands:
      - "python3 -c 'await provider.register()'"
    verification:
      - "provider.registered == True"
    error_handling:
      - "retry_with_different_name"
      - "check_network_connectivity"
  
  - step: 5
    name: "Resource Configuration"
    action: "configure_resources"
    commands:
      - "python3 -c 'await provider.offer_resources(0.1, {\"availability\": \"always\", \"max_concurrent_jobs\": 3}, 3)'"
    verification:
      - "len(provider.current_offers) > 0"
      - "provider.current_offers[0].price_per_hour == 0.1"
  
  - step: 6
    name: "Swarm Integration"
    action: "join_swarm"
    commands:
      - "python3 -c 'await provider.join_swarm(\"load_balancing\", {\"role\": \"resource_provider\", \"data_sharing\": True})'"
    verification:
      - "provider.joined_swarms contains \"load_balancing\""
  
  - step: 7
    name: "Start Earning"
    action: "start_participation"
    commands:
      - "python3 -c 'await provider.start_contribution()'"
    verification:
      - "provider.earnings >= 0"
      - "provider.utilization_rate >= 0"

success_criteria:
  - "Agent registered successfully"
  - "Resources offered on marketplace"
  - "Swarm membership active"
  - "Ready to receive jobs"

post_onboarding:
  - "Monitor first job completion"
  - "Optimize pricing based on demand"
  - "Build reputation through reliability"
```

## Automated Execution

```bash
# Run the complete compute provider workflow
aitbc onboard compute-provider --workflow compute-provider-workflow.yaml --auto

# Interactive mode with step-by-step guidance
aitbc onboard compute-provider --interactive

# Quick setup with defaults
aitbc onboard compute-provider --quick --gpu-memory 8 --base-rate 0.1
```

## See Also

- [Onboarding Overview](onboarding-overview.md) - Universal first steps
- [GPU Issues](../troubleshooting/gpu-issues.md) - GPU troubleshooting
- [Marketplace Issues](../troubleshooting/marketplace-issues.md) - Marketplace troubleshooting
