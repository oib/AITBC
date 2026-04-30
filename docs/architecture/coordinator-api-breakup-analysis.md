# Coordinator-API Monolith Breakup Analysis

## Overview

This document analyzes the coordinator-api monolith and proposes a bounded-context breakup strategy.

## Current Structure

The coordinator-api monolith contains:
- **59 routers** in `apps/coordinator-api/src/app/routers/`
- **101 services** in `apps/coordinator-api/src/app/services/`
- **33 domain modules** in `apps/coordinator-api/src/app/domain/`
- Approximately **80K lines of code**

## Identified Bounded Contexts

### 1. Agent Service (agent.aitbc.local)
**Routers:**
- agent_creativity.py
- agent_identity.py
- agent_integration_router.py
- agent_performance.py
- agent_router.py
- agent_security_router.py

**Responsibilities:**
- Agent registration and identity management
- Agent performance tracking
- Agent security and authentication
- Agent creativity metrics
- Agent integration coordination

**Estimated Size:** ~140K lines

### 2. Marketplace Service (marketplace.aitbc.local)
**Routers:**
- marketplace.py
- marketplace_enhanced.py
- marketplace_enhanced_app.py
- marketplace_enhanced_health.py
- marketplace_enhanced_simple.py
- marketplace_gpu.py
- marketplace_offers.py
- marketplace_performance.py
- global_marketplace.py
- global_marketplace_integration.py

**Responsibilities:**
- GPU marketplace listings
- Marketplace offers and pricing
- Marketplace performance monitoring
- Global marketplace integration

**Estimated Size:** ~130K lines

### 3. Governance Service (governance.aitbc.local)
**Routers:**
- governance.py
- governance_enhanced.py
- staking.py

**Responsibilities:**
- DAO governance
- Proposal management
- Voting mechanisms
- Staking operations

**Estimated Size:** ~50K lines

### 4. Trading Service (trading.aitbc.local)
**Routers:**
- trading.py
- exchange.py
- settlement.py
- payments.py

**Responsibilities:**
- Trading operations
- Exchange integration
- Cross-chain settlements
- Payment processing

**Estimated Size:** ~60K lines

### 5. GPU Service (gpu.aitbc.local)
**Routers:**
- edge_gpu.py
- gpu_multimodal_health.py
- miner.py

**Responsibilities:**
- GPU resource management
- GPU health monitoring
- Mining operations

**Estimated Size:** ~15K lines

### 6. Cross-Chain Service (crosschain.aitbc.local)
**Routers:**
- cross_chain_integration.py

**Responsibilities:**
- Cross-chain bridge operations
- Cross-chain transaction management

**Estimated Size:** ~25K lines

### 7. Analytics Service (analytics.aitbc.local)
**Routers:**
- analytics.py
- monitoring_dashboard.py
- web_vitals.py

**Responsibilities:**
- Performance analytics
- Monitoring dashboards
- Web vitals collection

**Estimated Size:** ~45K lines

### 8. Platform Service (platform.aitbc.local)
**Routers:**
- admin.py
- client.py
- developer_platform.py
- partners.py
- registry.py
- users.py

**Responsibilities:**
- Platform administration
- Client management
- Developer platform
- Partner management
- Service registry
- User management

**Estimated Size:** ~70K lines

### 9. AI/ML Service (ai.aitbc.local)
**Routers:**
- ml_zk_proofs.py
- zk_applications.py
- adaptive_learning_health.py
- modality_optimization_health.py
- multimodal_health.py
- openclaw_enhanced_health.py

**Responsibilities:**
- ZK proof generation
- AI/ML model operations
- Health monitoring for AI services

**Estimated Size:** ~40K lines

## Shared Dependencies

### Shared Utilities to Extract to aitbc-core:
1. Database session management
2. Authentication middleware
3. Rate limiting middleware
4. Logging configuration
5. Common exception classes
6. API response models
7. Utility functions

### Shared Services:
1. Blockchain RPC client
2. Encryption service
3. Cache management
4. Event bus/message queue

## Proposed Breakup Strategy

### Phase 1: Extract Shared Utilities (Week 1-2)
1. Identify and extract common utilities to aitbc-core
2. Create shared middleware package
3. Update coordinator-api to use shared utilities

### Phase 2: Extract GPU Service (Week 2-3)
1. Create new FastAPI app for GPU service
2. Extract GPU-related routers and services
3. Create systemd service
4. Update routing

### Phase 3: Extract Marketplace Service (Week 3-4)
1. Create new FastAPI app for marketplace service
2. Extract marketplace-related routers and services
3. Create systemd service
4. Update routing

### Phase 4: Extract Agent Service (Week 4-5)
1. Create new FastAPI app for agent service
2. Extract agent-related routers and services
3. Create systemd service
4. Update routing

### Phase 5: Extract Trading Service (Week 5-6)
1. Create new FastAPI app for trading service
2. Extract trading-related routers and services
3. Create systemd service
4. Update routing

### Phase 6: Extract Governance Service (Week 6-7)
1. Create new FastAPI app for governance service
2. Extract governance-related routers and services
3. Create systemd service
4. Update routing

### Phase 7: Extract Remaining Services (Week 7-8)
1. Extract remaining services (analytics, platform, AI/ML, cross-chain)
2. Create API gateway or service discovery
3. Update client SDKs
4. Performance testing

## API Gateway Considerations

### Options:
1. **Nginx reverse proxy** - Simple, well-understood
2. **Kubernetes Ingress** - If using Kubernetes
3. **FastAPI gateway** - Custom API gateway
4. **Traefik** - Dynamic routing with service discovery

### Recommendation:
Start with Nginx reverse proxy for simplicity, migrate to more sophisticated solution if needed.

## Database Considerations

### Options:
1. **Shared database** - All services share the same database (simpler migration)
2. **Separate databases** - Each service has its own database (better isolation)

### Recommendation:
Start with shared database for easier migration, consider separating databases in future phases.

## Success Metrics

1. Reduced coordinator-api codebase by 70%
2. Each microservice can be deployed independently
3. Service latency < 100ms for 95th percentile
4. No regression in existing functionality
5. Improved code maintainability and developer productivity

## Next Steps

1. Review and approve this breakup strategy
2. Create detailed implementation plan for Phase 1
3. Begin extracting shared utilities to aitbc-core
