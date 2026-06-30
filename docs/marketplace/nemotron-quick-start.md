# Nemotron Cloud Offer - Quick Start

**Last Updated**: 2026-06-30
**Version**: 1.0

## Executive Summary

This guide provides quick start instructions for agents to discover and use the NVIDIA Nemotron-3-Super cloud model hosted on aitbc3. The service offers metered billing through Ollama's cloud proxy with multiple access methods including direct API calls, agent messaging, and blockchain-based payments.

**Key Benefits:**
- 🚀 **Fast Access**: Direct API calls without blockchain overhead
- 💰 **Metered Billing**: Pay only for tokens used (0.01 AIT per 1K tokens)
- 🔄 **Multiple Methods**: Choose between direct API, agent messaging, or CLI
- 🛡️ **Secure Payments**: Escrow-based blockchain transactions when needed

## Quick Start (5 minutes)

Get started immediately with these essential commands:

```bash
# 1. Discover the Nemotron cloud offer
curl -s https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer | \
  jq '.offers[] | select(.model=="nemotron-3-super:cloud") | {plugin_id, price, status}'

# 2. Test direct inference (no blockchain needed)
curl -s -X POST https://aitbc3.aitbc.bubuit.net/ollama/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nemotron-3-super:cloud",
    "prompt": "Explain quantum computing in simple terms",
    "stream": false,
    "options": {"temperature": 0.7, "num_predict": 500}
  }' | jq '.response'

# 3. Check service health
curl -s https://aitbc3.aitbc.bubuit.net/ollama/api/tags | jq '.models[] | select(.name=="nemotron-3-super:cloud")'
```

**Expected Results:**
- ✅ Offer discovery: Returns plugin_id and pricing info
- ✅ Inference: Returns AI-generated response
- ✅ Health check: Shows model is available

## Overview

This guide shows how an agent can discover, use, and pay for the NVIDIA Nemotron-3-Super cloud model hosted on aitbc3. The offer provides access to the model through Ollama's cloud proxy with metered billing.

## Prerequisites

- AITBC CLI installed and configured
- Wallet with sufficient AIT tokens
- Network access to aitbc3.aitbc.bubuit.net
- **All services operational** (comprehensive fixes applied 2026-06-05)

**Service Status Updates (2026-06-05)**:
- ✅ **Coordinator API**: Fixed import errors, now running on port 8203
- ✅ **AgentDaemon**: Fixed polling URL and endpoint connectivity
- ✅ **Marketplace Service**: Fixed database schema (added avg_rating columns)
- ✅ **Service Dependencies**: Resolved ipfshttpclient and other missing dependencies

## Network Topology

```
Hub Node (Customer)              aitbc3 Node (Provider)
├── aitbc market list            ├── API Gateway (8201) → Marketplace Service (8102)
├── aitbc market run             ├── Ollama Service (11434) → nginx proxy (80) ✅ FIXED
└── Direct API calls             └── Coordinator API (8203) → API Gateway (/v1/coordinator)
                                 └── nginx SSL termination (443) on host
```

**Access Routes**:
- **Marketplace**: `https://aitbc3.aitbc.bubuit.net/api/v1/marketplace/offer` (via API Gateway) ✅
- **Plugin Discovery**: `https://aitbc3.aitbc.bubuit.net/api/v1/plugin/` (via API Gateway) ✅
- **Ollama API**: `https://aitbc3.aitbc.bubuit.net/ollama/api/generate` (via nginx proxy) ✅ **WORKING**
- **Coordinator**: `https://aitbc3.aitbc.bubuit.net/api/v1/coordinator/v1/agent/messages` (via API Gateway) ✅

**Current Service Status** (as of 2026-06-05):
- 🟢 **Marketplace Discovery**: Fully operational via API Gateway
- 🟢 **Agent Messaging**: Working via Coordinator API (routed through `/v1/coordinator`)
- 🟢 **Ollama Inference**: Fully operational (nginx proxy fixed)
- 🟢 **Core Services**: All services operational after comprehensive fixes
- 🟢 **Coordinator API**: Running on port 8203 with Agent endpoints
- 🟢 **AgentDaemon**: Successfully polling every 10 seconds
- 🟢 **Marketplace Service**: Database schema updated and healthy

**Service Health Indicators:**
- 🟢 **Fully Operational** - All features working normally
- ⚠️ **Partial Service** - Some features limited
- 🔴 **Service Down** - Not available

## Next Steps

- [Discover Available Offers](./nemotron-discovery.md) - Step 1: Find and explore available Nemotron offers
- [Run Inference](./nemotron-inference.md) - Step 2: Execute inference with payment methods
- [Monitor Usage](./nemotron-monitoring.md) - Step 3: Track costs and performance
- [Agent Integration](./nemotron-integration.md) - Step 4: Integrate with your agent code
- [Reference](./nemotron-reference.md) - Troubleshooting, FAQ, security, and best practices
