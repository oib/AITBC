# Completed Deployments

This document tracks components that have been successfully deployed and are operational.

## Container Services (aitbc.bubuit.net)

- ✅ **Main Website** - Deployed at https://aitbc.bubuit.net/
  - Static HTML/CSS with responsive design
  - Features overview, architecture, roadmap, platform status
  - Documentation portal integrated

- ✅ **Explorer Web** - Deployed at https://aitbc.bubuit.net/explorer/
  - Full-featured blockchain explorer
  - Mock data with genesis block (height 0) displayed
  - Blocks, transactions, addresses, receipts tracking
  - Mock/live data toggle functionality (live mode backed by Coordinator API)
  - Live API (nginx): `/api/explorer/*`

- ✅ **Marketplace Web** - Deployed at https://aitbc.bubuit.net/marketplace/
  - Vite + TypeScript frontend
  - Offer list, bid form, stats cards
  - Mock data fixtures with API abstraction

- ✅ **Coordinator API** - Deployed in container
  - FastAPI service running on port 8000
  - Health endpoint: `/api/v1/health` returns `{"status":"ok","env":"dev"}`
  - nginx proxy: `/api/` routes to container service (so `/api/v1/*` works)
  - Explorer API (nginx): `/api/explorer/*` → backend `/v1/explorer/*`
  - Users API: `/api/v1/users/*` (compat: `/api/users/*` for Exchange)
  - ZK Applications API: /api/zk/ endpoints for privacy-preserving features

- ✅ **Wallet Daemon** - Deployed in container
  - FastAPI service with encrypted keystore (Argon2id + XChaCha20-Poly1305)
  - REST and JSON-RPC endpoints for wallet management
  - Mock ledger adapter with SQLite backend
  - Running on port 8002, nginx proxy: /wallet/
  - Dependencies: aitbc-sdk, aitbc-crypto, fastapi, uvicorn

- ✅ **Documentation** - Deployed at https://aitbc.bubuit.net/docs/
  - Split documentation for different audiences
  - Miner, client, developer guides
  - API references and technical specs

- ✅ **Trade Exchange** - Deployed at https://aitbc.bubuit.net/Exchange/
  - Bitcoin wallet integration for AITBC purchases
  - User management system with individual wallets
  - QR code generation for payments
  - Real-time payment monitoring
  - Session-based authentication
  - Exchange rate: 1 BTC = 100,000 AITBC

- ✅ **ZK Applications** - Privacy-preserving features deployed
  - Circom compiler v2.2.3 installed
  - ZK circuits compiled (receipt_simple with 300 constraints)
  - Trusted setup ceremony completed (Powers of Tau)
  - Available features:
    - Identity commitments
    - Stealth addresses
    - Private receipt attestation
    - Group membership proofs
    - Private bidding
    - Computation proofs
  - API endpoints: /api/zk/

## Host Services (GPU Access)

- ✅ **Blockchain Node** - Running on host
  - SQLModel-based blockchain with PoA consensus
  - RPC API on port 9080 (proxied via /rpc/)
  - Mock coordinator on port 8090 (proxied via /v1/)
  - Devnet scripts and observability hooks

## Infrastructure

- ✅ **Incus Container** - 'aitbc' container deployed
  - RAID1 configuration for data redundancy
  - nginx reverse proxy for all web services
  - Bridge networking (10.1.223.1 gateway)

- ✅ **nginx Configuration** - All routes configured
  - /explorer/ → Explorer Web
  - /marketplace/ → Marketplace Web  
  - /api/ → Coordinator API (container)
  - /api/v1/ → Coordinator API (container)
  - /api/explorer/ → Explorer API (container)
  - /api/users/ → Users API (container, Exchange compatibility)
  - /api/zk/ → ZK Applications API (container)
  - /rpc/ → Blockchain RPC (host)
  - /v1/ → Mock Coordinator (host)
  - /wallet/ → Wallet Daemon (container)
  - /docs/ → Documentation portal

- ✅ **SSL/HTTPS** - Configured and working
  - All services accessible via https://aitbc.bubuit.net/
  - Proper security headers implemented

- ✅ **DNS Resolution** - Fully operational
  - All endpoints accessible via domain name
  - SSL certificates properly configured

## Deployment Architecture

- **Container Services**: Public web access, no GPU required
  - Website, Explorer, Marketplace, Coordinator API, Wallet Daemon, Docs, ZK Apps
- **Host Services**: GPU access required, private network
  - Blockchain Node, Mining operations
- **nginx Proxy**: Routes requests between container and host
  - Seamless user experience across all services

## Current Status

**Production Ready**: All core services deployed and operational
- ✅ 8 container services running (including ZK Applications)
- ✅ 1 host service running  
- ✅ Complete nginx proxy configuration
- ✅ SSL/HTTPS fully configured
- ✅ DNS resolution working
- ✅ Trade Exchange with Bitcoin integration
- ✅ Zero-Knowledge proof capabilities enabled

## Remaining Tasks

- Fix full Coordinator API codebase import issues (low priority)
- Fix Blockchain Node SQLModel/SQLAlchemy compatibility issues (low priority)
- Configure additional monitoring and observability
- Set up automated backup procedures
