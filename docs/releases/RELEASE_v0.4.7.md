# AITBC v0.4.7 Release Notes

**Date**: June 5, 2026
**Status**: ✅ Implemented
**Scope**: Multi-Model Ollama Support, Hardware+Software Bundle Offers (GPU-only marketplace deprecated), FFmpeg Video Processing Service, Service Reputation System

## 🎯 Overview

AITBC v0.4.7 enhances the software marketplace with multi-model Ollama support (local and cloud deployment), hardware+software bundle offers with GPU information, a new FFmpeg video processing service with GPU acceleration, and a comprehensive service reputation system with cross-node rating synchronization. This release enables shop owners to offer multiple Ollama models with different pricing, link software offers to specific GPU hardware, provide GPU-accelerated video processing as a metered service, and allow customers to rate and review services with automatic synchronization across nodes.

**Implementation Status:**
- ✅ Multi-Model Ollama Support - Fully Implemented
- ✅ Hardware+Software Bundle Offers - Fully Implemented
- ✅ FFmpeg Video Processing Service - Fully Implemented
- ✅ Service Reputation System - Fully Implemented
- ✅ Cross-Node Rating Synchronization - Fully Implemented
- ✅ **Service Stability Fixes** - All core services operational (2026-06-05)

## 🎯 Release Highlights

### Multi-Model Ollama Support
- ✅ Multiple Ollama models can be offered (local and cloud)
- ✅ Auto-detection of deployment type from model name suffix (`:cloud`)
- ✅ Different pricing per model
- ✅ Deployment type visible in offer listings
- ✅ Manual deployment type override via `--deployment-type` option

### Hardware+Software Bundle Offers
- ✅ All software offers include GPU hardware information
- ✅ Auto-detection of GPU name from nvidia-smi
- ✅ Manual GPU name override via `--gpu-name` option
- ✅ Optional GPU offer ID linking via `--gpu-offer-id` option
- ✅ GPU name visible in offer listings
- ✅ Cloud deployment marked as "N/A (cloud)"

### FFmpeg Video Processing Service
- ✅ GPU-accelerated video processing (NVENC/NVDEC)
- ✅ FastAPI service at port 8230
- ✅ Health and capabilities endpoints
- ✅ Video processing with format, codec, resolution, bitrate options
- ✅ Metered pricing based on processing time
- ✅ On-chain proof of work via result hash
- ✅ Routed through API Gateway at `/v1/ffmpeg/*`
- ✅ Systemd service configuration

### Cross-Node Agent Messaging System
- ✅ Coordinator API exposed through API Gateway at `/v1/coordinator/v1/hermes/*`
- ✅ Agent mailbox system for cross-node communication
- ✅ Message sending between agents on different nodes
- ✅ Message polling and retrieval by agent ID
- ✅ Host nginx proxy configuration for external access
- ✅ Ollama cloud model inference via public endpoint
- ✅ Full customer journey: discovery → messaging → inference → payment
- ✅ End-to-end verified: hub ↔ aitbc3 agent communication

### Service Reputation System
- ✅ ServiceRating model with service_id, rating (1-5), reviewer_id, comment, created_at
- ✅ SoftwareService model extended with avg_rating and rating_count fields
- ✅ Automatic rating aggregation and average calculation
- ✅ Rating submission via API and CLI
- ✅ Rating retrieval with pagination support
- ✅ Rating display in marketplace listings
- ✅ Database schema with sync metadata (synced_at, source_node)

### Cross-Node Rating Synchronization
- ✅ Sync metadata fields: synced_at, source_node
- ✅ GET `/v1/marketplace/ratings/unsynced` - Fetch unsynced ratings
- ✅ POST `/v1/marketplace/ratings/sync` - Sync ratings from remote with conflict resolution
- ✅ POST `/v1/marketplace/ratings/mark-synced` - Mark ratings as synced
- ✅ CLI command: `aitbc market sync-ratings [--remote-url] [--limit]`
- ✅ Conflict resolution: keep most recent rating based on timestamp
- ✅ Sync tracking and audit trail
- ✅ End-to-end tested: hub → aitbc3 rating propagation

