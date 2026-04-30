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

## Endpoints

- `GET /health` - Health check
- `GET /services` - List registered services
- `/*` - Proxy all other requests to appropriate microservice

## Configuration

Service URLs are configured in `main.py` under the `SERVICES` dictionary.
