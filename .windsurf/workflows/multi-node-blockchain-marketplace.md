---
description: Marketplace scenario testing, GPU provider testing, transaction tracking, and verification procedures
title: Multi-Node Blockchain Setup - Marketplace Module
version: 1.0
---

# Multi-Node Blockchain Setup - Marketplace Module

This module covers marketplace scenario testing, GPU provider testing, transaction tracking, verification procedures, and performance testing for the AITBC blockchain marketplace.

## Prerequisites

- Complete [Core Setup Module](multi-node-blockchain-setup-core.md)
- Complete [Operations Module](multi-node-blockchain-operations.md)
- Complete [Advanced Features Module](multi-node-blockchain-advanced.md)
- Complete [Production Module](multi-node-blockchain-production.md)
- Stable blockchain network with AI operations enabled
- Marketplace services configured

## Marketplace Setup

### Initialize Marketplace Services

```bash
cd /opt/aitbc && source venv/bin/activate

# Create marketplace service provider wallet
./aitbc-cli wallet create marketplace-provider 123

# Fund marketplace provider wallet
./aitbc-cli wallet send genesis-ops $(./aitbc-cli wallet list | grep "marketplace-provider:" | cut -d" " -f2) 10000 123

# Create AI service provider wallet
./aitbc-cli wallet create ai-service-provider 123

# Fund AI service provider wallet
./aitbc-cli wallet send genesis-ops $(./aitbc-cli wallet list | grep "ai-service-provider:" | cut -d" " -f2) 5000 123

# Create GPU provider wallet
./aitbc-cli wallet create gpu-provider 123

# Fund GPU provider wallet
./aitbc-cli wallet send genesis-ops $(./aitbc-cli wallet list | grep "gpu-provider:" | cut -d" " -f2) 5000 123
```

### Create Marketplace Services

```bash
# Create AI inference service
./aitbc-cli market create \
    --type ai-inference \
    --price 100 \
    --wallet marketplace-provider \
    --description "High-quality image generation using advanced AI models"

# Create AI training service
./aitbc-cli market create \
    --type ai-training \
    --price 500 \
    --wallet ai-service-provider \
    --description "Custom AI model training on your datasets"

# Create GPU rental service
./aitbc-cli market create \
    --type gpu-rental \
    --price 50 \
    --wallet gpu-provider \
    --description "High-performance GPU rental for AI workloads"

# Create data processing service
./aitbc-cli market create \
    --type data-processing \
    --price 25 \
    --wallet marketplace-provider \
    --description "Automated data analysis and processing"
```

### Verify Marketplace Services

```bash
# List all marketplace services
./aitbc-cli market list

# Check service details
./aitbc-cli market search --query "AI"

# Verify provider listings
./aitbc-cli market my-listings --wallet marketplace-provider
./aitbc-cli market my-listings --wallet ai-service-provider
./aitbc-cli market my-listings --wallet gpu-provider
```

## Scenario Testing

### Scenario 1: AI Image Generation Workflow

```bash
# Customer creates wallet and funds it
./aitbc-cli wallet create customer-1 123
./aitbc-cli wallet send genesis-ops $(./aitbc-cli wallet list | grep "customer-1:" | cut -d" " -f2) 1000 123

# Customer browses marketplace
./aitbc-cli market search --query "image generation"

# Customer bids on AI image generation service
SERVICE_ID=$(./aitbc-cli market search --query "AI Image Generation" | grep "service_id" | head -1 | cut -d" " -f2)
./aitbc-cli market bid --service-id $SERVICE_ID --amount 120 --wallet customer-1

# Service provider accepts bid
./aitbc-cli market accept-bid --service-id $SERVICE_ID --bid-id "bid_123" --wallet marketplace-provider

# Customer submits AI job
./aitbc-cli ai submit --wallet customer-1 --type inference \
    --prompt "Generate a futuristic cityscape with flying cars" \
    --payment 120 --service-id $SERVICE_ID

# Monitor job completion
./aitbc-cli ai status --job-id "ai_job_123"

# Customer receives results
./aitbc-cli ai results --job-id "ai_job_123"

# Verify transaction completed
./aitbc-cli wallet balance customer-1
./aitbc-cli wallet balance marketplace-provider
```

