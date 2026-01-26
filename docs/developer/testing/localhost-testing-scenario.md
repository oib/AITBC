# AITBC Testing Scenario: Customer-Service Provider Interaction

## Overview

This document outlines a comprehensive testing scenario for customers and service providers interacting on the AITBC platform. This scenario enables end-to-end testing of the complete marketplace workflow using the publicly accessible deployment at https://aitbc.bubuit.net/.

## Integration Tests

### Test Suite Status (Updated 2026-01-26)

The integration test suite has been updated to use real implemented features:

#### ✅ Passing Tests (6)
1. **End-to-End Job Execution** - Tests complete job workflow
2. **Multi-Tenant Isolation** - Verifies tenant data separation
3. **Block Propagation** - Tests P2P network block sync
4. **Transaction Propagation** - Tests P2P transaction sync
5. **Marketplace Integration** - Connects to live marketplace
6. **Security Integration** - Uses real ZK proof features

#### ⏸️ Skipped Tests (1)
1. **Wallet Payment Flow** - Awaiting wallet-coordinator integration

#### Running Tests
```bash
# Run all integration tests
python -m pytest tests/integration/test_full_workflow.py -v

# Run specific test class
python -m pytest tests/integration/test_full_workflow.py::TestSecurityIntegration -v

# Run with real client (not mocks)
export USE_REAL_CLIENT=1
python -m pytest tests/integration/ -v
```

#### Test Features
- Tests work with both real client and mock fallback
- Security tests use actual ZK proof requirements
- Marketplace tests connect to https://aitbc.bubuit.net/marketplace
- All tests pass in CLI and Windsorf environments

## Prerequisites

### System Requirements
- Modern web browser (Chrome, Firefox, Safari, or Edge)
- Internet connection to access https://aitbc.bubuit.net/
- Terminal/command line access (for API testing)
- Python 3.11+ and virtual environment (for local testing)
- Ollama installed and running (for GPU miner testing)
- systemd (for running miner as service)

### Local Development Setup
For localhost testing, ensure you have:
- AITBC repository cloned to `/home/oib/windsurf/aitbc`
- Virtual environment created: `python3 -m venv .venv`
- Dependencies installed: `source .venv/bin/python -m pip install -e .`
- Bash CLI wrapper: `/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh`

