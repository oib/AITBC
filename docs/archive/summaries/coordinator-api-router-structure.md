# Coordinator-API Router Structure Documentation

This document details the router structure of the legacy coordinator-api to inform the microservices migration.

## Router Overview

The coordinator-api has approximately 60+ routers covering various domains. This document categorizes them by functionality and lists their key endpoints.

## Core Routers

### Miner Operations (`miner.py`)
**Purpose:** GPU miner registration, heartbeat, job polling, and result submission
**Status:** MIGRATION PENDING - Should be migrated to GPU Service

**Endpoints:**
- POST `/miners/register` - Register or update miner
- POST `/miners/heartbeat` - Send miner heartbeat
- POST `/miners/poll` - Poll for next job
- POST `/miners/{job_id}/result` - Submit job result
- POST `/miners/{job_id}/fail` - Submit job failure
- POST `/miners/{miner_id}/jobs` - List jobs for a miner
- POST `/miners/{miner_id}/earnings` - Get miner earnings
- PUT `/miners/{miner_id}/capabilities` - Update miner capabilities
- DELETE `/miners/{miner_id}` - Deregister miner

### Client Operations (`client.py`)
**Purpose:** Job submission, status tracking, and result retrieval
**Status:** MIGRATION PENDING - Should be migrated to AI Service

**Endpoints:**
- POST `/jobs` - Submit a job
- GET `/jobs/{job_id}` - Get job status
- GET `/jobs/{job_id}/result` - Get job result
- POST `/jobs/{job_id}/cancel` - Cancel job
- GET `/jobs/{job_id}/receipt` - Get latest signed receipt
- GET `/jobs/{job_id}/receipts` - List signed receipts
- GET `/jobs` - List jobs with filtering
- GET `/jobs/history` - Get job history
- GET `/blocks` - Get blockchain blocks
- POST `/agents/networks` - Create agent network
- GET `/agents/executions/{execution_id}/receipt` - Get agent execution receipt

### Explorer Operations (`explorer.py`)
**Purpose:** Blockchain explorer for blocks, transactions, addresses, receipts
**Status:** MIGRATION PENDING - Should be migrated to Explorer Service

**Endpoints:**
- GET `/blocks` - List recent blocks
- GET `/blocks/{block_id}` - Get block details
- GET `/addresses` - List address summaries
- GET `/receipts` - List job receipts
- GET `/transactions/{tx_hash}` - Get transaction details by hash

### Agent Router (`agent_router.py`)
**Purpose:** AI agent workflow management and execution
**Status:** MIGRATION PENDING - Should be migrated to AI Service

**Endpoints:**
- POST `/workflows` - Create AI agent workflow
- GET `/workflows` - List workflows
- GET `/workflows/{workflow_id}` - Get workflow details
- PUT `/workflows/{workflow_id}` - Update workflow
- DELETE `/workflows/{workflow_id}` - Delete workflow
- POST `/workflows/{workflow_id}/execute` - Execute workflow
- GET `/executions/{execution_id}/status` - Get execution status
- GET `/executions` - List executions
- POST `/executions/{execution_id}/cancel` - Cancel execution
- GET `/executions/{execution_id}/logs` - Get execution logs
- GET `/test` - Test endpoint
- POST `/networks` - Create network
- GET `/executions/{execution_id}/receipt` - Get execution receipt

## Marketplace Routers

### GPU Marketplace (`marketplace_gpu.py`)
**Purpose:** GPU registration, listing, booking, and pricing
**Status:** PARTIALLY MIGRATED - Core functionality migrated to GPU/Marketplace Services

**Endpoints:**
- POST `/marketplace/gpu/register` - Register GPU for marketplace
- GET `/marketplace/gpu/list` - List available GPUs
- GET `/marketplace/gpu/{gpu_id}` - Get GPU details
- POST `/marketplace/gpu/purchase` - Purchase GPU
- POST `/marketplace/gpu/sell` - Sell GPU
- POST `/marketplace/gpu/{gpu_id}/book` - Book GPU
- POST `/marketplace/gpu/{gpu_id}/release` - Release GPU
- POST `/marketplace/gpu/{gpu_id}/confirm` - Confirm booking
- POST `/tasks/ollama` - Submit Ollama task
- POST `/payments/send` - Send payment
- DELETE `/marketplace/gpu/{gpu_id}` - Remove GPU
- GET `/marketplace/gpu/{gpu_id}/reviews` - Get GPU reviews
- POST `/marketplace/gpu/{gpu_id}/reviews` - Add GPU review
- GET `/marketplace/orders` - Get marketplace orders
- GET `/marketplace/pricing/{model}` - Get pricing for model
- POST `/marketplace/gpu/bid` - Bid on GPU

### Marketplace (`marketplace.py`)
**Purpose:** Basic marketplace operations
**Status:** MIGRATED - Functionality moved to Marketplace Service

