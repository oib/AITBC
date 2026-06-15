# AITBC v0.4.5 Release Notes

**Date**: June 3, 2026
**Status**: ✅ Released
**Scope**: Software Marketplace & On-Chain Proof of Work

## 🎯 Overview

AITBC v0.4.5 introduces a blockchain-native software marketplace for AI/ML services with on-chain proof of work. This release enables providers to offer software services (Ollama LLM inference, Whisper audio transcription, PeerTube video transcoding) as discoverable marketplace offers, with metered escrow payments and immutable proof of job completion. The plugin registry provides agent-discoverable service metadata, and public nginx endpoints enable remote access to services.

## 🎯 Release Highlights

### Software Marketplace
- ✅ Blockchain-native software offer registration (no PostgreSQL dependency)
- ✅ Support for multiple service types: Ollama (LLM), Whisper (transcription), PeerTube (transcoding)
- ✅ Metered pricing models: per token, per audio minute, per video minute
- ✅ Offer discovery via hub blockchain transactions
- ✅ CLI commands: `market software-offer`, `market run`, `market transcribe`, `market transcode`

### On-Chain Proof of Work
- ✅ Result hash (SHA256) returned by services for output verification
- ✅ `software_job` blockchain transaction records job completion
- ✅ Job TX hash stored in escrow records for audit trail
- ✅ Full chain: offer → job (proof) → escrow release (payment)

### Plugin Registry Service
- ✅ JSON-backed registry at port 8109
- ✅ Auto-registration after successful blockchain offer TX
- ✅ Live offer resolution from hub chain
- ✅ Endpoints: GET /plugins, GET /plugins/{id}, POST /register, DELETE /plugins/{id}

### Public Service Endpoints
- ✅ Nginx reverse proxy with path rewriting
- ✅ Public HTTPS endpoints: /whisper/, /plugin/, /peertube/
- ✅ Node-agnostic nginx config with hostname override
- ✅ Deploy script: install-nginx-node.sh

### Whisper Transcription Service
- ✅ FastAPI service at port 8110
- ✅ GPU-accelerated transcription via faster-whisper
- ✅ Returns result_hash for on-chain proof
- ✅ Systemd service: aitbc-whisper.service

### PeerTube Transcoding Service
- ✅ FastAPI service at port 8220
- ✅ Wraps peertube-runner for VOD transcoding
- ✅ Returns result_hash for on-chain proof
- ✅ Systemd service: aitbc-peertube-transcoder.service

### Escrow Integration
- ✅ Metered escrow locking before job execution
- ✅ Actual cost calculation after job completion
- ✅ Escrow release with job TX hash reference
- ✅ Database schema update: Escrow.job_tx_hash column

## 📋 Detailed Features

### Software Offer Registration

#### CLI Command
```bash
aitbc market software-offer ollama|whisper|peertube_transcoder <model> <price> --unit per_token|per_audio_min|per_video_min
```

#### Blockchain Transaction
```json
{
  "action": "software_offer",
  "offer_id": "sw_offer_YYYYMMDDHHMMSS_<8hex>",
  "service_type": "ollama|whisper|peertube_transcoder",
  "model": "llama3|base|default",
  "price": 0.001,
  "price_unit": "per_token|per_audio_min|per_video_min",
  "provider_address": "0x...",
  "endpoint": "https://<node_fqdn>/<service>/",
  "created_at": "2026-06-03T..."
}
```

#### Auto-Registration
After successful blockchain TX, offer is auto-registered in local plugin registry for agent discovery.

### Job Execution Flow

#### 1. Offer Discovery
```bash
aitbc market list  # Queries hub /rpc/transactions for software_offer actions
```

#### 2. Escrow Locking
```bash
# Estimate cost based on input size
estimated_cost = duration * price
job_id = sw_job_YYYYMMDDHHMMSS_<8hex>
contract_id = escrow_create(job_id, buyer, provider, estimated_cost)
```

#### 3. Service Execution
```bash
# Service processes input and returns result_hash
result = {
  "text": "...",  # or transcoded_url
  "result_hash": "sha256(...)",
  "duration_seconds": 12.5
}
```

#### 4. On-Chain Proof
```bash
# Post software_job TX with result_hash
job_tx = {
  "action": "software_job",
  "job_id": job_id,
  "offer_id": offer_id,
  "result_hash": result_hash,
  "actual_duration": duration,
  "actual_cost": actual_cost,
  "status": "completed"
}
```

#### 5. Escrow Release
```bash
# Release payment with job TX hash reference
escrow_release(job_id, actual_cost, job_tx_hash)
```

### Service Endpoints

#### Whisper (port 8110)
- GET /health — Service health check
- POST /transcribe — Audio transcription
- Returns: text, language, duration, result_hash

#### PeerTube Transcoder (port 8220)
- GET /health — Service health check
- POST /transcode — Video transcoding
- Returns: transcoded_url, duration, file_size, result_hash

#### Plugin Registry (port 8109)
- GET /plugins — List all registered plugins
- GET /plugins/{id} — Get specific plugin
- GET /plugins/{id}/offer — Resolve offer from hub chain
- POST /register — Register new plugin
- DELETE /plugins/{id} — Unregister plugin

