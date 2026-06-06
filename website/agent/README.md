# AITBC Agent API

Machine-readable API endpoints for autonomous agents to discover and interact with the AITBC network.

## Overview

This directory provides agent-first access to the AITBC blockchain network. All endpoints return structured JSON for programmatic consumption.

## Quick Start

```bash
# 1. Discover the network
curl -s http://aitbc:8006/agent/discovery.json | jq .

# 2. Get island information
curl -s http://aitbc:8006/agent/islands.json | jq '.islands[]'

# 3. Get chain information
curl -s http://aitbc:8006/agent/chains.json | jq '.chains[]'

# 4. Get join instructions
curl -s http://aitbc:8006/agent/join/ait-mainnet.json | jq '.how_to_join'
```

## Endpoints

### Discovery

| Endpoint | Description | Cache |
|----------|-------------|-------|
| `/agent/discovery.json` | Complete network information | 60s |
| `/agent/islands.json` | All islands with status | 30s |
| `/agent/chains.json` | Chain configurations | 60s |

### Join Network

| Endpoint | Description | Cache |
|----------|-------------|-------|
| `/agent/join/ait-mainnet.json` | Join instructions for mainnet | 1h |
| `/agent/join/ait-testnet.json` | Join instructions for testnet | 1h |

### API Documentation

| Endpoint | Description | Cache |
|----------|-------------|-------|
| `/agent/openapi.json` | OpenAPI 3.0 specification | 1h |
| `/agent/health` | Health check endpoint | No cache |

### RPC Endpoints

| Endpoint | Description |
|----------|-------------|
| `/rpc/head` | Current head block |
| `/rpc/info` | Chain information |
| `/rpc/islands` | Island memberships |
| `/rpc/islands/{id}` | Island details |

## CORS Support

All `/agent/` and `/rpc/` endpoints include CORS headers for cross-origin access:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Accept
```

## Agent Landing Page

Human-readable documentation is available at:
- http://aitbc:8006/agent/

## Network Architecture

### Islands

- **ait-mainnet-island**: Production chain (hub: aitbc)
- **ait-testnet-island**: Test chain (hub: aitbc1)

### Nodes

| Node | Role | Chains | Island |
|------|------|--------|--------|
| aitbc | Hub | ait-mainnet | ait-mainnet-island |
| aitbc | Follower | ait-testnet | ait-testnet-island |
| aitbc1 | Hub | ait-testnet | ait-testnet-island |
| aitbc1 | Follower | ait-mainnet | ait-mainnet-island |

## Configuration Templates

See `/agent/join/*.json` files for complete configuration templates including:
- Environment variables
- P2P peer lists
- RPC endpoints
- Step-by-step join instructions

## Version

- API Version: 1.0.0
- Format Version: 1.0
- Last Updated: 2026-05-19

## For Humans

The main website is available at the root: http://aitbc:8006/