### Marketplace Offers (`marketplace_offers.py`)
**Purpose:** Marketplace offer management
**Status:** MIGRATED - Functionality moved to Marketplace Service

### Global Marketplace (`global_marketplace.py`)
**Purpose:** Cross-chain marketplace operations
**Status:** MIGRATION PENDING - Should be migrated to Marketplace Service

### Global Marketplace Integration (`global_marketplace_integration.py`)
**Purpose:** Integration with external marketplaces
**Status:** MIGRATION PENDING - Should be migrated to Marketplace Service

## Governance Routers

### Governance (`governance.py`)
**Purpose:** Basic governance operations
**Status:** MIGRATED - Functionality moved to Governance Service

### Governance Enhanced (`governance_enhanced.py`)
**Purpose:** Enhanced governance features
**Status:** MIGRATION PENDING - Should be migrated to Governance Service

## Trading Routers

### Trading (`trading.py`)
**Purpose:** Trading operations
**Status:** MIGRATED - Functionality moved to Trading Service

### Exchange (`exchange.py`)
**Purpose:** Exchange operations
**Status:** MIGRATION PENDING - Should be migrated to Trading Service

### Settlement (`settlement.py`)
**Purpose:** Settlement operations
**Status:** MIGRATION PENDING - Should be migrated to Trading Service

## Agent Identity Routers

### Agent Identity (`agent_identity.py`)
**Purpose:** Agent identity management
**Status:** MIGRATION PENDING - Should be migrated to dedicated Agent Service

### Agent Security Router (`agent_security_router.py`)
**Purpose:** Agent security operations
**Status:** MIGRATION PENDING - Should be migrated to dedicated Agent Service

### Agent Integration Router (`agent_integration_router.py`)
**Purpose:** Agent integration operations
**Status:** MIGRATION PENDING - Should be migrated to dedicated Agent Service

### Agent Performance (`agent_performance.py`)
**Purpose:** Agent performance tracking
**Status:** MIGRATION PENDING - Should be migrated to dedicated Agent Service

### Agent Creativity (`agent_creativity.py`)
**Purpose:** Agent creativity metrics
**Status:** MIGRATION PENDING - Should be migrated to dedicated Agent Service

## Blockchain Routers

### Blockchain (`blockchain.py`)
**Purpose:** Basic blockchain operations
**Status:** MIGRATION PENDING - Should be migrated to Blockchain Service

### Cross Chain Integration (`cross_chain_integration.py`)
**Purpose:** Cross-chain operations
**Status:** MIGRATION PENDING - Should be migrated to Blockchain Service

## Payment Routers

### Payments (`payments.py`)
**Purpose:** Payment operations
**Status:** MIGRATION PENDING - Should be migrated to Payment Service

### Staking (`staking.py`)
**Purpose:** Staking operations
**Status:** MIGRATION PENDING - Should be migrated to Payment Service

### Rewards (`rewards.py`)
**Purpose:** Rewards distribution
**Status:** MIGRATION PENDING - Should be migrated to Payment Service

## Developer Routers

### Developer Platform (`developer_platform.py`)
**Purpose:** Developer platform operations
**Status:** MIGRATION PENDING - Should be migrated to Developer Service

### Registry (`registry.py`)
**Purpose:** Registry operations
**Status:** MIGRATION PENDING - Should be migrated to Developer Service

### Certification (`certification.py`)
**Purpose:** Certification operations
**Status:** MIGRATION PENDING - Should be migrated to Developer Service

## Monitoring Routers

### Monitoring Dashboard (`monitoring_dashboard.py`)
**Purpose:** Monitoring dashboard
**Status:** MIGRATION PENDING - Should be migrated to Monitoring Service

### Web Vitals (`web_vitals.py`)
**Purpose:** Web vitals tracking
**Status:** MIGRATION PENDING - Should be migrated to Monitoring Service

### Analytics (`analytics.py`)
**Purpose:** Analytics operations
**Status:** MIGRATION PENDING - Should be migrated to Analytics Service

## OpenClaw Routers

### OpenClaw Enhanced (`openclaw_enhanced.py`)
**Purpose:** OpenClaw operations
**Status:** MIGRATION PENDING - Should be migrated to OpenClaw Service

### OpenClaw Enhanced Simple (`openclaw_enhanced_simple.py`)
**Purpose:** Simplified OpenClaw operations
**Status:** MIGRATION PENDING - Should be migrated to OpenClaw Service

## Multimodal Routers

### Multimodal Health (`multimodal_health.py`)
**Purpose:** Multimodal health checks
**Status:** MIGRATION PENDING - Should be migrated to AI Service

### GPU Multimodal Health (`gpu_multimodal_health.py`)
**Purpose:** GPU multimodal health checks
**Status:** MIGRATION PENDING - Should be migrated to GPU Service