### Services Running
Ensure all AITBC services are accessible via:
- Coordinator API (http://127.0.0.1:18000/)
- Blockchain Node (http://127.0.0.1:19000/)
- Wallet Daemon (http://127.0.0.1:20000/)
- Marketplace UI (http://127.0.0.1:21000/)
- Explorer Web (http://127.0.0.1:22000/)
- Trade Exchange (http://127.0.0.1:23000/)
- Miner Dashboard (http://127.0.0.1:24000/)

## Scenario: GPU Computing Service Marketplace

### Actors
1. **Customer** - Wants to purchase GPU computing power
2. **Service Provider** - Offers GPU computing services
3. **Platform** - AITBC marketplace facilitating the transaction

## Testing Workflow

### Phase 1: Service Provider Setup

#### 1.1 Register as a Service Provider
```bash
# Navigate to marketplace
http://127.0.0.1:21000/

# Click "Become a Provider"
# Fill in provider details:
- Provider Name: "GPUCompute Pro"
- Service Type: "GPU Computing"
- Description: "High-performance GPU computing for AI/ML workloads"
- Pricing Model: "Per Hour"
- Rate: "100 AITBC tokens/hour"
```

#### 1.2 Configure Service Offering
```python
# Example service configuration
service_config = {
    "service_id": "gpu-compute-001",
    "name": "GPU Computing Service",
    "type": "gpu_compute",
    "specs": {
        "gpu_type": "NVIDIA RTX 4090",
        "memory": "24GB",
        "cuda_cores": 16384,
        "supported_frameworks": ["PyTorch", "TensorFlow", "JAX"]
    },
    "pricing": {
        "rate_per_hour": 100,
        "currency": "AITBC"
    },
    "availability": {
        "start_time": "2024-01-01T00:00:00Z",
        "end_time": "2024-12-31T23:59:59Z",
        "timezone": "UTC"
    }
}
```

#### 1.3 Register Service with Coordinator
```bash
# Using bash CLI wrapper
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh admin-miners

# Or POST to coordinator API directly
curl -X POST http://127.0.0.1:18000/v1/services/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: provider-api-key" \
  -d @service_config.json
```

### Phase 2: Customer Discovery and Selection

#### 2.1 Browse Available Services
```bash
# Customer navigates to marketplace
http://127.0.0.1:21000/

# Or use CLI to check coordinator status
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh health

# Filter by:
- Service Category: "GPU Computing"
- Price Range: "50-200 AITBC/hour"
- Availability: "Available Now"
```

#### 2.2 View Service Details
```bash
# Using bash CLI wrapper
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh browser --receipt-limit 5

# Or GET service details via API
service_id="gpu-compute-001"
curl -X GET "http://127.0.0.1:18000/v1/services/${service_id}" \
  -H "X-API-Key: customer-api-key"
```

#### 2.3 Verify Provider Reputation
```bash
# Check provider ratings and reviews
curl -X GET http://127.0.0.1:18000/v1/providers/gpu-compute-pro/reputation

# View transaction history
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh receipts --limit 10
```

### Phase 3: Service Purchase and Execution

#### 3.1 Purchase Service Credits
```bash
# Navigate to Trade Exchange
http://127.0.0.1:23000/

# Purchase AITBC tokens:
- Amount: 1000 AITBC
- Payment Method: Bitcoin (testnet)
- Exchange Rate: 1 BTC = 100,000 AITBC

# Or check balance via CLI
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh admin-stats
```

#### 3.2 Create Service Job
```bash
# Using bash CLI wrapper (recommended)
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh submit inference \
  --prompt "Train a ResNet model on ImageNet" \
  --model llama3.2:latest \
  --ttl 900

# Example output:
# ✅ Job submitted successfully!
#    Job ID: 707c75d0910e49e2965196bce0127ba1

# Track job status
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh status 707c75d0910e49e2965196bce0127ba1
```

Or using Python/curl:
```python
# Create job request
job_request = {
    "service_id": "gpu-compute-001",
    "customer_id": "customer-123",
    "requirements": {
        "task_type": "model_training",
        "framework": "PyTorch",
        "dataset_size": "10GB",
        "estimated_duration": "2 hours"
    },
    "budget": {
        "max_cost": 250,
        "currency": "AITBC"
    }
}

# Submit job
response = requests.post(
    "http://127.0.0.1:18000/v1/jobs/create",
    json=job_request,
    headers={"X-API-Key": "customer-api-key"}
)
job_id = response.json()["job_id"]
```

#### 3.3 Monitor Job Progress
```bash
# Using bash CLI wrapper
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh status <job_id>

# Or real-time job monitoring via API
curl -X GET http://127.0.0.1:18000/v1/jobs/{job_id}/status

# WebSocket for live updates
ws://127.0.0.1:18000/v1/jobs/{job_id}/stream

# View blockchain transactions
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh browser --block-limit 5
```

#### 3.4 Receive Results
```bash
# Using bash CLI wrapper to check receipts
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh receipts --job-id <job_id>

# Or download completed job results via API
response=$(curl -s -X GET "http://127.0.0.1:18000/v1/jobs/{job_id}/results" \
  -H "X-API-Key: customer-api-key")

echo "$response" | jq .

# Verify results with receipt
receipt=$(echo "$response" | jq -r .receipt)
# Verify receipt signature with customer public key
```

Or using Python:
```python
import requests

response = requests.get(
    f"http://127.0.0.1:18000/v1/jobs/{job_id}/results",
    headers={"X-API-Key": "customer-api-key"}
)

# Verify results with receipt
receipt = response.json()["receipt"]
verified = verify_job_receipt(receipt, customer_public_key)
```

### Phase 4: Payment and Settlement

#### 4.1 Automatic Payment Processing
```bash
# Payment automatically processed upon job completion
# Check transaction on blockchain
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh browser --receipt-limit 1

# Or via RPC API
curl -X POST http://127.0.0.1:19000/api/v1/transaction/get \
  -d '{"tx_hash": "0x..."}'
```

#### 4.2 Provider Receives Payment
```bash
# Provider checks wallet balance via CLI
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh admin-stats

# Or via wallet daemon API
curl -X GET http://127.0.0.1:20000/api/v1/wallet/balance \
  -H "X-API-Key: provider-api-key"

# Example output: {"balance": 100.0, "currency": "AITBC"}
```

Or using Python:
```python
# Provider checks wallet balance
balance = wallet_daemon.get_balance(provider_address)
print(f"Received payment: {balance} AITBC")
```

#### 4.3 Rate and Review
```bash
# Customer rates service via API
POST http://127.0.0.1:18000/v1/services/{service_id}/rate
{
    "rating": 5,
    "review": "Excellent service! Fast execution and great results.",
    "customer_id": "customer-123"
}

# Or check provider stats
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh admin-miners
```

## Testing Scripts

### Automated Test Runner
```python
#!/usr/bin/env python3
"""
AITBC Test Runner for Marketplace
Tests complete customer-provider workflow
"""

import asyncio
import requests
import time
from datetime import datetime

class AITBCTestTester:
    def __init__(self):
        self.base_url = "http://127.0.0.1"
        self.coordinator_url = "http://127.0.0.1:18000"
        self.marketplace_url = "http://127.0.0.1:21000"
        self.exchange_url = "http://127.0.0.1:23000"
        self.cli_path = "/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh"
        
    async def run_full_scenario(self):
        """Run complete customer-provider test scenario"""
        print("Starting AITBC Test Scenario...")
        
        # Phase 1: Setup
        await self.setup_test_environment()
        
        # Phase 2: Provider Registration
        provider_id = await self.register_provider()
        
        # Phase 3: Service Registration
        service_id = await self.register_service(provider_id)
        
        # Phase 4: Customer Setup
        customer_id = await self.setup_customer()
        
        # Phase 5: Service Discovery
        await self.test_service_discovery()
        
        # Phase 6: Job Creation and Execution
        job_id = await self.create_and_execute_job(service_id, customer_id)
        
        # Phase 7: Payment and Settlement
        await self.test_payment_flow(job_id)
        
        # Phase 8: Review and Rating
        await self.test_review_system(service_id, customer_id)
        
        print("Test scenario completed successfully!")
        
    async def setup_test_environment(self):
        """Setup test wallets and accounts"""
        print("Setting up test environment...")
        # Create test wallets for customer and provider
        # Fund test accounts with AITBC tokens
        
    async def register_provider(self):
        """Register a test service provider"""
        print("Registering service provider...")
        # Implementation here
        
    async def register_service(self, provider_id):
        """Register a test service"""
        print("Registering service...")
        # Implementation here
        
    async def setup_customer(self):
        """Setup test customer"""
        print("Setting up customer...")
        # Implementation here
        
    async def test_service_discovery(self):
        """Test service discovery functionality"""
        print("Testing service discovery...")
        # Implementation here
        
    async def create_and_execute_job(self, service_id, customer_id):
        """Create and execute a test job"""
        print("Creating and executing job...")
        # Implementation here
        return "test-job-123"
        
    async def test_payment_flow(self, job_id):
        """Test payment processing"""
        print("Testing payment flow...")
        # Implementation here
        
    async def test_review_system(self, service_id, customer_id):
        """Test review and rating system"""
        print("Testing review system...")
        # Implementation here

if __name__ == "__main__":
    tester = AITBCTestTester()
    asyncio.run(tester.run_full_scenario())
```

### Manual Testing Checklist

#### Pre-Test Setup
- [ ] All services running and accessible
- [ ] Test wallets created with initial balance
- [ ] SSL certificates configured (if using HTTPS)
- [ ] Browser cache cleared

#### Provider Workflow
- [ ] Provider registration successful
- [ ] Service configuration accepted
- [ ] Service appears in marketplace listings
- [ ] Provider dashboard shows active services

#### Customer Workflow
- [ ] Customer can browse marketplace
- [ ] Service search and filters working
- [ ] Service details display correctly
- [ ] Job submission successful
- [ ] Real-time progress updates working
- [ ] Results download successful
- [ ] Payment processed correctly

#### Post-Transaction
- [ ] Provider receives payment
- [ ] Transaction visible on explorer
- [ ] Review system working
- [ ] Reputation scores updated

## Test Data and Mock Services

### Sample GPU Service Configurations
```json
{
  "services": [
    {
      "id": "gpu-ml-training",
      "name": "ML Model Training",
      "type": "gpu_compute",
      "specs": {
        "gpu": "RTX 4090",
        "memory": "24GB",
        "software": ["PyTorch 2.0", "TensorFlow 2.13"]
      },
      "pricing": {"rate": 100, "unit": "hour", "currency": "AITBC"}
    },
    {
      "id": "gpu-rendering",
      "name": "3D Rendering Service",
      "type": "gpu_compute",
      "specs": {
        "gpu": "RTX 4090",
        "memory": "24GB",
        "software": ["Blender", "Maya", "3ds Max"]
      },
      "pricing": {"rate": 80, "unit": "hour", "currency": "AITBC"}
    }
  ]
}
```

### Mock Job Templates
```python
# Machine Learning Training Job
ml_job = {
    "type": "ml_training",
    "parameters": {
        "model": "resnet50",
        "dataset": "imagenet",
        "epochs": 10,
        "batch_size": 32
    },
    "expected_duration": "2 hours",
    "estimated_cost": 200
}

# 3D Rendering Job
render_job = {
    "type": "3d_render",
    "parameters": {
        "scene": "architectural_visualization",
        "resolution": "4K",
        "samples": 256,
        "engine": "cycles"
    },
    "expected_duration": "3 hours",
    "estimated_cost": 240
}
```

## Monitoring and Debugging

### Log Locations
```bash
# Service logs (localhost)
sudo journalctl -u coordinator-api.service -f
sudo journalctl -u aitbc-blockchain.service -f
sudo journalctl -u wallet-daemon.service -f
sudo journalctl -u aitbc-host-gpu-miner.service -f

# Application logs
tail -f /var/log/aitbc/marketplace.log
tail -f /var/log/aitbc/exchange.log

# Virtual environment logs
cd /home/oib/windsurf/aitbc
source .venv/bin/activate
```

### Debug Tools
```bash
# Check service health
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh health

curl http://127.0.0.1:18000/v1/health
curl http://127.0.0.1:19000/api/v1/health

# Monitor blockchain
curl http://127.0.0.1:19000/api/v1/block/latest

# Check active jobs
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh admin-jobs

# Verify transactions
/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh browser --tx-limit 5

# Run GPU miner manually for debugging
cd /home/oib/windsurf/aitbc
source .venv/bin/activate
python3 gpu_miner_host.py

# Or as systemd service
sudo systemctl restart aitbc-host-gpu-miner.service
sudo journalctl -u aitbc-host-gpu-miner.service -f
```

## Common Issues and Solutions

### Service Not Accessible
- Check if service is running: `sudo systemctl status [service-name]`
- Verify port is not blocked: `netstat -tlnp | grep [port]`
- Check nginx configuration: `sudo nginx -t`
- For localhost: ensure services are running in Incus container
- Check coordinator API: `/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh health`

### Transaction Failed
- Verify wallet balance: `curl http://127.0.0.1:20000/api/v1/wallet/balance`
- Check gas settings: Ensure sufficient gas for transaction
- Verify network sync: `curl http://127.0.0.1:19000/api/v1/sync/status`

### Job Not Starting
- Check service availability: `curl http://127.0.0.1:18000/v1/services/{id}`
- Verify customer balance: Check wallet has sufficient tokens
- Review job requirements: Ensure they match service capabilities
- Check if miner is running: `sudo systemctl status aitbc-host-gpu-miner.service`
- View miner logs: `sudo journalctl -u aitbc-host-gpu-miner.service -n 50`
- Submit test job: `/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh submit inference --prompt "test" --model llama3.2:latest`

## Performance Testing

### Load Testing Script
```python
"""
Simulate multiple customers and providers
"""
import asyncio
import aiohttp

async def simulate_load(num_customers=10, num_providers=5):
    """Simulate marketplace load"""
    async with aiohttp.ClientSession() as session:
        # Create providers
        providers = []
        for i in range(num_providers):
            provider = await create_provider(session, f"provider-{i}")
            providers.append(provider)
        
        # Create customers and jobs
        jobs = []
        for i in range(num_customers):
            customer = await create_customer(session, f"customer-{i}")
            job = await create_job(session, customer, random.choice(providers))
            jobs.append(job)
        
        # Monitor execution
        await monitor_jobs(session, jobs)
```

## Security Considerations for Testing

### Test Network Isolation
- Use testnet blockchain, not mainnet
- Isolate test wallets from production funds
- Use test API keys, not production keys

### Data Privacy
- Sanitize PII from test data
- Use synthetic data for testing
- Clear test data after completion

## Next Steps

1. **Production Readiness**
   - Security audit of test scenarios
   - Performance benchmarking
   - Documentation review

2. **Expansion**
   - Add more service types
   - Implement advanced matching algorithms
   - Add dispute resolution workflow

3. **Automation**
   - CI/CD integration for test scenarios
   - Automated regression testing
   - Performance monitoring alerts

## Conclusion

This localhost testing scenario provides a comprehensive environment for validating the complete AITBC marketplace workflow. It enables developers and testers to verify all aspects of the customer-provider interaction in a controlled setting before deploying to production.

## Quick Start Commands

```bash
# 1. Setup environment
cd /home/oib/windsurf/aitbc
source .venv/bin/activate

# 2. Check all services
./scripts/aitbc-cli.sh health

# 3. Start GPU miner
sudo systemctl restart aitbc-host-gpu-miner.service
sudo journalctl -u aitbc-host-gpu-miner.service -f

# 4. Submit test job
./scripts/aitbc-cli.sh submit inference --prompt "Hello AITBC" --model llama3.2:latest

# 5. Monitor progress
./scripts/aitbc-cli.sh status <job_id>
./scripts/aitbc-cli.sh browser --receipt-limit 5
```

## Host User Paths

- Repository: `/home/oib/windsurf/aitbc`
- Virtual Environment: `/home/oib/windsurf/aitbc/.venv`
- CLI Wrapper: `/home/oib/windsurf/aitbc/scripts/aitbc-cli.sh`
- GPU Miner Script: `/home/oib/windsurf/aitbc/scripts/gpu/gpu_miner_host.py`
- Systemd Unit: `/etc/systemd/system/aitbc-host-gpu-miner.service`
- Client Scripts: `/home/oib/windsurf/aitbc/home/client/`
- Test Scripts: `/home/oib/windsurf/aitbc/home/`