### Scenario 2: GPU Rental + AI Training

```bash
# Researcher creates wallet and funds it
./aitbc-cli wallet create researcher-1 123
./aitbc-cli wallet send genesis-ops $(./aitbc-cli wallet list | grep "researcher-1:" | cut -d" " -f2) 2000 123

# Researcher rents GPU for training
GPU_SERVICE_ID=$(./aitbc-cli market search --query "GPU" | grep "service_id" | head -1 | cut -d" " -f2)
./aitbc-cli market bid --service-id $GPU_SERVICE_ID --amount 60 --wallet researcher-1

# GPU provider accepts and allocates GPU
./aitbc-cli market accept-bid --service-id $GPU_SERVICE_ID --bid-id "bid_456" --wallet gpu-provider

# Researcher submits training job with allocated GPU
./aitbc-cli ai submit --wallet researcher-1 --type training \
    --model "custom-classifier" --dataset "/data/training_data.csv" \
    --payment 500 --gpu-allocated 1 --memory 8192

# Monitor training progress
./aitbc-cli ai status --job-id "ai_job_456"

# Verify GPU utilization
./aitbc-cli resource status --agent-id "gpu-worker-1"

# Training completes and researcher gets model
./aitbc-cli ai results --job-id "ai_job_456"
```

### Scenario 3: Multi-Service Pipeline

```bash
# Enterprise creates wallet and funds it
./aitbc-cli wallet create enterprise-1 123
./aitbc-cli wallet send genesis-ops $(./aitbc-cli wallet list | grep "enterprise-1:" | cut -d" " -f2) 5000 123

# Enterprise creates data processing pipeline
DATA_SERVICE_ID=$(./aitbc-cli market search --query "data processing" | grep "service_id" | head -1 | cut -d" " -f2)
./aitbc-cli market bid --service-id $DATA_SERVICE_ID --amount 30 --wallet enterprise-1

# Data provider processes raw data
./aitbc-cli market accept-bid --service-id $DATA_SERVICE_ID --bid-id "bid_789" --wallet marketplace-provider

# Enterprise submits AI analysis on processed data
./aitbc-cli ai submit --wallet enterprise-1 --type inference \
    --prompt "Analyze processed data for trends and patterns" \
    --payment 200 --input-data "/data/processed_data.csv"

# Results are delivered and verified
./aitbc-cli ai results --job-id "ai_job_789"

# Enterprise pays for services
./aitbc-cli market settle-payment --service-id $DATA_SERVICE_ID --amount 30 --wallet enterprise-1
```

## GPU Provider Testing

### GPU Resource Allocation Testing

```bash
# Test GPU allocation and deallocation
./aitbc-cli resource allocate --agent-id "gpu-worker-1" --memory 8192 --duration 3600

# Verify GPU allocation
./aitbc-cli resource status --agent-id "gpu-worker-1"

# Test GPU utilization monitoring
./aitbc-cli resource utilization --type gpu --period "1h"

# Test GPU deallocation
./aitbc-cli resource deallocate --agent-id "gpu-worker-1"

# Test concurrent GPU allocations
for i in {1..5}; do
    ./aitbc-cli resource allocate --agent-id "gpu-worker-$i" --memory 8192 --duration 1800 &
done
wait

# Monitor concurrent GPU usage
./aitbc-cli resource status
```

### GPU Performance Testing

```bash
# Test GPU performance with different workloads
./aitbc-cli ai submit --wallet gpu-provider --type inference \
    --prompt "Generate high-resolution image" --payment 100 \
    --gpu-allocated 1 --resolution "1024x1024"

./aitbc-cli ai submit --wallet gpu-provider --type training \
    --model "large-model" --dataset "/data/large_dataset.csv" --payment 500 \
    --gpu-allocated 1 --batch-size 64

# Monitor GPU performance metrics
./aitbc-cli ai metrics --agent-id "gpu-worker-1" --period "1h"

# Test GPU memory management
./aitbc-cli resource test --type gpu --memory-stress --duration 300
```

