# API Gateway

**Level**: Intermediate<br>
**Prerequisites**: Familiarity with AITBC microservices architecture<br>
**Estimated Time**: 10 minutes<br>
**Last Updated**: 2026-05-03<br>
**Version**: 1.0

## 🧭 **Navigation Path:**
**🏠 [Documentation Home](../../README.md)** → **📦 Apps** → **🏗️ Infrastructure** → *You are here*

**breadcrumb**: Home → Apps → Infrastructure → API Gateway

---

## 🎯 **See Also:**
- **📖 [About Documentation](../../about/README.md)** - Template standard and audit checklist
- **🧭 [Master Index](../../MASTER_INDEX.md)** - Full documentation catalog
- **📁 [Infrastructure Overview](./README.md)** - Infrastructure services overview

---

## Overview

The AITBC API Gateway is a central routing service that directs requests to appropriate microservices. It provides a unified entry point for all AITBC services, simplifying client integration and enabling service discovery.

## Service Registry

The gateway routes requests to the following services:

| Service | Port | Routes | Description |
|---------|------|--------|-------------|
| GPU Service | 8101 | `/gpu/*` | GPU resource management |
| Marketplace Service | 8102 | `/marketplace/*` | GPU marketplace |
| Agent Service | 8103 | `/agent/*` | Agent operations |
| Trading Service | 8104 | `/trading/*` | Trading operations |
| Governance Service | 8105 | `/governance/*` | Governance operations |
| Coordinator API | 8000 | `/coordinator/*` | Coordinator API (default) |

## Installation

```bash
cd /opt/aitbc
poetry install --with api-gateway
```

## Running

### Development
```bash
python -m api_gateway.main
```

### Production (systemd)
```bash
sudo systemctl start api-gateway
sudo systemctl enable api-gateway
```

## Endpoints

- `GET /health` - Health check
- `GET /services` - List registered services
- `/*` - Proxy all other requests to appropriate microservice

## Configuration

Service URLs are configured in `main.py` under the `SERVICES` dictionary.

## Testing

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

### Test Routing
```bash
# Route to GPU service
curl http://localhost:8080/gpu/health

# Route to Marketplace service
curl http://localhost:8080/marketplace/health

# Route to Trading service
curl http://localhost:8080/trading/health

# Route to Governance service
curl http://localhost:8080/governance/health
```

## Architecture

The API Gateway implements:
- **Request Routing**: Directs requests to appropriate microservices based on URL patterns
- **Service Discovery**: Maintains a registry of available services
- **Health Monitoring**: Checks service health before routing
- **Load Balancing**: Distributes requests across service instances (future enhancement)

## Security

- TLS termination at gateway (future)
- Rate limiting (future)
- Authentication/Authorization (future)

## Troubleshooting

### Service Not Responding
1. Check if target microservice is running
2. Verify service URL configuration
3. Check gateway logs for routing errors

### Health Check Failing
1. Verify gateway is running on port 8080
2. Check systemd service status: `systemctl status api-gateway`
3. Review logs: `journalctl -u api-gateway -f`

---

*Last updated: 2026-05-03*<br>
*Version: 1.0*<br>
*Status: Active service*<br>
*Tags: api-gateway, infrastructure, routing, microservices*
