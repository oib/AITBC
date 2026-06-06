# Multi-Region Load Balancer

## Status
✅ Operational

## Overview
Load balancing service for distributing traffic across multiple regions and ensuring high availability and optimal performance.

## Architecture

### Core Components
- **Load Balancer**: Distributes traffic across regions
- **Health Checker**: Monitors regional health status
- **Traffic Router**: Routes traffic based on load and latency
- **Failover Manager**: Handles failover between regions
- **Configuration Manager**: Manages load balancing rules

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Multiple regional endpoints
- DNS configuration for load balancing

### Installation
```bash
cd /opt/aitbc/apps/multi-region-load-balancer
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
REGIONAL_ENDPOINTS=us-east:https://us.example.com,eu-west:https://eu.example.com
LOAD_BALANCING_STRATEGY=round_robin|least_latency|weighted
HEALTH_CHECK_INTERVAL=30
FAILOVER_ENABLED=true
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
4. Configure regional endpoints
5. Run tests: `pytest tests/`

### Project Structure
```
multi-region-load-balancer/
├── src/
│   ├── load_balancer/        # Load balancing logic
│   ├── health_checker/       # Regional health monitoring
│   ├── traffic_router/       # Traffic routing
│   ├── failover_manager/     # Failover management
│   └── config_manager/       # Configuration management
├── tests/                    # Test suite
└── pyproject.toml            # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run load balancer tests
pytest tests/test_load_balancer.py

# Run failover tests
pytest tests/test_failover.py
```

## API Reference

### Load Balancing

#### Get Load Balancer Status
```http
GET /api/v1/lb/status
```

#### Configure Load Balancing Strategy
```http
PUT /api/v1/lb/strategy
Content-Type: application/json

{
  "strategy": "round_robin|least_latency|weighted",
  "parameters": {}
}
```

#### Get Regional Status
```http
GET /api/v1/lb/regions
```

### Health Checks

#### Run Health Check
```http
POST /api/v1/lb/health/check
Content-Type: application/json

{
  "region": "us-east"
}
```

#### Get Health History
```http
GET /api/v1/lb/health/history?region=us-east
```

### Failover

#### Trigger Manual Failover
```http
POST /api/v1/lb/failover/trigger
Content-Type: application/json

{
  "from_region": "us-east",
  "to_region": "eu-west"
}
```

#### Get Failover Status
```http
GET /api/v1/lb/failover/status
```

### Configuration

#### Add Regional Endpoint
```http
POST /api/v1/lb/regions
Content-Type: application/json

{
  "region": "us-west",
  "endpoint": "https://us-west.example.com",
  "weight": 1.0
}
```

#### Remove Regional Endpoint
```http
DELETE /api/v1/lb/regions/{region}
```

## Configuration

### Environment Variables
- `REGIONAL_ENDPOINTS`: Comma-separated regional endpoints
- `LOAD_BALANCING_STRATEGY`: Strategy for load distribution
- `HEALTH_CHECK_INTERVAL`: Interval for health checks (default: 30s)
- `FAILOVER_ENABLED`: Enable automatic failover
- `FAILOVER_THRESHOLD`: Threshold for triggering failover

### Load Balancing Strategies
- **Round Robin**: Distributes traffic evenly across regions
- **Least Latency**: Routes to region with lowest latency
- **Weighted**: Uses configured weights for distribution

### Health Check Parameters
- **Check Interval**: Frequency of health checks
- **Timeout**: Timeout for health check responses
- **Failure Threshold**: Number of failures before marking region down

## Troubleshooting

**Load balancing not working**: Verify regional endpoints and strategy configuration.

**Failover not triggering**: Check health check configuration and thresholds.

**High latency**: Review regional health and network connectivity.

**Uneven distribution**: Check weights and load balancing strategy.

## Security Notes

- Use TLS for all regional connections
- Implement authentication for load balancer API
- Monitor for DDoS attacks
- Regularly review regional access
- Implement rate limiting