### GPU Provider Economics

```bash
# Test GPU provider revenue tracking
./aitbc-cli market revenue --wallet gpu-provider --period "24h"

# Test GPU utilization optimization
./aitbc-cli market optimize --wallet gpu-provider --metric "utilization"

# Test GPU pricing strategy
./aitbc-cli market pricing --service-id $GPU_SERVICE_ID --strategy "dynamic"
```

## Transaction Tracking

### Transaction Monitoring

```bash
# Monitor all marketplace transactions
./aitbc-cli market transactions --period "1h"

# Track specific service transactions
./aitbc-cli market transactions --service-id $SERVICE_ID

# Monitor customer transaction history
./aitbc-cli wallet transactions customer-1 --limit 50

# Track provider revenue
./aitbc-cli market revenue --wallet marketplace-provider --period "24h"
```

### Transaction Verification

```bash
# Verify transaction integrity
./aitbc-cli wallet transaction verify --tx-id "tx_123"

# Check transaction confirmation status
./aitbc-cli wallet transaction status --tx-id "tx_123"

# Verify marketplace settlement
./aitbc-cli market verify-settlement --service-id $SERVICE_ID

# Audit transaction trail
./aitbc-cli market audit --period "24h"
```

### Cross-Node Transaction Tracking

```bash
# Monitor transactions across both nodes
./aitbc-cli wallet transactions --cross-node --period "1h"

# Verify transaction propagation
./aitbc-cli wallet transaction verify-propagation --tx-id "tx_123"

# Track cross-node marketplace activity
./aitbc-cli market cross-node-stats --period "24h"
```

## Verification Procedures

### Service Quality Verification

```bash
# Verify service provider performance
./aitbc-cli market verify-provider --wallet ai-service-provider

# Check service quality metrics
./aitbc-cli market quality-metrics --service-id $SERVICE_ID

# Verify customer satisfaction
./aitbc-cli market satisfaction --wallet customer-1 --period "7d"
```

### Compliance Verification

```bash
# Verify marketplace compliance
./aitbc-cli market compliance-check --period "24h"

# Check regulatory compliance
./aitbc-cli market regulatory-audit --period "30d"

# Verify data privacy compliance
./aitbc-cli market privacy-audit --service-id $SERVICE_ID
```

### Financial Verification

```bash
# Verify financial transactions
./aitbc-cli market financial-audit --period "24h"

# Check payment processing
./aitbc-cli market payment-verify --period "1h"

# Reconcile marketplace accounts
./aitbc-cli market reconcile --period "24h"
```

## Performance Testing

### Load Testing

```bash
# Simulate high transaction volume
for i in {1..100}; do
    ./aitbc-cli market bid --service-id $SERVICE_ID --amount 100 --wallet test-wallet-$i &
done
wait

# Monitor system performance under load
./aitbc-cli market performance-metrics --period "5m"

# Test marketplace scalability
./aitbc-cli market stress-test --transactions 1000 --concurrent 50
```

### Latency Testing

```bash
# Test transaction processing latency
time ./aitbc-cli market bid --service-id $SERVICE_ID --amount 100 --wallet test-wallet

# Test AI job submission latency
time ./aitbc-cli ai submit --wallet test-wallet --type inference --prompt "test" --payment 50

# Monitor overall system latency
./aitbc-cli market latency-metrics --period "1h"
```

### Throughput Testing

```bash
# Test marketplace throughput
./aitbc-cli market throughput-test --duration 300 --transactions-per-second 10

# Test AI job throughput
./aitbc-cli market ai-throughput-test --duration 300 --jobs-per-minute 5

# Monitor system capacity
./aitbc-cli market capacity-metrics --period "24h"
```

## Troubleshooting Marketplace Issues

