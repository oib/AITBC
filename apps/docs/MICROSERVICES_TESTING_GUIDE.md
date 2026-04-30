# AITBC Microservices Testing Guide

This guide provides comprehensive testing procedures for the AITBC microservices architecture following the Coordinator-API monolith breakup.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Database Setup](#database-setup)
- [Service Installation](#service-installation)
- [Service Startup](#service-startup)
- [Individual Service Testing](#individual-service-testing)
- [Gateway Integration Testing](#gateway-integration-testing)
- [Expected Test Outcomes](#expected-test-outcomes)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- Python 3.13+
- PostgreSQL 14+
- Poetry (for dependency management)
- Systemd (for production deployment)
- curl or httpie (for testing endpoints)

### Environment Setup

```bash
# Ensure you're in the AITBC root directory
cd /opt/aitbc

# Install dependencies
poetry install

# Verify PostgreSQL is running
sudo systemctl status postgresql
```

## Database Setup

Each microservice requires a separate database. Run the setup scripts for each service you want to test.

### GPU Service Database

```bash
sudo -u postgres psql -f apps/gpu-service/scripts/setup-database.sql
```

Expected output:
```
CREATE DATABASE
CREATE ROLE
GRANT
```

### Marketplace Service Database

```bash
sudo -u postgres psql -f apps/marketplace-service/scripts/setup-database.sql
```

### Trading Service Database

```bash
sudo -u postgres psql -f apps/trading-service/scripts/setup-database.sql
```

### Governance Service Database

```bash
sudo -u postgres psql -f apps/governance-service/scripts/setup-database.sql
```

### Verify Database Creation

```bash
sudo -u postgres psql -l
```

Expected databases:
- aitbc_gpu
- aitbc_marketplace
- aitbc_trading
- aitbc_governance

## Service Installation

Install each service using Poetry:

```bash
# GPU Service
poetry install --with gpu-service

# Marketplace Service
poetry install --with marketplace-service

# Trading Service
poetry install --with trading-service

# Governance Service
poetry install --with governance-service

# API Gateway
poetry install --with api-gateway
```

## Service Startup

### Development Mode (Manual Startup)

Start services manually in separate terminal windows:

```bash
# Terminal 1: GPU Service
cd /opt/aitbc
python -m gpu_service.main

# Terminal 2: Marketplace Service
cd /opt/aitbc
python -m marketplace_service.main

# Terminal 3: Trading Service
cd /opt/aitbc
python -m trading_service.main

# Terminal 4: Governance Service
cd /opt/aitbc
python -m governance_service.main

# Terminal 5: API Gateway
cd /opt/aitbc
python -m api_gateway.main
```

### Production Mode (Systemd)

For production deployment, use systemd services:

```bash
# Copy service files to systemd
sudo cp apps/gpu-service/gpu-service.service /etc/systemd/system/
sudo cp apps/marketplace-service/marketplace-service.service /etc/systemd/system/
sudo cp apps/trading-service/trading-service.service /etc/systemd/system/
sudo cp apps/governance-service/governance-service.service /etc/systemd/system/
sudo cp apps/api-gateway/api-gateway.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start services
sudo systemctl enable gpu-service marketplace-service trading-service governance-service api-gateway
sudo systemctl start gpu-service marketplace-service trading-service governance-service api-gateway

# Check service status
sudo systemctl status gpu-service
sudo systemctl status marketplace-service
sudo systemctl status trading-service
sudo systemctl status governance-service
sudo systemctl status api-gateway
```

## Individual Service Testing

### GPU Service Testing

#### Health Check

```bash
curl http://localhost:8101/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "gpu-service"
}
```

#### GPU Status

```bash
curl http://localhost:8101/gpu/status
```

Expected response:
```json
{
  "status": "operational",
  "service": "gpu-service",
  "message": "GPU service is running"
}
```

#### Get Consumer GPU Profiles

```bash
curl http://localhost:8101/v1/marketplace/edge-gpu/profiles
```

Expected response:
```json
[
  {
    "profile_id": "consumer_nvidia_a100",
    "name": "NVIDIA A100",
    "architecture": "NVIDIA",
    "memory_gb": 80,
    "cuda_cores": 6912,
    "tensor_cores": 432,
    "compute_capability": "8.0",
    "typical_use_cases": ["ml_training", "inference", "hpc"]
  }
]
```

### Marketplace Service Testing

#### Health Check

```bash
curl http://localhost:8102/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "marketplace-service"
}
```

#### Get Marketplace Offers

```bash
curl http://localhost:8102/v1/marketplace/offers
```

Expected response:
```json
[]
```

### Trading Service Testing

#### Health Check

```bash
curl http://localhost:8104/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "trading-service"
}
```

#### Get Trade Requests

```bash
curl http://localhost:8104/v1/trading/requests
```

Expected response:
```json
[]
```

### Governance Service Testing

#### Health Check

```bash
curl http://localhost:8105/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "governance-service"
}
```

#### Get Governance Proposals

```bash
curl http://localhost:8105/v1/governance/proposals
```

Expected response:
```json
[]
```

## Gateway Integration Testing

### Gateway Health Check

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "api-gateway"
}
```

### Gateway Service Registry

```bash
curl http://localhost:8080/services
```

Expected response:
```json
{
  "services": [
    {
      "name": "gpu",
      "url": "http://localhost:8101",
      "health_check": "/health",
      "routes": ["/gpu/*"]
    },
    {
      "name": "marketplace",
      "url": "http://localhost:8102",
      "health_check": "/health",
      "routes": ["/marketplace/*"]
    },
    {
      "name": "trading",
      "url": "http://localhost:8104",
      "health_check": "/health",
      "routes": ["/trading/*"]
    },
    {
      "name": "governance",
      "url": "http://localhost:8105",
      "health_check": "/health",
      "routes": ["/governance/*"]
    }
  ]
}
```

### Test GPU Service Through Gateway

```bash
curl http://localhost:8080/gpu/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "gpu-service"
}
```

```bash
curl http://localhost:8080/gpu/v1/marketplace/edge-gpu/profiles
```

Expected response:
```json
[
  {
    "profile_id": "consumer_nvidia_a100",
    "name": "NVIDIA A100",
    "architecture": "NVIDIA",
    "memory_gb": 80,
    "cuda_cores": 6912,
    "tensor_cores": 432,
    "compute_capability": "8.0",
    "typical_use_cases": ["ml_training", "inference", "hpc"]
  }
]
```

### Test Marketplace Service Through Gateway

```bash
curl http://localhost:8080/marketplace/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "marketplace-service"
}
```

### Test Trading Service Through Gateway

```bash
curl http://localhost:8080/trading/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "trading-service"
}
```

### Test Governance Service Through Gateway

```bash
curl http://localhost:8080/governance/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "governance-service"
}
```

## Expected Test Outcomes

### Successful Test Indicators

- All health endpoints return `{"status": "healthy", "service": "<service-name>"}`
- Gateway successfully proxies requests to microservices
- Service registry shows all registered services
- Database connections are established without errors
- No 500 errors or connection refused messages

### Failure Indicators

- Connection refused errors (service not running)
- 500 internal server errors (service error)
- Gateway routing failures (incorrect configuration)
- Database connection errors (database not set up)

## Troubleshooting

### Service Won't Start

**Issue:** Service fails to start with database connection error

**Solution:**
```bash
# Verify database exists
sudo -u postgres psql -l

# Recreate database if needed
sudo -u postgres psql -f apps/<service-name>/scripts/setup-database.sql

# Check service logs
sudo journalctl -u <service-name> -n 50
```

### Gateway Can't Reach Service

**Issue:** Gateway returns connection refused when proxying to service

**Solution:**
```bash
# Verify service is running
curl http://localhost:<port>/health

# Check gateway service registry
curl http://localhost:8080/services

# Verify service URL in gateway configuration
```

### Database Connection Errors

**Issue:** Service fails with "could not connect to server" error

**Solution:**
```bash
# Verify PostgreSQL is running
sudo systemctl status postgresql

# Check database credentials in service file
# Default: aitbc_<service>:password@localhost:5432/aitbc_<service>

# Test database connection manually
sudo -u postgres psql -d aitbc_<service>
```

### Port Already in Use

**Issue:** Service fails to start with "Address already in use" error

**Solution:**
```bash
# Find process using the port
sudo lsof -i :<port>

# Kill the process if needed
sudo kill <pid>

# Or use a different port in the service configuration
```

## Testing Checklist

Before considering testing complete:

- [ ] All databases created and accessible
- [ ] All services installed via Poetry
- [ ] All services start successfully in development mode
- [ ] All services start successfully in production mode (systemd)
- [ ] Health endpoints return healthy status for all services
- [ ] Gateway health check passes
- [ ] Gateway service registry shows all services
- [ ] Gateway successfully proxies requests to GPU service
- [ ] Gateway successfully proxies requests to Marketplace service
- [ ] Gateway successfully proxies requests to Trading service
- [ ] Gateway successfully proxies requests to Governance service
- [ ] No 500 errors in service logs
- [ ] No connection errors in gateway logs

## Next Steps

After successful testing:

1. Deploy services to production environment
2. Configure monitoring and alerting
3. Set up log aggregation
4. Implement automated testing in CI/CD pipeline
5. Gradually migrate traffic from coordinator-api to microservices