### Service Stability Fixes (2026-06-05)
- ✅ **Coordinator API**: Fixed import errors and deprecated schema references
- ✅ **AgentDaemon**: Resolved polling URL configuration and endpoint connectivity
- ✅ **Marketplace Service**: Fixed database schema with missing rating columns
- ✅ **Service Dependencies**: Resolved missing ipfshttpclient and other dependencies
- ✅ **Service Management**: Fixed systemd service unit file linking
- ✅ **Database Migrations**: Applied schema updates for rating system functionality

### CLI Enhancements
- ✅ `aitbc market offer` — renamed from `software-offer` (hardware+software bundle)
  - `--gpu-name` — GPU name (auto-detected from nvidia-smi)
  - `--gpu-device` — GPU device ID (0, 1, 2, etc.) for multi-GPU servers
  - `--gpu-offer-id` — GPU marketplace offer ID
  - `ffmpeg` added to service type choices
  - `per_processing_hour` added to pricing unit choices
  - `--deployment-type` removed (inferred from model name suffix)
- ✅ `aitbc market process` — NEW FFmpeg video processing command
  - `--format` — output format (mp4, webm)
  - `--codec` — target codec (h264, vp9, av1)
  - `--resolution` — target resolution (1080p, 720p, 480p)
  - `--bitrate` — target bitrate (5M, 10M)
- ✅ `aitbc market list` — updated to show GPU device and service ratings
- ✅ `aitbc market rate` — NEW rating submission command
  - `service_id` — service to rate (plugin_id or offer_id)
  - `rating` — rating value (1.0-5.0)
  - `--comment` — optional review text
  - `--reviewer-id` — reviewer ID (defaults to wallet address)
- ✅ `aitbc market ratings` — NEW rating retrieval command
  - `service_id` — service to view ratings for
  - `--limit` — number of ratings to return (default: 50)
  - `--offset` — pagination offset (default: 0)
