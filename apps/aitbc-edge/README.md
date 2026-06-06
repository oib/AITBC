# Edge API Service

REST API for AITBC island and edge operations, providing HTTP equivalents for CLI commands.

## Overview

The Edge API Service exposes island and edge operations via REST API, following the coordinator-api pattern. It integrates with the existing GPU service and blockchain node RPC.

## Architecture

- **Port:** 8103
- **Database:** PostgreSQL (aitbc_edge)
- **Communication:**
  - Blockchain node RPC: localhost:8006
  - GPU service: localhost:8101
- **Authentication:** JWT tokens (same as coordinator-api)

## Installation

```bash
cd /opt/aitbc/apps/edge-api
pip install -e .
```

## Database Setup

Create PostgreSQL database and user:

```bash
sudo -u postgres psql
CREATE DATABASE aitbc_edge;
CREATE USER aitbc_edge WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE aitbc_edge TO aitbc_edge;
\q
```

## Running

### Development

```bash
cd /opt/aitbc/apps/edge-api
python -m edge_api.main
```

### Production (systemd)

```bash
# Install service
sudo cp edge-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable edge-api
sudo systemctl start edge-api
```

## API Endpoints

### Health Checks

- `GET /health` - Health check
- `GET /ready` - Readiness check

### Island Operations (Phase 2)

- `POST /v1/islands/join` - Join an island
- `POST /v1/islands/leave` - Leave an island
- `GET /v1/islands` - List all islands
- `GET /v1/islands/{island_id}` - Get island details
- `POST /v1/islands/bridge` - Request bridge

### GPU Operations (Phase 3)

- `POST /v1/gpu/listings` - List GPU on island
- `GET /v1/gpu/listings` - Get GPU listings
- `DELETE /v1/gpu/listings/{listing_id}` - Remove GPU listing
- `GET /v1/gpu/scan` - Scan GPUs

### Edge Database Operations (Phase 4)

- `POST /v1/database/init` - Initialize edge database
- `GET /v1/database` - Get edge database status
- `DELETE /v1/database` - Delete edge database
- `POST /v1/database/sync` - Sync edge database

### Edge Serve Operations (Phase 5)

- `POST /v1/serve/start` - Start serving
- `POST /v1/serve/stop` - Stop serving
- `GET /v1/serve/status` - Get serve status
- `GET /v1/serve/requests` - Get pending requests
- `POST /v1/serve/requests/{request_id}/complete` - Complete request

### Edge Metrics (Phase 6)

- `GET /v1/metrics` - Get edge metrics
- `GET /v1/metrics/gpu` - Get GPU metrics
- `GET /v1/metrics/database` - Get database metrics

## Implementation Status

**Phase 1: Foundation** ✅
- Service structure
- FastAPI application
- Database configuration
- Basic stub endpoints

**Phase 2: Island Operations** ⏳
- Island join/leave endpoints
- Blockchain RPC integration
- Island listing

**Phase 3: GPU Operations** ⏳
- GPU listing endpoints
- GPU service integration
- GPU metrics

**Phase 4: Edge Database** ⏳
- Database initialization
- Database sync
- Database management

**Phase 5: Edge Serve** ⏳
- Serve start/stop
- Request queue
- Request processing

**Phase 6: Metrics** ⏳
- Metrics collection
- Metrics endpoints
- Performance monitoring

## CLI Integration

CLI commands will be updated to use REST API instead of placeholder implementations:

- `aitbc island join` → `POST /v1/islands/join`
- `aitbc gpu list-island` → `POST /v1/gpu/listings`
- `aitbc database init-edge` → `POST /v1/database/init`
- `aitbc edge serve` → `POST /v1/serve/start`
- `aitbc edge metrics` → `GET /v1/metrics`

## Agent SDK Integration

Agent SDK will be updated to use REST API for island and edge operations.

## Dependencies

- FastAPI
- SQLAlchemy + SQLModel
- PostgreSQL
- httpx
- PyJWT
- uvicorn
