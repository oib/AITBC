# Global Infrastructure

## Status
✅ Operational

## Overview
Global infrastructure management service for deploying, monitoring, and managing AITBC infrastructure across multiple regions and cloud providers.

## Architecture

### Core Components
- **Infrastructure Manager**: Manages infrastructure resources
- **Deployment Service**: Handles deployments across regions
- **Resource Scheduler**: Schedules resources optimally
- **Configuration Manager**: Manages infrastructure configuration
- **Cost Optimizer**: Optimizes infrastructure costs

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Cloud provider credentials (AWS, GCP, Azure)
- Terraform or CloudFormation templates

### Installation
```bash
cd /opt/aitbc/apps/global-infrastructure
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
CLOUD_PROVIDER=aws
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
TERRAFORM_PATH=/path/to/terraform
```

### Running the Service
```bash
.venv/bin/python main.py
```

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Configure cloud provider credentials
5. Run tests: `pytest tests/`

### Project Structure
```
global-infrastructure/
├── src/
│   ├── infrastructure_manager/ # Infrastructure management
│   ├── deployment_service/      # Deployment orchestration
│   ├── resource_scheduler/      # Resource scheduling
│   ├── config_manager/          # Configuration management
│   └── cost_optimizer/          # Cost optimization
├── terraform/                   # Terraform templates
├── tests/                       # Test suite
└── pyproject.toml               # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run deployment tests
pytest tests/test_deployment.py

# Run cost optimizer tests
pytest tests/test_cost.py
```

## API Reference

### Infrastructure Management

#### Get Infrastructure Status
```http
GET /api/v1/infrastructure/status
```

#### Provision Resource
```http
POST /api/v1/infrastructure/provision
Content-Type: application/json

{
  "resource_type": "server|database|storage",
  "region": "us-east-1",
  "specifications": {}
}
```

#### Decommission Resource
```http
DELETE /api/v1/infrastructure/resources/{resource_id}
```

### Deployment

#### Deploy Service
```http
POST /api/v1/infrastructure/deploy
Content-Type: application/json

{
  "service_name": "blockchain-node",
  "region": "us-east-1",
  "configuration": {}
}
```

#### Get Deployment Status
```http
GET /api/v1/infrastructure/deployments/{deployment_id}
```

### Resource Scheduling

#### Get Resource Utilization
```http
GET /api/v1/infrastructure/resources/utilization
```

#### Optimize Resources
```http
POST /api/v1/infrastructure/resources/optimize
Content-Type: application/json

{
  "optimization_type": "cost|performance",
  "constraints": {}
}
```

### Configuration

#### Get Configuration
```http
GET /api/v1/infrastructure/config/{region}
```

#### Update Configuration
```http
PUT /api/v1/infrastructure/config/{region}
Content-Type: application/json

{
  "parameters": {}
}
```

### Cost Management

#### Get Cost Report
```http
GET /api/v1/infrastructure/costs?period=month
```

#### Get Cost Optimization Recommendations
```http
GET /api/v1/infrastructure/costs/recommendations
```

## Configuration

### Environment Variables
- `CLOUD_PROVIDER`: Cloud provider (aws, gcp, azure)
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `AWS_REGION`: Default AWS region
- `TERRAFORM_PATH`: Path to Terraform templates
- `DEPLOYMENT_TIMEOUT`: Deployment timeout in seconds

### Infrastructure Parameters
- **Regions**: Supported cloud regions
- **Instance Types**: Available instance types
- **Storage Classes**: Storage class configurations
- **Network Configurations**: VPC and network settings

## Troubleshooting

**Deployment failed**: Check cloud provider credentials and configuration.

**Resource not provisioned**: Verify resource specifications and quotas.

**Cost optimization not working**: Review cost optimizer configuration and constraints.

**Configuration sync failed**: Check network connectivity and configuration validity.

## Security Notes

- Rotate cloud provider credentials regularly
- Use IAM roles instead of access keys when possible
- Enable encryption for all storage resources
- Implement network security groups and firewalls
- Monitor for unauthorized resource changes
- Regularly audit infrastructure configuration