### Modality Optimization Health (`modality_optimization_health.py`)
**Purpose:** Modality optimization health checks
**Status:** MIGRATION PENDING - Should be migrated to AI Service

### ML ZK Proofs (`ml_zk_proofs.py`)
**Purpose:** ML zero-knowledge proofs
**Status:** MIGRATION PENDING - Should be migrated to AI Service

### ZK Applications (`zk_applications.py`)
**Purpose:** Zero-knowledge applications
**Status:** MIGRATION PENDING - Should be migrated to AI Service

## Other Routers

### Admin (`admin.py`)
**Purpose:** Administrative operations
**Status:** MIGRATION PENDING - Should be migrated to Admin Service

### Users (`users.py`)
**Purpose:** User management
**Status:** MIGRATION PENDING - Should be migrated to User Service

### Services (`services.py`)
**Purpose:** Service management
**Status:** MIGRATION PENDING - Should be migrated to Service Registry

### Bounty (`bounty.py`)
**Purpose:** Bounty operations
**Status:** MIGRATION PENDING - Should be migrated to Marketplace Service

### Community (`community.py`)
**Purpose:** Community operations
**Status:** MIGRATION PENDING - Should be migrated to Community Service

### Confidential (`confidential.py`)
**Purpose:** Confidential operations
**Status:** MIGRATION PENDING - Should be migrated to Security Service

### Dynamic Pricing (`dynamic_pricing.py`)
**Purpose:** Dynamic pricing operations
**Status:** MIGRATION PENDING - Should be migrated to Marketplace Service

### Ecosystem Dashboard (`ecosystem_dashboard.py`)
**Purpose:** Ecosystem dashboard
**Status:** MIGRATION PENDING - Should be migrated to Monitoring Service

### Marketplace Enhanced (`marketplace_enhanced.py`)
**Purpose:** Enhanced marketplace operations
**Status:** MIGRATION PENDING - Should be migrated to Marketplace Service

### Marketplace Enhanced Simple (`marketplace_enhanced_simple.py`)
**Purpose:** Simplified enhanced marketplace operations
**Status:** MIGRATION PENDING - Should be migrated to Marketplace Service

### Marketplace Performance (`marketplace_performance.py`)
**Purpose:** Marketplace performance metrics
**Status:** MIGRATION PENDING - Should be migrated to Marketplace Service

### Partners (`partners.py`)
**Purpose:** Partner management
**Status:** MIGRATION PENDING - Should be migrated to Partnership Service

### Reputation (`reputation.py`)
**Purpose:** Reputation management
**Status:** MIGRATION PENDING - Should be migrated to Reputation Service

### Cache Management (`cache_management.py`)
**Purpose:** Cache management
**Status:** MIGRATION PENDING - Should be migrated to Infrastructure Service

### Adaptive Learning Health (`adaptive_learning_health.py`)
**Purpose:** Adaptive learning health checks
**Status:** MIGRATION PENDING - Should be migrated to AI Service

## Migration Priority

### High Priority (Core Operations)
1. **Miner Operations** - Critical for GPU provider functionality
2. **Client Operations** - Critical for job submission and tracking
3. **Explorer Operations** - Critical for blockchain visibility

### Medium Priority (Enhanced Features)
4. **Agent Router** - Important for AI agent management
5. **Governance Enhanced** - Important for DAO operations
6. **Trading/Exchange** - Important for marketplace liquidity

### Low Priority (Specialized Features)
7. **OpenClaw Routers** - Specialized feature
8. **Multimodal Routers** - Specialized AI features
9. **Developer Platform** - Developer-facing features

## Recommended Microservices

Based on the router analysis, the following microservices should be created:

1. **Miner Service** - Miner operations
2. **AI Service** - Client operations, Agent router, Multimodal operations
3. **Explorer Service** - Explorer operations, Blockchain operations
4. **Payment Service** - Payments, Staking, Rewards
5. **Agent Service** - Agent identity, security, integration, performance
6. **Blockchain Service** - Blockchain, Cross-chain integration
7. **Developer Service** - Developer platform, Registry, Certification
8. **Monitoring Service** - Monitoring dashboard, Analytics, Ecosystem dashboard
9. **OpenClaw Service** - All OpenClaw operations
10. **Admin Service** - Admin, Users
11. **Community Service** - Community, Partners
12. **Security Service** - Confidential operations
13. **Reputation Service** - Reputation management

## Dependencies

Many routers have dependencies on shared services and databases:
- Shared database models in `coordinator-api/src/app/domain/`
- Shared schemas in `coordinator-api/src/app/schemas/`
- Shared services in `coordinator-api/src/app/services/`

These dependencies will need to be refactored as part of the microservices migration.

## Conclusion

The coordinator-api contains a large number of routers covering diverse functionality. A phased migration approach is recommended, starting with high-priority core operations (Miner, Client, Explorer) and gradually migrating other functionality as needed.
