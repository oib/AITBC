# CLI Usage

## Setup

```bash
pip install -e .                                    # from monorepo root
aitbc config set coordinator_url http://localhost:8000
export AITBC_API_KEY=your-key                       # or use --api-key
```

## Verify Installation

```bash
# Check CLI version and platform
aitbc --version
aitbc --debug

# Test connectivity
aitbc blockchain status
aitbc --config
```

## Global Options

| Option | Description |
|--------|-------------|
| `--url URL` | Coordinator API URL |
| `--api-key KEY` | API key for authentication |
| `--output table\|json\|yaml` | Output format |
| `-v / -vv / -vvv` | Verbosity level |
| `--debug` | Debug mode with system information |
| `--config` | Show current configuration |

## Enhanced Command Groups

| Group | Key commands |
|-------|-------------|
| `agent` | `workflow create`, `execute`, `network`, `learning enable` |
| `multimodal` | `agent`, `process`, `convert`, `search` |
| `optimize` | `enable`, `status`, `recommendations`, `apply`, `predict`, `tune` |
| `openclaw` | `deploy`, `status`, `optimize`, `edge`, `routing`, `ecosystem` |
| `marketplace` | `list`, `gpu list`, `offer create`, `gpu rent`, `orders`, `reviews` |
| `swarm` | `join`, `coordinate`, `consensus` |
| `client` | `submit`, `status`, `list`, `cancel`, `download`, `batch-submit` |
| `miner` | `register`, `poll`, `mine`, `earnings`, `deregister` |
| `wallet` | `create`, `balance`, `send`, `stake`, `backup`, `multisig-create` |
| `auth` | `login`, `logout`, `token`, `keys` |
| `blockchain` | `status`, `sync`, `info`, `peers`, `blocks`, `transaction`, `validators` |
| `admin` | `status`, `jobs`, `miners`, `audit-log` |
| `config` | `set`, `show`, `profiles`, `secrets`, `get` |
| `monitor` | `dashboard`, `metrics`, `alerts`, `webhooks` |
| `simulate` | `workflow`, `load-test`, `scenario` |

## Enhanced Client Workflow

```bash
# Setup and configuration
aitbc wallet create --name my-wallet               # create wallet
aitbc wallet balance                                 # check funds
aitbc config show                                   # verify configuration

# Job submission with enhanced options
aitbc client submit --prompt "What is AI?" \
  --model gpt2 \
  --priority normal \
  --timeout 3600

# Job tracking and management
aitbc client status --job-id <JOB_ID>               # check progress
aitbc client download --job-id <JOB_ID> --output ./ # get results
aitbc client list --status completed                 # list completed jobs
```

## Agent Workflow (New)

```bash
# Agent workflow management
aitbc agent workflow create \
  --name "ai_inference" \
  --description "AI inference workflow" \
  --config '{"model": "gpt2", "type": "inference"}'

# Execute agent workflow
aitbc agent execute ai_inference \
  --input '{"prompt": "Hello world"}' \
  --priority normal

# Agent learning and optimization
aitbc agent learning enable --agent-id agent_123 \
  --mode performance \
  --auto-tune

# Agent networks
aitbc agent network create \
  --name "compute_network" \
  --type "resource_sharing"
```

## OpenClaw Deployment (New)

```bash
# Deploy applications
aitbc openclaw deploy \
  --name "web_app" \
  --image "nginx:latest" \
  --replicas 3 \
  --region "us-west"

# Monitor and optimize deployments
aitbc openclaw status web_app
aitbc openclaw optimize web_app \
  --target performance \
  --auto-tune

# Edge deployments
aitbc openclaw edge deploy \
  --name "edge_service" \
  --compute "gpu" \
  --region "edge_location"
```

## Optimization Features (New)

```bash
# Enable agent optimization
aitbc optimize enable --agent-id agent_123 \
  --mode performance \
  --auto-tune

# Get optimization recommendations
aitbc optimize recommendations --agent-id agent_123

# Apply optimizations
aitbc optimize apply --agent-id agent_123 \
  --recommendation-id rec_456

# Predictive scaling
aitbc optimize predict --agent-id agent_123 \
  --metric cpu_usage \
  --horizon 1h

# Auto-tuning
aitbc optimize tune --agent-id agent_123 \
  --objective performance \
  --constraints '{"cost": "<100"}'
```

## Enhanced Marketplace Operations

```bash
# List available GPUs
aitbc marketplace gpu list

# Register GPU offer
aitbc marketplace offer create \
  --miner-id gpu_miner_123 \
  --gpu-model "RTX-4090" \
  --gpu-memory "24GB" \
  --price-per-hour "0.05" \
  --models "gpt2,llama" \
  --endpoint "http://localhost:11434"

# Rent GPU
aitbc marketplace gpu rent --gpu-id gpu_789 --duration 2h

# Track orders and reviews
aitbc marketplace orders --status active
aitbc marketplace reviews --miner-id gpu_miner_123
```

