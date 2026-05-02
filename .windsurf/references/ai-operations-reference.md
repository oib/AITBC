# AITBC AI Operations Reference

This reference guide covers AI operations in the AITBC blockchain network, including job submission, resource allocation, marketplace interactions, agent coordination, and blockchain integration.

## Table of Contents
- [AI Job Types and Parameters](#ai-job-types-and-parameters)
- [Ollama Integration](#ollama-integration)
- [Resource Allocation](#resource-allocation)
- [Marketplace Operations](#marketplace-operations)
- [GPU Provider Marketplace](#gpu-provider-marketplace)
- [Agent AI Workflows](#agent-ai-workflows)
- [OpenClaw Agent Coordination](#openclaw-agent-coordination)
- [Cross-Node AI Coordination](#cross-node-ai-coordination)
- [Blockchain Integration](#blockchain-integration)
- [AI Economics and Pricing](#ai-economics-and-pricing)
- [AI Monitoring and Analytics](#ai-monitoring-and-analytics)
- [API Endpoints](#api-endpoints)
- [AI Security and Compliance](#ai-security-and-compliance)
- [Troubleshooting AI Operations](#troubleshooting-ai-operations)
- [Best Practices](#best-practices)
- [Real-World Workflows](#real-world-workflows)

## AI Job Types and Parameters

### Inference Jobs
```bash
# Basic image generation
./aitbc-cli ai job submit --wallet genesis-ops --type inference --prompt "Generate image of futuristic city" --payment 100

# Text analysis
./aitbc-cli ai job submit --wallet genesis-ops --type inference --prompt "Analyze sentiment of this text" --payment 50

# Code generation
./aitbc-cli ai job submit --wallet genesis-ops --type inference --prompt "Generate Python function for data processing" --payment 75
```

### Training Jobs
```bash
# Model training
./aitbc-cli ai job submit --wallet genesis-ops --type training --model "custom-model" --dataset "training_data.json" --payment 500

# Fine-tuning
./aitbc-cli ai job submit --wallet genesis-ops --type training --model "gpt-3.5-turbo" --dataset "fine_tune_data.json" --payment 300
```

### Multimodal Jobs
```bash
# Image analysis
./aitbc-cli ai job submit --wallet genesis-ops --type multimodal --prompt "Analyze this image" --image-path "/path/to/image.jpg" --payment 200

# Audio processing
./aitbc-cli ai job submit --wallet genesis-ops --type multimodal --prompt "Transcribe audio" --audio-path "/path/to/audio.wav" --payment 150

# Video analysis
./aitbc-cli ai job submit --wallet genesis-ops --type multimodal --prompt "Analyze video content" --video-path "/path/to/video.mp4" --payment 300
```

### Streaming Jobs
```bash
# Real-time inference streaming
./aitbc-cli ai job submit --wallet genesis-ops --type inference --prompt "Generate story" --stream true --payment 150

# Continuous monitoring
./aitbc-cli ai job submit --wallet genesis-ops --type monitoring --target "network" --interval 60 --payment 200
```

## Ollama Integration

### Ollama Model Operations
```bash
# List available Ollama models
python3 /opt/aitbc/plugins/ollama/client_plugin.py --list-models

# Run inference with Ollama
python3 /opt/aitbc/plugins/ollama/client_plugin.py --model llama2 --prompt "Generate code for REST API"

# Submit Ollama job via CLI
./aitbc-cli ai job submit --wallet genesis-ops --type ollama --model "llama2:7b" --prompt "Analyze this data" --payment 50

# Use custom Ollama endpoint
./aitbc-cli ai job submit --wallet genesis-ops --type ollama --endpoint "http://localhost:11434" --model "mistral" --prompt "Generate summary" --payment 75
```

### Ollama GPU Provider Integration
```bash
# Register as Ollama GPU provider
./aitbc-cli gpu provider register --type ollama --models "llama2,mistral,codellama" --gpu-count 1 --price 0.05

# Submit Ollama job to specific provider
./aitbc-cli ai job submit --wallet genesis-ops --type ollama --provider "provider_123" --model "llama2" --prompt "Generate text" --payment 50

# Monitor Ollama provider status
./aitbc-cli gpu provider status --provider-id "provider_123"
```

### Ollama Batch Operations
```bash
# Batch inference
./aitbc-cli ai job submit --wallet genesis-ops --type ollama --model "llama2" --batch-file "prompts.json" --payment 200

# Parallel Ollama jobs
./aitbc-cli ai job submit --wallet genesis-ops --type ollama --model "mistral" --parallel 4 --prompts "prompt1,prompt2,prompt3,prompt4" --payment 150
```

## Resource Allocation

### GPU Resources
```bash
# Single GPU allocation
./aitbc-cli resource allocate --agent-id ai-inference-worker --gpu 1 --memory 8192 --duration 3600

# Multiple GPU allocation
./aitbc-cli resource allocate --agent-id ai-training-agent --gpu 2 --memory 16384 --duration 7200

# GPU with specific model
./aitbc-cli resource allocate --agent-id ai-agent --gpu 1 --memory 8192 --duration 3600 --model "stable-diffusion"
```

### CPU Resources
```bash
# CPU allocation for preprocessing
./aitbc-cli resource allocate --agent-id data-processor --cpu 4 --memory 4096 --duration 1800

# High-performance CPU allocation
./aitbc-cli resource allocate --agent-id ai-trainer --cpu 8 --memory 16384 --duration 7200
```

## Marketplace Operations

### Service Provider Registration
```bash
# Register as AI service provider
./aitbc-cli market provider register --name "AI-Service-Pro" --wallet genesis-ops --verification full

# Update service listing
./aitbc-cli market service update --service-id "service_123" --price 60 --description "Updated description"

# Deactivate service
./aitbc-cli market service deactivate --service-id "service_123"
```

### Creating AI Services
```bash
# Image generation service
./aitbc-cli market service create --name "AI Image Generation" --type ai-inference --price 50 --wallet genesis-ops --description "Generate high-quality images from text prompts"

# Model training service
./aitbc-cli market service create --name "Custom Model Training" --type ai-training --price 200 --wallet genesis-ops --description "Train custom models on your data"

# Data analysis service
./aitbc-cli market service create --name "AI Data Analysis" --type ai-processing --price 75 --wallet genesis-ops --description "Analyze and process datasets with AI"
```

### Marketplace Interaction
```bash
# List available services
./aitbc-cli market service list

# Search for specific services
./aitbc-cli market service search --query "image generation"

# Bid on service
./aitbc-cli market order bid --service-id "service_123" --amount 60 --wallet genesis-ops

# Execute purchased service
./aitbc-cli market order execute --service-id "service_123" --job-data "prompt:Generate landscape image"
```

## GPU Provider Marketplace

### GPU Provider Registration
```bash
# Register as GPU provider
./aitbc-cli gpu provider register --name "GPU-Provider-1" --wallet genesis-ops --gpu-model "RTX4090" --gpu-count 4 --price 0.10

# Register Ollama-specific provider
./aitbc-cli gpu provider register --name "Ollama-Node" --type ollama --models "llama2,mistral" --gpu-count 2 --price 0.05

# Update provider capacity
./aitbc-cli gpu provider update --provider-id "provider_123" --gpu-count 8 --price 0.08
```

### GPU Provider Operations
```bash
# List available GPU providers
./aitbc-cli gpu provider list

# Search for specific GPU models
./aitbc-cli gpu provider search --model "RTX4090"

# Check provider availability
./aitbc-cli gpu provider availability --provider-id "provider_123"

# Get provider pricing
./aitbc-cli gpu provider pricing --provider-id "provider_123"
```

### GPU Allocation from Providers
```bash
# Allocate from specific provider
./aitbc-cli resource allocate --provider-id "provider_123" --gpu 2 --memory 16384 --duration 3600

# Auto-select best provider
./aitbc-cli resource allocate --auto-select --gpu 1 --memory 8192 --duration 1800 --criteria price

# Allocate with provider preferences
./aitbc-cli resource allocate --preferred-providers "provider_123,provider_456" --gpu 1 --memory 8192 --duration 3600
```

### GPU Provider Earnings
```bash
# Check provider earnings
./aitbc-cli gpu provider earnings --provider-id "provider_123" --period "7d"

# Withdraw earnings
./aitbc-cli gpu provider withdraw --provider-id "provider_123" --wallet genesis-ops --amount 1000

# Provider utilization report
./aitbc-cli gpu provider utilization --provider-id "provider_123" --period "24h"
```

## Agent AI Workflows

### Creating AI Agents
```bash
# Inference agent
./aitbc-cli agent create --name "ai-inference-worker" --description "Specialized agent for AI inference tasks" --verification full

# Training agent
./aitbc-cli agent create --name "ai-training-agent" --description "Specialized agent for AI model training" --verification full

# Coordination agent
./aitbc-cli agent create --name "ai-coordinator" --description "Coordinates AI jobs across nodes" --verification full
```

### Executing AI Agents
```bash
# Execute inference agent
./aitbc-cli agent execute --name "ai-inference-worker" --wallet genesis-ops --priority high

# Execute training agent with parameters
./aitbc-cli agent execute --name "ai-training-agent" --wallet genesis-ops --priority high --parameters "model:gpt-3.5-turbo,dataset:training.json"

# Execute coordinator agent
./aitbc-cli agent execute --name "ai-coordinator" --wallet genesis-ops --priority high
```

## OpenClaw Agent Coordination

> **Canonical validation**: Use [`docs/scenarios/VALIDATION.md`](../../docs/scenarios/VALIDATION.md) and `scripts/workflow/44_comprehensive_multi_node_scenario.sh` for the current 3-node test path.

### OpenClaw AI Agent Setup
```bash
# Initialize OpenClaw AI agent
openclaw agent init --name ai-inference-agent --type ai-worker

# Configure agent for AI operations
openclaw agent configure --name ai-inference-agent --ai-model "llama2" --gpu-requirement 1

# Deploy agent to node
openclaw agent deploy --name ai-inference-agent --target-node aitbc1
```

### OpenClaw AI Workflows
```bash
# Execute AI workflow via OpenClaw
openclaw execute --agent AI-InferenceAgent --task run_inference --prompt "Generate image" --model "stable-diffusion"

# Coordinate multi-agent AI pipeline
openclaw execute --agent CoordinatorAgent --task ai_pipeline --workflow "preprocess->inference->postprocess"

# Monitor agent AI performance
openclaw monitor --agent AI-InferenceAgent --metrics gpu,throughput,errors
```

### Cross-Agent Communication
```bash
# Send AI job result to another agent
openclaw message --from AI-InferenceAgent --to Data-ProcessingAgent --payload "job_id:123,result:image.png"

# Request resources from coordinator
openclaw message --from AI-TrainingAgent --to Resource-CoordinatorAgent --payload "request:gpu,count:2,duration:3600"

# Broadcast job completion
openclaw broadcast --from AI-InferenceAgent --channel ai-jobs --payload "job_123:completed"
```

## Cross-Node AI Coordination

### Multi-Node Job Submission
```bash
# Submit to specific node
./aitbc-cli ai job submit --wallet genesis-ops --type inference --prompt "Generate image" --target-node "aitbc1" --payment 100

# Distribute training across nodes
./aitbc-cli ai job submit --wallet genesis-ops --type training --model "distributed-model" --nodes "aitbc,aitbc1" --payment 500
```

### Cross-Node Resource Management
```bash
# Allocate resources on follower node
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli resource allocate --agent-id ai-agent --gpu 1 --memory 8192 --duration 3600'

# Monitor multi-node AI status
./aitbc-cli ai job status --multi-node
```

## Blockchain Integration

### AI Job on Blockchain
```bash
# Submit AI job with blockchain recording
./aitbc-cli ai job submit --wallet genesis-ops --type inference --prompt "Generate image" --payment 100 --record-on-chain

# Verify AI job on blockchain
./aitbc-cli blockchain verify --job-id "job_123" --check-integrity

# Get AI job transaction hash
./aitbc-cli ai job tx-hash --job-id "job_123"
```

### AI Payments via Blockchain
```bash
# Pay for AI job with blockchain transaction
./aitbc-cli ai payment pay --job-id "job_123" --wallet genesis-ops --amount 100 --on-chain

# Check payment status on blockchain
./aitbc-cli blockchain tx-status --tx-hash "0x123...abc"

# Get AI payment history
./aitbc-cli ai payment history --wallet genesis-ops --on-chain
```

### AI Smart Contract Integration
```bash
# Deploy AI service smart contract
./aitbc-cli contract deploy --type ai-service --name "AI-Inference-Service" --wallet genesis-ops

# Interact with AI smart contract
./aitbc-cli contract call --contract "0x123...abc" --method submitJob --params "prompt:Generate image,payment:100"

# Query AI smart contract state
./aitbc-cli contract query --contract "0x123...abc" --method getJobStatus --params "job_id:123"
```

### AI Data Verification
```bash
# Verify AI output integrity
./aitbc-cli ai verify --job-id "job_123" --check-hash --check-signature

# Generate AI output proof
./aitbc-cli ai proof --job-id "job_123" --output-path "/path/to/output.png"

# Store AI result on blockchain
./aitbc-cli ai store --job-id "job_123" --ipfs --on-chain
```

## AI Economics and Pricing

### Job Cost Estimation
```bash
# Estimate inference job cost
./aitbc-cli ai estimate --type inference --prompt-length 100 --resolution 512

# Estimate training job cost
./aitbc-cli ai estimate --type training --model-size "1B" --dataset-size "1GB" --epochs 10
```

### Payment and Earnings
```bash
# Pay for AI job
./aitbc-cli ai payment pay --job-id "job_123" --wallet genesis-ops --amount 100

# Check AI earnings
./aitbc-cli ai payment earnings --wallet genesis-ops --period "7d"
```

## AI Monitoring and Analytics

### Advanced Metrics
```bash
# Detailed job metrics
./aitbc-cli ai metrics detailed --job-id "job_123" --include gpu,memory,network,io

# Agent performance comparison
./aitbc-cli ai metrics compare --agents "agent1,agent2,agent3" --period "24h"

# Cost analysis
./aitbc-cli ai metrics cost --wallet genesis-ops --period "30d" --breakdown job_type,provider

# Error analysis
./aitbc-cli ai metrics errors --period "7d" --group-by error_type
```

### Real-time Monitoring
```bash
# Stream live metrics
./aitbc-cli ai monitor live --job-id "job_123"

# Monitor multiple jobs
./aitbc-cli ai monitor multi --job-ids "job1,job2,job3"

# Set up alerts
./aitbc-cli ai alert create --condition "job_duration > 3600" --action notify --email admin@example.com
```

### Job Monitoring
```bash
# Monitor specific job
./aitbc-cli ai job status --job-id "job_123"

# Monitor all jobs
./aitbc-cli ai job status --all

# Job history
./aitbc-cli ai job history --wallet genesis-ops --limit 10
```

### Performance Metrics
```bash
# AI performance metrics
./aitbc-cli ai metrics --agent-id "ai-inference-worker" --period "1h"

# Resource utilization
./aitbc-cli resource utilization --type gpu --period "1h"

# Job throughput
./aitbc-cli ai metrics throughput --nodes "aitbc,aitbc1" --period "24h"
```

## API Endpoints

### AI Job API
```bash
# Submit AI job via API
curl -X POST http://localhost:8006/api/ai/job/submit \
  -H "Content-Type: application/json" \
  -d '{"wallet":"genesis-ops","type":"inference","prompt":"Generate image","payment":100}'

# Get job status
curl http://localhost:8006/api/ai/job/status?job_id=job_123

# List all jobs
curl http://localhost:8006/api/ai/jobs
```

### Resource API
```bash
# Allocate resources via API
curl -X POST http://localhost:8006/api/resource/allocate \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"ai-agent","gpu":1,"memory":8192,"duration":3600}'

# Get resource utilization
curl http://localhost:8006/api/resource/utilization?type=gpu&period=1h
```

### Marketplace API
```bash
# List services
curl http://localhost:8006/api/market/services

# Create service
curl -X POST http://localhost:8006/api/market/service/create \
  -H "Content-Type: application/json" \
  -d '{"name":"AI Service","type":"inference","price":50,"wallet":"genesis-ops"}'

# Bid on service
curl -X POST http://localhost:8006/api/market/order/bid \
  -H "Content-Type: application/json" \
  -d '{"service_id":"service_123","amount":60,"wallet":"genesis-ops"}'
```

### GPU Provider API
```bash
# Register provider
curl -X POST http://localhost:8006/api/gpu/provider/register \
  -H "Content-Type: application/json" \
  -d '{"name":"GPU Provider","gpu_model":"RTX4090","gpu_count":4,"price":0.10}'

# Get provider status
curl http://localhost:8006/api/gpu/provider/status?provider_id=provider_123

# List providers
curl http://localhost:8006/api/gpu/providers
```

## AI Security and Compliance

### Secure AI Operations
```bash
# Secure job submission
./aitbc-cli ai job submit --wallet genesis-ops --type inference --prompt "Generate image" --payment 100 --encrypt

# Verify job integrity
./aitbc-cli ai job verify --job-id "job_123"

# AI job audit
./aitbc-cli ai job audit --job-id "job_123"
```

### Compliance Features
- **Data Privacy**: Encrypt sensitive AI data
- **Job Verification**: Cryptographic job verification
- **Audit Trail**: Complete job execution history
- **Access Control**: Role-based AI service access

## Troubleshooting AI Operations

### Common Issues and Solutions

#### Job Submission Failures
```bash
# Check wallet balance
./aitbc-cli wallet balance --name genesis-ops

# Verify network connectivity
./aitbc-cli network status

# Check AI service availability
./aitbc-cli ai service status

# Verify job parameters
./aitbc-cli ai job validate --type inference --prompt "test" --payment 50
```

#### GPU Allocation Issues
```bash
# Check GPU availability
nvidia-smi
./aitbc-cli resource available --type gpu

# Verify GPU provider status
./aitbc-cli gpu provider status --provider-id "provider_123"

# Check resource locks
./aitbc-cli resource locks --list

# Release stuck resources
./aitbc-cli resource release --allocation-id "alloc_123" --force
```

#### Performance Issues
```bash
# Check system resources
htop
iostat -x 1

# Monitor GPU usage
nvidia-smi dmon
./aitbc-cli resource utilization --type gpu --live

# Check network latency
ping aitbc1
./aitbc-cli network latency --target aitbc1

# Analyze job logs
./aitbc-cli ai job logs --job-id "job_123" --tail 100
```

#### Payment Issues
```bash
# Check transaction status
./aitbc-cli blockchain tx-status --tx-hash "0x123...abc"

# Verify wallet state
./aitbc-cli wallet info --name genesis-ops

# Check payment queue
./aitbc-cli ai payment queue --wallet genesis-ops

# Retry failed payment
./aitbc-cli ai payment retry --job-id "job_123"
```

### Debug Commands
```bash
# Check AI service status
./aitbc-cli ai service status

# Debug resource allocation
./aitbc-cli resource debug --agent-id "ai-agent"

# Check wallet balance
./aitbc-cli wallet balance --name genesis-ops

# Verify network connectivity
ping aitbc1
curl -s http://localhost:8006/health
```

## Real-World Workflows

### Workflow 1: Batch Image Generation
```bash
# 1. Allocate GPU resources
./aitbc-cli resource allocate --agent-id batch-gen --gpu 2 --memory 16384 --duration 7200

# 2. Submit batch job
./aitbc-cli ai job submit --wallet genesis-ops --type inference --batch-file "prompts.json" --parallel 4 --payment 400

# 3. Monitor progress
./aitbc-cli ai job status --job-id "job_123" --watch

# 4. Verify results
./aitbc-cli ai job verify --job-id "job_123" --check-integrity

# 5. Release resources
./aitbc-cli resource release --agent-id batch-gen
```

### Workflow 2: Distributed Model Training
```bash
# 1. Register GPU providers on multiple nodes
ssh aitbc1 './aitbc-cli gpu provider register --name "GPU-1" --gpu-count 2 --price 0.10'
ssh aitbc2 './aitbc-cli gpu provider register --name "GPU-2" --gpu-count 4 --price 0.08'

# 2. Submit distributed training job
./aitbc-cli ai job submit --wallet genesis-ops --type training --model "distributed-model" \
  --nodes "aitbc,aitbc1,aitbc2" --dataset "training.json" --payment 1000

# 3. Monitor training across nodes
./aitbc-cli ai job status --job-id "job_456" --multi-node

# 4. Collect training metrics
./aitbc-cli ai metrics training --job-id "job_456" --nodes "aitbc,aitbc1,aitbc2"
```

### Workflow 3: Ollama GPU Provider Service
```bash
# 1. Set up Ollama on node
ssh gitea-runner 'ollama serve &'
ssh gitea-runner 'ollama pull llama2'
ssh gitea-runner 'ollama pull mistral'

# 2. Register as Ollama provider
./aitbc-cli gpu provider register --name "Ollama-Provider" --type ollama \
  --models "llama2,mistral" --gpu-count 1 --price 0.05

# 3. Submit Ollama jobs
./aitbc-cli ai job submit --wallet genesis-ops --type ollama --provider "Ollama-Provider" \
  --model "llama2" --prompt "Analyze text" --payment 50

# 4. Monitor provider earnings
./aitbc-cli gpu provider earnings --provider-id "provider_789" --period "7d"
```

### Workflow 4: AI Service Marketplace
```bash
# 1. Create AI service
./aitbc-cli market service create --name "Premium Image Gen" --type ai-inference \
  --price 100 --wallet genesis-ops --description "High-quality image generation"

# 2. Register as provider
./aitbc-cli market provider register --name "AI-Service-Pro" --wallet genesis-ops

# 3. Customer bids on service
./aitbc-cli market order bid --service-id "service_123" --amount 110 --wallet customer-wallet

# 4. Execute service
./aitbc-cli market order execute --service-id "service_123" --job-data "prompt:Generate landscape"

# 5. Verify completion
./aitbc-cli market order status --order-id "order_456"
```

### Workflow 5: OpenClaw Multi-Agent Pipeline
```bash
# 1. Initialize agents
openclaw agent init --name Data-Preprocessor --type data-worker
openclaw agent init --name AI-Inference --type ai-worker
openclaw agent init --name Result-Postprocessor --type data-worker

# 2. Configure agents
openclaw agent configure --name AI-Inference --ai-model "llama2" --gpu-requirement 1

# 3. Execute pipeline
openclaw execute --agent CoordinatorAgent --task run_pipeline \
  --workflow "Data-Preprocessor->AI-Inference->Result-Postprocessor" \
  --input "data.json" --output "results.json"

# 4. Monitor pipeline
openclaw monitor --pipeline pipeline_123 --realtime
```

## Best Practices

### Resource Management
- Allocate appropriate resources for job type
- Monitor resource utilization regularly
- Release resources when jobs complete
- Use priority settings for important jobs

### Cost Optimization
- Estimate costs before submitting jobs
- Use appropriate job parameters
- Monitor AI spending regularly
- Optimize resource allocation

### Security
- Use encryption for sensitive data
- Verify job integrity regularly
- Monitor audit logs
- Implement access controls
- Use blockchain verification for critical jobs
- Keep AI models and data isolated
- Regular security audits of AI services
- Implement rate limiting for API endpoints

### Performance
- Use appropriate job types
- Optimize resource allocation
- Monitor performance metrics
- Use multi-node coordination for large jobs