### Public Endpoints (aitbc3)
- https://aitbc3.aitbc.bubuit.net/whisper/health|transcribe|models
- https://aitbc3.aitbc.bubuit.net/plugin/plugins
- https://aitbc3.aitbc.bubuit.net/peertube/health|transcode

### Nginx Configuration

#### Path Rewriting
```nginx
location /whisper/ {
    rewrite ^/whisper/(.*) /$1 break;
    proxy_pass http://localhost:8110;
}

location /plugin/ {
    rewrite ^/plugin/(.*) /$1 break;
    proxy_pass http://localhost:8109;
}

location /peertube/ {
    rewrite ^/peertube/(.*) /$1 break;
    proxy_pass http://localhost:8220;
}
```

#### Node-Agnostic Config
Server hostname configured via include file, patched by install-nginx-node.sh script.

## 🔧 Breaking Changes

- New CLI commands require hub connectivity for offer discovery
- Escrow release API now accepts optional `job_tx_hash` parameter
- Escrow database schema requires migration (add `job_tx_hash` column)
- Public endpoints require SSL-terminated reverse proxy

## 📊 Migration Guide

### v0.4.4 → v0.4.5

1. **Database Migration**
   ```bash
   # Add job_tx_hash column to Escrow table
   alembic upgrade head
   ```

2. **Install Dependencies**
   ```bash
   # Whisper service
   pip install faster-whisper

   # PeerTube runner
   npm install -g @peertube/peertube-runner
   ```

3. **Configure Nginx**
   ```bash
   # Copy node-agnostic config
   cp /opt/aitbc/deployment/nginx-aitbc.conf /etc/nginx/sites-available/aitbc-proxy.conf

   # Run deploy script to patch hostname
   /opt/aitbc/scripts/setup/install-nginx-node.sh

   # Enable and reload
   ln -s /etc/nginx/sites-available/aitbc-proxy.conf /etc/nginx/sites-enabled/
   nginx -t && systemctl reload nginx
   ```

4. **Start Services**
   ```bash
   systemctl start aitbc-whisper
   systemctl start aitbc-peertube-transcoder
   systemctl start aitbc-plugin
   ```

5. **Register Offers**
   ```bash
   # Whisper offer
   aitbc market software-offer whisper base 0.02 --unit per_audio_min

   # PeerTube offer
   aitbc market software-offer peertube_transcoder default 0.05 --unit per_video_min
   ```

## 🧪 Testing

### Software Marketplace Testing
- ✅ Offer registration via CLI
- ✅ Offer discovery from hub
- ✅ Auto-registration in plugin registry
- ✅ Plugin registry CRUD operations

### Service Execution Testing
- ✅ Whisper transcription with metered escrow
- ✅ PeerTube transcoding with metered escrow
- ✅ Result hash generation and verification
- ✅ On-chain job transaction posting

### Escrow Integration Testing
- ✅ Escrow locking before job execution
- ✅ Actual cost calculation
- ✅ Escrow release with job TX hash
- ✅ Database job_tx_hash storage

### Public Endpoint Testing
- ✅ Nginx path rewriting
- ✅ HTTPS access to services
- ✅ Cross-node service discovery

### Test Coverage
- Software marketplace: 95%
- Service execution: 90%
- Escrow integration: 100%
- Plugin registry: 100%
- Public endpoints: 85%

## 📚 Documentation

- [HOWTO_WHISPER_OFFER.md](../apps/marketplace/HOWTO_WHISPER_OFFER.md)
- [SETUP.md - Software Marketplace](../getting-started/SETUP.md#software-marketplace)
- [SERVICE_PORTS.md](../deployment/SERVICE_PORTS.md)
- [nginx-aitbc.conf](../deployment/nginx-aitbc.conf)
- [install-nginx-node.sh](../scripts/setup/install-nginx-node.sh)

## 🚀 Dependencies

### New Dependencies
- faster-whisper (Whisper transcription)
- @peertube/peertube-runner (VOD transcoding)

### Updated Dependencies
- CLI v0.4.5+
- Blockchain node v0.4.5+
- Escrow service v0.4.5+

## 🔐 Security Considerations

- Result hash provides cryptographic proof of work
- Job TX hash creates immutable audit trail
- Escrow release requires valid job proof
- Public endpoints use SSL termination
- Service endpoints require valid offers

## 📈 Performance Improvements

- **Metered pricing**: Pay only for actual usage
- **On-chain proof**: No need for trusted intermediaries
- **Push-based discovery**: Plugin registry for fast agent lookup
- **Public endpoints**: Direct access without hub proxy

### Performance Metrics
- Transcription latency: <1s for 10s audio (RTX 4000)
- Escrow locking: <100ms
- Job TX posting: <500ms
- Plugin registry lookup: <50ms

## 🎯 Success Criteria

- ✅ Software marketplace functional
- ✅ Offer registration and discovery working
- ✅ Metered escrow payments operational
- ✅ On-chain proof of work verified
- ✅ Plugin registry operational
- ✅ Public endpoints accessible
- ✅ Documentation complete
- ✅ Migration guide tested

## 🚀 Next Steps

### v0.5.1 Planning
- Inter-chain trading (AITBC-to-AITBC)
- External exchange (BTC/ETH → AIT)
- Governance service integration
- Advanced marketplace features

---

*Last Updated: 2026-06-03*
*Version: 0.4.5*
*Status: Released*
