# AITBC GPU Service

Manages GPU resource operations.

## Installation

```bash
cd /opt/aitbc
poetry install --with gpu-service
```

## Database Setup

Create a separate database for the GPU service:

```sql
CREATE DATABASE aitbc_gpu;
CREATE USER aitbc_gpu WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_gpu TO aitbc_gpu;
```

## Running

```bash
# Development
python -m gpu_service.main

# Production (systemd)
sudo systemctl start gpu-service
sudo systemctl enable gpu-service
```

## Endpoints

- `GET /health` - Health check
- `GET /gpu/status` - Get GPU status

## Future Work

To fully extract GPU functionality from coordinator-api, the following needs to be done:

1. **Extract domain models**: Copy GPU-related domain models from coordinator-api
2. **Extract services**: Copy GPU-related services from coordinator-api
3. **Extract storage layer**: Set up separate database session management
4. **Extract routers**: Copy GPU routers (edge_gpu.py, gpu_multimodal_health.py, miner.py)
5. **Update coordinator-api**: Remove GPU-related code
6. **Update gateway**: GPU service is already configured in gateway

## Service Configuration

- Port: 8101
- Database: aitbc_gpu
- Gateway route: /gpu/*