- ✅ `aitbc market sync-ratings` — NEW cross-node sync command
  - `--remote-url` — remote marketplace service URL (default: https://aitbc3.aitbc.bubuit.net/api)
  - `--limit` — number of ratings to sync (default: 100)

### API Gateway Integration
- ✅ FFmpeg service added to service registry
- ✅ Routing `/v1/ffmpeg/*` → `http://localhost:8230/*`
- ✅ No nginx configuration changes needed

### Plugin Registry Updates
- ✅ `deployment_type` field added to plugin schema
- ✅ `gpu_name` field added to plugin schema
- ✅ `gpu_offer_id` field added to plugin schema
- ✅ FFmpeg service type support

### Plugin Service Migration
- ✅ Plugin service (port 8109) migrated into marketplace service (port 8102)
- ✅ SoftwareService model added to marketplace database
- ✅ Software service endpoints added to marketplace API (`/v1/marketplace/software-services/*`)
- ✅ CLI updated to register with marketplace service
- ✅ API Gateway updated to route plugin requests to marketplace service
- ✅ Migration script created and executed (2 entries migrated)
- ✅ aitbc-plugin.service decommissioned
- ✅ Database-backed registry replaces JSON file store

### Multi-GPU Support
- ✅ GPU device ID and UUID captured from nvidia-smi
- ✅ `--gpu-device` option added to software_offer CLI
- ✅ SoftwareService model extended with `gpu_device` and `gpu_uuid` fields
- ✅ Blockchain payload includes GPU device and UUID
- ✅ Market list displays GPU device in format "GPU Name [GPU X]"
- ✅ Enables service placement on specific GPUs in multi-GPU servers
- ✅ Removed `--deployment-type` option (inferred from model name suffix)

## 📋 Detailed Features

### Plugin Service Migration

#### Architecture Change
The plugin service (port 8109) has been migrated into the marketplace service (port 8102). This consolidates marketplace functionality and provides database-backed persistence instead of JSON file storage.

**Before:**
- aitbc-plugin.service (8109) - JSON file registry at `/var/lib/aitbc/plugins.json`
- Separate service to manage
- File-based storage

**After:**
- SoftwareService table in marketplace database
- Part of aitbc-marketplace.service (8102)
- Database-backed with better scalability

#### New Endpoints
Software service registry is now available at:
- `GET /v1/marketplace/software-services` - List all software services
- `GET /v1/marketplace/software-services/{plugin_id}` - Get specific service
- `POST /v1/marketplace/software-services` - Register/update service
- `DELETE /v1/marketplace/software-services/{plugin_id}` - Unregister service

#### API Gateway Routing
Legacy `/v1/plugin/*` requests are automatically rewritten to `/v1/marketplace/software-services/*`:
```
/v1/plugin/plugins → /v1/marketplace/software-services
/v1/plugin/{id} → /v1/marketplace/software-services/{id}
```

#### Migration Script
Migration script at `/opt/aitbc/scripts/migration/migrate_plugin_to_marketplace.py`:
- Backs up original JSON file to `/var/lib/aitbc/plugins.json.backup`
- Converts JSON entries to SoftwareService database records
- Preserves all metadata (deployment_type, gpu_name, gpu_offer_id)
- 2 entries migrated successfully (ollama-llama3.2-3b, whisper-base)

#### Service Decommission
- aitbc-plugin.service stopped and disabled
- Systemd symlink removed
- Port 8109 no longer in use
- Original JSON file preserved for reference

### Multi-GPU Support

#### GPU Device Identification
The marketplace now supports multi-GPU servers by capturing GPU device ID and UUID from nvidia-smi. This enables precise hardware binding for software services.

**nvidia-smi output parsing:**
```
GPU 0: NVIDIA GeForce RTX 4060 Ti (UUID: GPU-ba5c6553-6396-ab66-5706-17e6de30a93a)
GPU 1: NVIDIA GeForce RTX 4090 (UUID: GPU-abc123...)
```

**New CLI option:**
```bash
# Specify which GPU to use
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour --gpu-device 1

# Auto-detect (defaults to GPU 0)
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour
```

**Use cases:**
- Run FFmpeg on GPU 3 (for video encoding)
- Run Ollama on GPU 1 (bigger GPU for LLM)
- Reserve GPU 0 for Hermes (no offers)
- Different pricing per GPU capability

**Blockchain payload:**
```json
{
  "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
  "gpu_device": "0",
  "gpu_uuid": "GPU-ba5c6553-6396-ab66-5706-17e6de30a93a",
  ...
}
```

**Market list display:**
```
GPU: NVIDIA GeForce RTX 4060 Ti [GPU 0]
GPU: NVIDIA GeForce RTX 4090 [GPU 1]
GPU: N/A (cloud)
```

**Deployment type inference:**
- Removed `--deployment-type` option
- Automatically inferred from model name suffix:
  - `model:cloud` → cloud deployment
  - Otherwise → local deployment

### Multi-Model Ollama Support

#### Deployment Type Auto-Detection
Models ending with `:cloud` are automatically classified as cloud deployment:
```bash
# Local model (auto-detected)
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour

# Cloud model (auto-detected)
aitbc market offer ollama nemotron-3-super:cloud 0.10 --unit per_hour

# Manual override
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour --deployment-type local
```

#### Blockchain Payload
```json
{
  "action": "software_offer",
  "deployment_type": "local|cloud",
  "model": "llama3.2:3b",
  ...
}
```

### Hardware+Software Bundle Offers

#### GPU Name Auto-Detection
GPU name is automatically detected from nvidia-smi for local deployments:
```bash
# Auto-detect GPU name
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour
# Output: Auto-detected GPU: NVIDIA GeForce RTX 4060 Ti

# Explicit GPU name
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour \
  --gpu-name "NVIDIA GeForce RTX 4060 Ti"

# Cloud deployment (no GPU)
aitbc market offer ollama nemotron-3-super:cloud 0.10 --unit per_hour \
  --deployment-type cloud
# Output: GPU name: N/A (cloud)
```

#### GPU Offer Linking
Optional linking to GPU marketplace offer for cross-reference:
```bash
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour \
  --gpu-offer-id gpu_offer_20260605120000_abc12345
```

#### Blockchain Payload
```json
{
  "action": "software_offer",
  "gpu_name": "NVIDIA GeForce RTX 4060 Ti",
  "gpu_offer_id": "gpu_offer_...",
  ...
}
```

#### Market List Output
```
Offer ID          | Type     | Service | Model          | Deploy  | GPU Name                     | Price
sw_offer_...      | SOFTWARE | ollama  | llama3.2:3b    | local   | NVIDIA GeForce RTX 4060 Ti  | 0.05 AIT/h
sw_offer_...      | SOFTWARE | ollama  | nemotron:cloud | cloud   | N/A (cloud)                  | 0.10 AIT/h
```

### FFmpeg Video Processing Service

#### Service Endpoints
- `GET /health` — Service health check
- `GET /capabilities` — List supported codecs, formats, GPU info
- `POST /process` — Process video with GPU acceleration

#### Capabilities Endpoint
```bash
curl http://localhost:8230/capabilities
```
Returns:
```json
{
  "gpu": {
    "name": "NVIDIA GeForce RTX 4060 Ti",
    "memory": "16380 MiB"
  },
  "hw_accel": "cuda",
  "supported_encoders": ["..."],
  "gpu_device": "0"
}
```

#### Process Endpoint
```bash
curl -X POST http://localhost:8230/process \
  -F "file=@input.mp4" \
  -F "output_format=mp4" \
  -F "codec=h264" \
  -F "resolution=1080p" \
  -F "bitrate=5M"
```
Returns:
```json
{
  "status": "completed",
  "output_path": "/tmp/...",
  "file_size_bytes": 12345678,
  "processing_time_seconds": 45.67,
  "processing_time_hours": 0.0127,
  "codec": "h264",
  "resolution": "1080p",
  "bitrate": "5M",
  "result_hash": "abc123...",
  "gpu_device": "0",
  "hw_accel": "cuda"
}
```

#### CLI Command
```bash
# Register FFmpeg offer
aitbc market offer ffmpeg default 0.15 --unit per_processing_hour

# Process video
aitbc market process <offer_id> input.mp4 --format mp4 --codec h264 --resolution 1080p --bitrate 5M
```

#### On-Chain Proof of Work
FFmpeg service returns `result_hash` (SHA256 of output file). The `market process` command posts a `software_job` transaction on-chain with:
- job_id, offer_id, result_hash, actual_processing_hours, actual_cost

#### API Gateway Routing
Requests to `/v1/ffmpeg/*` are proxied to `http://localhost:8230/*` by the API Gateway.

## 🔧 Configuration

### FFmpeg Service Configuration
**Environment Variables** (`/etc/aitbc/ffmpeg.env`):
```bash
FFMPEG_PORT=8230
FFMPEG_GPU_DEVICE=0
FFMPEG_HW_ACCEL=cuda
```

**Systemd Service** (`/etc/systemd/system/aitbc-ffmpeg.service`):
```ini
[Unit]
Description=AITBC FFmpeg Video Processing Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc
EnvironmentFile=/etc/aitbc/ffmpeg.env
ExecStart=/opt/aitbc/venv/bin/python /opt/aitbc/apps/ffmpeg-service/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### API Gateway Configuration
FFmpeg service added to SERVICES dict in `/opt/aitbc/apps/api-gateway/src/api_gateway/main.py`:
```python
"ffmpeg": {
    "base_url": os.getenv("FFMPEG_SERVICE_URL", "http://localhost:8230"),
    "prefix": "/v1/ffmpeg",
},
```

## 📦 Dependencies

### New Dependencies
- FFmpeg with GPU acceleration (NVENC/NVDEC)
- Python packages: fastapi, uvicorn (already in venv)

### System Requirements
- NVIDIA GPU with CUDA support
- FFmpeg with hardware acceleration support
- nvidia-smi for GPU detection

## 🚀 Migration Guide

### v0.4.6 → v0.4.7

1. **Install FFmpeg with GPU support**
   ```bash
   # Ubuntu/Debian
   apt install ffmpeg libavcodec-extra

   # Verify GPU support
   ffmpeg -hwaccels
   ```

2. **Configure FFmpeg service**
   ```bash
   # /etc/aitbc/ffmpeg.env
   FFMPEG_PORT=8230
   FFMPEG_GPU_DEVICE=0
   FFMPEG_HW_ACCEL=cuda
   ```

3. **Start FFmpeg service**
   ```bash
   # Create symlink
   ln -s /opt/aitbc/apps/ffmpeg-service/aitbc-ffmpeg.service /etc/systemd/system/aitbc-ffmpeg.service

   # Enable and start
   systemctl daemon-reload
   systemctl enable aitbc-ffmpeg
   systemctl start aitbc-ffmpeg
   ```

4. **Update API Gateway configuration**
   ```bash
   # Restart API Gateway (config already updated in code)
   systemctl restart aitbc-api-gateway
   ```

5. **Register new offers**
   ```bash
   # Local Ollama model (GPU name auto-detected)
   aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour

   # Cloud Ollama model
   aitbc market offer ollama nemotron-3-super:cloud 0.10 --unit per_hour

   # FFmpeg service
   aitbc market offer ffmpeg default 0.15 --unit per_processing_hour
   ```

## 🔧 Service Stability Fixes (2026-06-05)

### Issues Resolved

#### 1. Coordinator API Import Errors
**Problem**: Coordinator API failed to start due to deprecated schema imports
```bash
ImportError: cannot import name 'MarketplaceBidRequest' from 'app.schemas'
```

**Solution**: 
- Removed deprecated `MarketplaceBidRequest` and `MarketplaceBidView` imports from multiple files
- Updated `/opt/aitbc/apps/coordinator-api/src/app/contexts/marketplace/services/marketplace.py`
- Updated `/opt/aitbc/apps/coordinator-api/src/app/models/__init__.py`
- Service now starts successfully on port 8203

#### 2. AgentDaemon Connection Issues
**Problem**: AgentDaemon unable to connect to Coordinator API
```bash
HTTPConnectionPool(host='localhost', port=8203): Max retries exceeded with url: /v1/hermes/messages/owl-hub
Connection refused
```

**Solution**:
- Fixed polling URL configuration in `/opt/aitbc/apps/agent-coordinator/scripts/hermes_polling_daemon.py`
- Updated coordinator URL from port 8107 to 8203 in `/etc/aitbc/node.env`
- Corrected endpoint path from `/api/v1/agent/messages/` to `/v1/hermes/messages/`
- AgentDaemon now successfully polls every 10 seconds

#### 3. Marketplace Service Database Schema
**Problem**: Marketplace service crashed due to missing database columns
```bash
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such column: softwareservice.avg_rating
```

**Solution**:
- Added missing `avg_rating` and `rating_count` columns to `softwareservice` table
- Applied database migration: `ALTER TABLE softwareservice ADD COLUMN avg_rating FLOAT DEFAULT 0.0`
- Service now runs without database errors

#### 4. Missing Dependencies
**Problem**: Coordinator API missing required Python packages
```bash
No module named 'ipfshttpclient'
```

**Solution**:
- Added `ipfshttpclient>=0.7.0` to `/opt/aitbc/requirements.txt`
- Installed dependency in virtual environment
- IPFS features now properly enabled

#### 5. Service Management Issues
**Problem**: Marketplace service unit file missing from systemd
```bash
Failed to restart aitbc-marketplace.service: Unit aitbc-marketplace.service not found
```

**Solution**:
- Recreated systemd symlink: `ln -s /opt/aitbc/apps/marketplace/aitbc-marketplace.service /etc/systemd/system/`
- Reloaded systemd daemon
- Service now properly manageable with systemctl commands

### Current Service Status (2026-06-05)
- ✅ **aitbc-coordinator-api.service**: Running on port 8203, Hermes endpoints operational
- ✅ **aitbc-agent-daemon.service**: Running, polling successfully every 10 seconds
- ✅ **aitbc-marketplace.service**: Running, database schema updated and healthy
- ✅ **All dependencies**: Installed and functional

## 🧪 Testing

### Ollama Multi-Model Testing
```bash
# Register local model offer
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour

# Register cloud model offer
aitbc market offer ollama nemotron-3-super:cloud 0.10 --unit per_hour

# Verify deployment type in market list
aitbc market list
```

### Hardware Binding Testing
```bash
# Register with auto-detected GPU
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour

# Register with explicit GPU name
aitbc market offer ollama llama3.2:3b 0.05 --unit per_hour \
  --gpu-name "NVIDIA GeForce RTX 4060 Ti"

# Verify GPU name in market list
aitbc market list
```

### FFmpeg Service Testing
```bash
# Test health endpoint
curl http://localhost:8230/health

# Test capabilities endpoint
curl http://localhost:8230/capabilities

# Test video processing
aitbc market offer ffmpeg default 0.15 --unit per_processing_hour
aitbc market process <offer_id> input.mp4 --format mp4 --codec h264 --resolution 1080p
```

## 🌐 Cross-Node Agent Messaging System

### Implementation Details

The cross-node agent messaging system enables agents on different AITBC nodes to communicate via the Coordinator API, which is now exposed through the API Gateway for external access.

**Architecture:**
- Coordinator API (port 8203) exposed via API Gateway at `/v1/coordinator/v1/hermes/*`
- Host nginx proxy handles SSL termination and forwards requests to container
- Agent mailbox system for message storage and retrieval
- Polling-based message delivery for cross-node communication

**Key Components:**
- **API Gateway Configuration**: Added coordinator service routing to `/v1/coordinator/` prefix
- **Host Nginx Proxy**: Configured to forward `/ollama/` and `/api/` paths to container
- **Ollama Proxy**: Fixed Host header issue (override to "localhost" to avoid 403 errors)
- **Agent Messaging**: Send/receive messages between agents on different nodes

### Verified Test Results

All cross-node flows have been tested and verified working:

| Flow | Endpoint | Result |
|------|----------|--------|
| Marketplace Discovery | GET /api/v1/marketplace/offer | ✅ 200 — Returns offer |
| Ollama Model List | GET /ollama/api/tags | ✅ 200 — Returns nemotron-3-super:cloud |
| Ollama Inference | POST /ollama/api/generate | ✅ 200 — Returns generation |
| Agent Msg Send (hub→shop) | POST /api/v1/coordinator/v1/hermes/messages/send | ✅ 200 — Message sent |
| Agent Msg Recv (shop) | GET /api/v1/coordinator/v1/hermes/messages/owl-aitbc3 | ✅ 200 — Returns messages |
| Agent Msg Send (shop→hub) | POST /api/v1/coordinator/v1/hermes/messages/send | ✅ 200 — Response sent |
| Agent Msg Recv (hub) | GET /api/v1/coordinator/v1/hermes/messages/owl-hub | ✅ 200 — Returns shop response |

### End-to-End Customer Journey

1. **Discovery**: Customer discovers shop's offer via marketplace API
2. **Direct Inference**: Customer calls Ollama API directly for inference
3. **Agent Messaging**: Customer sends message to shop agent
4. **Message Processing**: Shop receives and processes message
5. **Response**: Shop sends response back to customer
6. **Payment**: Escrow-based payment with proof of work

### Configuration Changes

**API Gateway (`/opt/aitbc/apps/api-gateway/src/api_gateway/main.py`):**
```python
"coordinator": {
    "base_url": os.getenv("COORDINATOR_API_URL", "http://localhost:8203"),
    "prefix": "/v1/coordinator",
},
```

**Container Nginx (`/etc/nginx/sites-enabled/aitbc`):**
```nginx
location /ollama/ {
    proxy_pass http://127.0.0.1:11434/;
    proxy_set_header Host "localhost";  # Fixed 403 issue
    # ... WebSocket support
}
```

**Host Nginx Proxy:**
- Configured to forward `/ollama/` and `/api/` paths to container
- SSL termination handled by host reverse proxy
- WebSocket support for streaming responses

### Documentation

Updated howto guide at `/opt/aitbc/docs/marketplace/agent-nemotron-cloud-inference.md` with:
- Working examples for all components
- Troubleshooting steps for common issues
- Agent messaging workflow documentation
- Cross-node access requirements

## 🐛 Breaking Changes

- **CLI command renamed**: `aitbc market offer` → `aitbc market offer` (now represents hardware+software bundles)
- Software offer payload now includes `gpu_device` and `gpu_uuid` fields for multi-GPU support
- `--deployment-type` option removed (inferred from model name suffix `:cloud`)
- New service type `ffmpeg` added to marketplace
- New pricing unit `per_processing_hour` added
- FFmpeg service routed through API Gateway instead of direct nginx
- **GPU-only marketplace deprecated** - all offers must be hardware+software bundles
  - Old `aitbc market offer gpu_id price duration` command removed
  - `aitbc market bid` command removed
  - `aitbc market accept` command removed
  - Only `aitbc market offer` (hardware+software bundle) remains
- **Plugin service (port 8109) decommissioned** - functionality migrated to marketplace service (port 8102)
- **Software service registry now database-backed** - `/var/lib/aitbc/plugins.json` no longer used

## 📝 Additional Suggestions

Based on the current architecture, here are additional features to consider for future releases:

1. **Model size metadata** - Add VRAM requirements and model parameter count to offers
2. **GPU specification taxonomy** - Standardize GPU metadata (VRAM, CUDA cores, memory bandwidth)
3. **Cloud provider integration** - Auto-detect cloud provider from model name (e.g., `:aws`, `:gcp`, `:azure`)
4. **Performance benchmarks** - Include benchmark scores (tokens/sec, fps) in offers
5. **Dynamic pricing** - Adjust pricing based on GPU class and model performance
6. **Service composition** - Allow chaining multiple services (e.g., transcribe → summarize)
7. **FFmpeg operation catalog** - Support more FFmpeg operations (thumbnail generation, audio extraction, GIF creation)
8. **GPU pool management** - Allow software offers to use GPU pools instead of single GPU offers
9. **Hardware compatibility checks** - Validate GPU meets minimum requirements for model (VRAM, compute capability)
10. **Service health monitoring** - Add health status to plugin registry for service availability
11. **GPU utilization metrics** - Track and report GPU utilization during job execution
12. **Multi-GPU support** - Allow software offers to span multiple GPUs for large models
13. **Service versioning** - Add version field to software offers for compatibility tracking
14. **Regional pricing** - Adjust pricing based on node location/region
15. **Batch job support** - Allow submitting multiple jobs in a single transaction
16. **Service SLA guarantees** - Define and enforce service level agreements
17. **Resource quotas** - Limit concurrent jobs per GPU to prevent overload
18. **Service dependencies** - Declare dependencies between services (e.g., model download)
19. **Usage analytics** - Track usage patterns for pricing optimization
20. **Service reputation** - Extend reputation system to include service-specific ratings

## ✅ Success Criteria

- ✅ Multiple Ollama models can be registered (local and cloud)
- ✅ Deployment type visible in offer listings
- ✅ Software offers can be bound to GPU offers
- ✅ Hardware class visible in offer listings
- ✅ FFmpeg service operational with GPU acceleration
- ✅ FFmpeg offers can be registered and executed
- ✅ Metered payment for FFmpeg processing time
- ✅ On-chain proof of work for FFmpeg jobs
- ✅ Documentation complete
- ✅ Migration guide tested
- ✅ **All core services operational and stable**
- ✅ **Service startup issues resolved**
- ✅ **Database schema updated and functional**
- ✅ **Agent messaging system working end-to-end**

## 🔗 Related Files

- `/opt/aitbc/cli/aitbc_cli/commands/market.py` — CLI marketplace commands
- `/opt/aitbc/apps/ffmpeg-service/main.py` — FFmpeg FastAPI service
- `/opt/aitbc/apps/ffmpeg-service/aitbc-ffmpeg.service` — Systemd service
- `/opt/aitbc/apps/api-gateway/src/api_gateway/main.py` — API Gateway routing
- `/opt/aitbc/apps/agent-management/examples/plugin-service/src/plugin_service/main.py` — Plugin registry
- `/etc/aitbc/ffmpeg.env` — FFmpeg environment configuration
