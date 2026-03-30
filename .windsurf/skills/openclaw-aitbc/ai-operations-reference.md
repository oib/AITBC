# AITBC AI Operations Reference

## AI Job Types and Parameters

### Inference Jobs
```bash
# Basic image generation
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Generate image of futuristic city" --payment 100

# Text analysis
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Analyze sentiment of this text" --payment 50

# Code generation
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Generate Python function for data processing" --payment 75
```

### Training Jobs
```bash
# Model training
./aitbc-cli ai-submit --wallet genesis-ops --type training --model "custom-model" --dataset "training_data.json" --payment 500

# Fine-tuning
./aitbc-cli ai-submit --wallet genesis-ops --type training --model "gpt-3.5-turbo" --dataset "fine_tune_data.json" --payment 300
```

### Multimodal Jobs
```bash
# Image analysis
./aitbc-cli ai-submit --wallet genesis-ops --type multimodal --prompt "Analyze this image" --image-path "/path/to/image.jpg" --payment 200

# Audio processing
./aitbc-cli ai-submit --wallet genesis-ops --type multimodal --prompt "Transcribe audio" --audio-path "/path/to/audio.wav" --payment 150
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

### Creating AI Services
```bash
# Image generation service
./aitbc-cli marketplace --action create --name "AI Image Generation" --type ai-inference --price 50 --wallet genesis-ops --description "Generate high-quality images from text prompts"

# Model training service
./aitbc-cli marketplace --action create --name "Custom Model Training" --type ai-training --price 200 --wallet genesis-ops --description "Train custom models on your data"

# Data analysis service
./aitbc-cli marketplace --action create --name "AI Data Analysis" --type ai-processing --price 75 --wallet genesis-ops --description "Analyze and process datasets with AI"
```

### Marketplace Interaction
```bash
# List available services
./aitbc-cli marketplace --action list

# Search for specific services
./aitbc-cli marketplace --action search --query "image generation"

# Bid on service
./aitbc-cli marketplace --action bid --service-id "service_123" --amount 60 --wallet genesis-ops

# Execute purchased service
./aitbc-cli marketplace --action execute --service-id "service_123" --job-data "prompt:Generate landscape image"
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

## Cross-Node AI Coordination

### Multi-Node Job Submission
```bash
# Submit to specific node
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Generate image" --target-node "aitbc1" --payment 100

# Distribute training across nodes
./aitbc-cli ai-submit --wallet genesis-ops --type training --model "distributed-model" --nodes "aitbc,aitbc1" --payment 500
```

### Cross-Node Resource Management
```bash
# Allocate resources on follower node
ssh aitbc1 'cd /opt/aitbc && source venv/bin/activate && ./aitbc-cli resource allocate --agent-id ai-agent --gpu 1 --memory 8192 --duration 3600'

# Monitor multi-node AI status
./aitbc-cli ai-status --multi-node
```

## AI Economics and Pricing

### Job Cost Estimation
```bash
# Estimate inference job cost
./aitbc-cli ai-estimate --type inference --prompt-length 100 --resolution 512

# Estimate training job cost
./aitbc-cli ai-estimate --type training --model-size "1B" --dataset-size "1GB" --epochs 10
```

### Payment and Earnings
```bash
# Pay for AI job
./aitbc-cli ai-pay --job-id "job_123" --wallet genesis-ops --amount 100

# Check AI earnings
./aitbc-cli ai-earnings --wallet genesis-ops --period "7d"
```

## AI Monitoring and Analytics

### Job Monitoring
```bash
# Monitor specific job
./aitbc-cli ai-status --job-id "job_123"

# Monitor all jobs
./aitbc-cli ai-status --all

# Job history
./aitbc-cli ai-history --wallet genesis-ops --limit 10
```

### Performance Metrics
```bash
# AI performance metrics
./aitbc-cli ai-metrics --agent-id "ai-inference-worker" --period "1h"

# Resource utilization
./aitbc-cli resource utilization --type gpu --period "1h"

# Job throughput
./aitbc-cli ai-throughput --nodes "aitbc,aitbc1" --period "24h"
```

## AI Security and Compliance

### Secure AI Operations
```bash
# Secure job submission
./aitbc-cli ai-submit --wallet genesis-ops --type inference --prompt "Generate image" --payment 100 --encrypt

# Verify job integrity
./aitbc-cli ai-verify --job-id "job_123"

# AI job audit
./aitbc-cli ai-audit --job-id "job_123"
```

### Compliance Features
- **Data Privacy**: Encrypt sensitive AI data
- **Job Verification**: Cryptographic job verification
- **Audit Trail**: Complete job execution history
- **Access Control**: Role-based AI service access

## Troubleshooting AI Operations

### Common Issues
1. **Job Not Starting**: Check resource allocation and wallet balance
2. **GPU Allocation Failed**: Verify GPU availability and driver installation
3. **High Latency**: Check network connectivity and resource utilization
4. **Payment Failed**: Verify wallet has sufficient AIT balance

### Debug Commands
```bash
# Check AI service status
./aitbc-cli ai-service status

# Debug resource allocation
./aitbc-cli resource debug --agent-id "ai-agent"

# Check wallet balance
./aitbc-cli balance --name genesis-ops

# Verify network connectivity
ping aitbc1
curl -s http://localhost:8006/health
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

### Performance
- Use appropriate job types
- Optimize resource allocation
- Monitor performance metrics
- Use multi-node coordination for large jobs
