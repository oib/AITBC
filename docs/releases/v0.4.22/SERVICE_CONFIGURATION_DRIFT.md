# Service Configuration Drift - v0.4.22

**Release**: v0.4.22
**Date**: 2026-06-15
**Status**: ✅ Complete

## Overview

AITBC v0.4.22 fixed service configuration drift issues across the codebase.

## Configuration Issues Fixed

### 1. RPC Port Inconsistencies (8006 vs 8202)
- blockchain-node/config.py: rpc_bind_port default 8080 → 8202
- edge/config.py: blockchain_rpc_port default 8006 → 8202
- wallet/settings.py: blockchain_rpc_url default localhost:8006 → localhost:8202
- blockchain-event-bridge/config.py: blockchain_rpc_url default localhost:8006 → localhost:8202

### 2. Port Conflict (hermes vs edge both on 8103)
- edge/config.py: api_port default 8103 → 8111
- hermes/aitbc-hermes-wrapper.py: hardcoded --port 8103 → read HERMES_PORT env var
- hermes/aitbc-hermes.service: added explicit HERMES_PORT=8103 and HERMES_BIND_HOST=127.0.0.1
- coordinator-api/islands_proxy.py: EDGE_API_BASE_URL port 8103 → 8111

### 3. Bind Host Inconsistencies (0.0.0.0 on internal services)
- trading/main.py: uvicorn.run fallback 0.0.0.0 → 127.0.0.1
- governance/main.py: uvicorn.run fallback 0.0.0.0 → 127.0.0.1

## Results

- ✅ 9 configuration issues resolved
- ✅ RPC ports unified: All services now use 8202 for blockchain RPC
- ✅ Port conflicts resolved: Edge (8111) and Hermes (8103) properly separated
- ✅ Bind hosts secured: Internal services bind to 127.0.0.1

---

*Last Updated: 2026-06-15*
