# AITBC GPU Service

Manages GPU resource operations.

## Installation

```bash
cd /opt/aitbc
poetry install --with gpu-service
```

## Database Setup

Create a separate database for the GPU service:

```bash
sudo -u postgres psql -f apps/gpu-service/scripts/setup-database.sql
```

Or manually:

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
- `GET /v1/marketplace/edge-gpu/profiles` - Get consumer GPU profiles
- `GET /v1/marketplace/edge-gpu/metrics/{gpu_id}` - Get edge GPU metrics
- `POST /v1/marketplace/edge-gpu/scan/{miner_id}` - Scan and register edge GPUs
- `POST /v1/marketplace/edge-gpu/optimize/inference/{gpu_id}` - Optimize ML inference

## Testing

### Prerequisites

- PostgreSQL running and aitbc_gpu database created
- Poetry dependencies installed

### Database Setup

```bash
sudo -u postgres psql -f scripts/setup-database.sql
```

### Start Service (Development)

```bash
python -m gpu_service.main
```

### Health Check

```bash
curl http://localhost:8101/health
```

Expected response:
```json
{"status": "healthy", "service": "gpu-service"}
```

### GPU Status

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

### Get Consumer GPU Profiles

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

### Test Through Gateway

1. Start the API gateway:
   ```bash
   python -m api_gateway.main
   ```

2. Test GPU endpoints through the gateway:
   ```bash
   curl http://localhost:8080/gpu/health
   curl http://localhost:8080/gpu/v1/marketplace/edge-gpu/profiles
   ```

For comprehensive testing procedures, see [MICROSERVICES_TESTING_GUIDE.md](../docs/MICROSERVICES_TESTING_GUIDE.md).

## Service Configuration

- Port: 8101
- Database: aitbc_gpu
- Gateway route: /gpu/*

## Migration Status

**Completed:**
- Extracted GPU domain models (GPUArchitecture, GPURegistry, ConsumerGPUProfile, EdgeGPUMetrics, GPUBooking, GPUReview)
- Extracted GPU services (EdgeGPUService)
- Extracted GPU data (consumer_gpu_profiles)
- Set up database session management
- Extracted GPU router endpoints
- Removed edge_gpu router from coordinator-api
- Created systemd service configuration
- Created database setup script

**Remaining:**
- Extract additional GPU routers (gpu_multimodal_health.py, miner.py) if needed
- Run database migration script to create aitbc_gpu database
- Install and enable systemd service
- End-to-end testing with gateway