## Enhanced Blockchain Operations

```bash
# Blockchain status and synchronization
aitbc blockchain status
aitbc blockchain sync
aitbc blockchain info

# Network and peers
aitbc blockchain peers
aitbc blockchain blocks --limit 10

# Transactions and validators
aitbc blockchain transaction <TX_ID>
aitbc blockchain validators
```

## Enhanced Configuration Management

```bash
# Configuration management
aitbc config show
aitbc config set coordinator_url http://localhost:8000
aitbc config get api_key
aitbc config profiles list
aitbc config profiles create development

# Secrets management
aitbc config secrets set api_key your_secret_key
aitbc config secrets get api_key
```

## Debug and Troubleshooting

```bash
# Debug mode with system information
aitbc --debug

# Monitor CLI performance
aitbc monitor dashboard
aitbc monitor metrics --component cli

# Simulation and testing
aitbc simulate workflow --test-scenario basic
aitbc simulate load-test --concurrent-users 10
```

## Miner Workflow

```bash
aitbc miner register --name gpu-1 --gpu a100 --count 4
aitbc miner poll                                    # start accepting jobs
aitbc wallet balance                                # check earnings
```

## Advanced AI Agent Workflows

```bash
# Create and execute advanced AI agents
aitbc agent create --name "MultiModal Agent" --workflow-file workflow.json --verification full
aitbc agent execute agent_123 --inputs inputs.json --verification zero-knowledge

# Multi-modal processing
aitbc multimodal agent create --name "Vision-Language Agent" --modalities text,image --gpu-acceleration
aitbc multimodal process agent_123 --text "Describe this image" --image photo.jpg

# Autonomous optimization
aitbc optimize self-opt enable agent_123 --mode auto-tune --scope full
aitbc optimize predict agent_123 --horizon 24h --resources gpu,memory
```

## Agent Collaboration & Learning

```bash
# Create collaborative agent networks
aitbc agent network create --name "Research Team" --agents agent1,agent2,agent3
aitbc agent network execute network_123 --task research_task.json

# Adaptive learning
aitbc agent learning enable agent_123 --mode reinforcement --learning-rate 0.001
aitbc agent learning train agent_123 --feedback feedback.json --epochs 50
```

## OpenClaw Edge Deployment

```bash
# Deploy to OpenClaw network
aitbc openclaw deploy agent_123 --region us-west --instances 3 --auto-scale
aitbc openclaw edge deploy agent_123 --locations "us-west,eu-central" --strategy latency

# Monitor and optimize
aitbc openclaw monitor deployment_123 --metrics latency,cost --real-time
aitbc openclaw optimize deployment_123 --objective cost
```

## Advanced Marketplace Operations

```bash
# Advanced NFT model operations
aitbc marketplace advanced models list --nft-version 2.0 --category multimodal
aitbc marketplace advanced mint --model-file model.pkl --metadata metadata.json --royalty 5.0

# Analytics and trading
aitbc marketplace advanced analytics --period 30d --metrics volume,trends
aitbc marketplace advanced trading execute --strategy arbitrage --budget 5000
```

## Swarm Intelligence

```bash
# Join swarm for collective optimization
aitbc swarm join --role load-balancer --capability resource-optimization
aitbc swarm coordinate --task network-optimization --collaborators 10
```

## Configuration

Config file: `~/.aitbc/config.yaml`
```yaml
coordinator_url: http://localhost:8000
api_key: your-api-key
output_format: table
log_level: INFO
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Auth error | `export AITBC_API_KEY=your-key` or `aitbc auth login` |
| Connection refused | Check coordinator: `curl http://localhost:8000/v1/health` |
| Unknown command | Update CLI: `pip install -e .` from monorepo root |
| Agent command not found | Ensure advanced agent commands are installed: `pip install -e .` |
| Multi-modal processing error | Check GPU availability: `nvidia-smi` |
| OpenClaw deployment failed | Verify OpenClaw credentials and region access |
| Marketplace NFT error | Check model file format and metadata structure |

## Advanced Agent Documentation

See [docs/11_agents/](../11_agents/) for detailed guides:
- [Advanced AI Agents](../11_agents/advanced-ai-agents.md) - Multi-modal and adaptive agents
- [Agent Collaboration](../11_agents/collaborative-agents.md) - Networks and learning
- [OpenClaw Integration](../11_agents/openclaw-integration.md) - Edge deployment
- [Swarm Intelligence](../11_agents/swarm/) - Collective optimization

## Full Reference

See [5_reference/1_cli-reference.md](../5_reference/1_cli-reference.md) for all 90+ commands with detailed options.