### Common Marketplace Problems

| Problem | Symptoms | Diagnosis | Fix |
|---|---|---|---|
| Service not found | Search returns no results | Check service listing status | Verify service is active and listed |
| Bid acceptance fails | Provider can't accept bids | Check provider wallet balance | Ensure provider has sufficient funds |
| Payment settlement fails | Transaction stuck | Check blockchain status | Verify blockchain is healthy |
| GPU allocation fails | Can't allocate GPU resources | Check GPU availability | Verify GPU resources are available |
| AI job submission fails | Job not processing | Check AI service status | Verify AI service is operational |

### Advanced Troubleshooting

```bash
# Diagnose marketplace connectivity
./aitbc-cli market connectivity-test

# Check marketplace service health
./aitbc-cli market health-check

# Verify marketplace data integrity
./aitbc-cli market integrity-check

# Debug marketplace transactions
./aitbc-cli market debug --transaction-id "tx_123"
```

## Automation Scripts

### Automated Marketplace Testing

```bash
#!/bin/bash
# automated_marketplace_test.sh

echo "Starting automated marketplace testing..."

# Create test wallets
./aitbc-cli wallet create test-customer 123
./aitbc-cli wallet create test-provider 123

# Fund test wallets
CUSTOMER_ADDR=$(./aitbc-cli wallet list | grep "test-customer:" | cut -d" " -f2)
PROVIDER_ADDR=$(./aitbc-cli wallet list | grep "test-provider:" | cut -d" " -f2)

./aitbc-cli wallet send genesis-ops $CUSTOMER_ADDR 1000 123
./aitbc-cli wallet send genesis-ops $PROVIDER_ADDR 1000 123

# Create test service
./aitbc-cli market create \
    --type ai-inference \
    --price 50 \
    --wallet test-provider \
    --description "Test AI Service"

# Test complete workflow
SERVICE_ID=$(./aitbc-cli market list | grep "Test AI Service" | grep "service_id" | cut -d" " -f2)

    ./aitbc-cli market bid --service-id $SERVICE_ID --amount 60 --wallet test-customer
    ./aitbc-cli market accept-bid --service-id $SERVICE_ID --bid-id "test_bid" --wallet test-provider

    ./aitbc-cli ai submit --wallet test-customer --type inference --prompt "test image" --payment 60

# Verify results
echo "Test completed successfully!"
```

### Performance Monitoring Script

```bash
#!/bin/bash
# marketplace_performance_monitor.sh

while true; do
    TIMESTAMP=$(date +%Y-%m-%d_%H:%M:%S)
    
    # Collect metrics
    ACTIVE_SERVICES=$(./aitbc-cli market list | grep -c "service_id")
    PENDING_BIDS=$(./aitbc-cli market pending-bids | grep -c "bid_id")
    TOTAL_VOLUME=$(./aitbc-cli market volume --period "1h")
    
    # Log metrics
    echo "$TIMESTAMP,services:$ACTIVE_SERVICES,bids:$PENDING_BIDS,volume:$TOTAL_VOLUME" >> /var/log/aitbc/marketplace_performance.log
    
    sleep 60
done
```

## Dependencies

This marketplace module depends on:
- **[Core Setup Module](multi-node-blockchain-setup-core.md)** - Basic node setup
- **[Operations Module](multi-node-blockchain-operations.md)** - Daily operations
- **[Advanced Features Module](multi-node-blockchain-advanced.md)** - Advanced features
- **[Production Module](multi-node-blockchain-production.md)** - Production deployment

## Next Steps

After mastering marketplace operations, proceed to:
- **[Reference Module](multi-node-blockchain-reference.md)** - Configuration and verification reference

## Best Practices

- Always test marketplace operations with small amounts first
- Monitor GPU resource utilization during AI jobs
- Verify transaction confirmations before considering operations complete
- Use proper wallet management for different roles (customers, providers)
- Implement proper logging for marketplace transactions
- Regularly audit marketplace compliance and financial integrity
