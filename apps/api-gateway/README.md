# AITBC API Gateway

Routes requests to AITBC microservices.

## Service Registry

The gateway routes requests to the following services:

- **GPU Service** (port 8101): `/gpu/*` → GPU resource management
- **Marketplace Service** (port 8102): `/marketplace/*` → GPU marketplace
- **Agent Service** (port 8103): `/agent/*` → Agent operations
- **Trading Service** (port 8104): `/trading/*` → Trading operations
- **Governance Service** (port 8105): `/governance/*` → Governance operations
- **Coordinator API** (port 8000): `/coordinator/*` → Coordinator API (default)

## Installation

```bash
cd /opt/aitbc
poetry install --with api-gateway
```

## Running

```bash
# Development
python -m api_gateway.main

# Production (systemd)
sudo systemctl start api-gateway
sudo systemctl enable api-gateway
```

## Testing

### Prerequisites

- All microservices installed via Poetry
- At least one microservice running (e.g., GPU service)
- Microservice database created (if testing that service)

### Start Gateway (Development)

```bash
python -m api_gateway.main
```

### Health Check

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{"status": "healthy", "service": "api-gateway"}
```

### Service Registry

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

### Test Routing to GPU Service

1. Start GPU service in another terminal:
   ```bash
   python -m gpu_service.main
   ```

2. Test through gateway:
   ```bash
   curl http://localhost:8080/gpu/health
   ```

Expected response:
```json
{"status": "healthy", "service": "gpu-service"}
```

### Test Routing to Marketplace Service

1. Start Marketplace service in another terminal:
   ```bash
   python -m marketplace_service.main
   ```

2. Test through gateway:
   ```bash
   curl http://localhost:8080/marketplace/health
   ```

Expected response:
```json
{"status": "healthy", "service": "marketplace-service"}
```

### Test Routing to Trading Service

1. Start Trading service in another terminal:
   ```bash
   python -m trading_service.main
   ```

2. Test through gateway:
   ```bash
   curl http://localhost:8080/trading/health
   ```

Expected response:
```json
{"status": "healthy", "service": "trading-service"}
```

### Test Routing to Governance Service

1. Start Governance service in another terminal:
   ```bash
   python -m governance_service.main
   ```

2. Test through gateway:
   ```bash
   curl http://localhost:8080/governance/health
   ```

Expected response:
```json
{"status": "healthy", "service": "governance-service"}
```

For comprehensive testing procedures, see [MICROSERVICES_TESTING_GUIDE.md](../docs/MICROSERVICES_TESTING_GUIDE.md).

## Endpoints

- `GET /health` - Health check
- `GET /services` - List registered services
- `/*` - Proxy all other requests to appropriate microservice

## Configuration

Service URLs are configured in `main.py` under the `SERVICES` dictionary.
