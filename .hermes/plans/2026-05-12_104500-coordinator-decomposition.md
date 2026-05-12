
# Coordinator-API Decomposition Plan

## Current State
- **1 monolith**: apps/coordinator-api/src/app/
  - 89 service files, 46,594 LOC
  - 53 routers
  - 51 files over 500 LOC
  - Largest: agent_integration.py (1,159 LOC)

## Decomposition Strategy: Bounded Contexts

Based on domain analysis, split into 7 microservices:

1. **agent-management** (agent lifecycle, performance, communication)
2. **blockchain** (chain operations, transactions, smart contracts)
3. **computing** (GPU, resources, marketplace for compute)
4. **enterprise** (integration, scalability, compliance)
5. **identity** (authentication, authorization, agents identity)
6. **payment** (billing, transactions, financial operations)
7. **ai-models** (AI services, RL, multi-modal fusion)

Each will be a separate FastAPI app with:
- Its own routers/, services/, models/
- Shared libraries: app.core.config, app.core.logging, app.core.database
- Independent systemd service
- Clear API boundaries

## Implementation Phases

### Phase 1: Infrastructure Setup (Week 1-2)
- Create apps/ directory structure: agent-management/, blockchain/, etc.
- Create shared core library: apps/coordinator-api/src/app/core/
- Extract common config, logging, DB session, exceptions
- Update pyproject.toml to support multiple packages

### Phase 2: Extract Agent Management (Week 2-3)
- Move agent_*.py, agent_service_marketplace.py -> agent-management
- Move agent_communication.py, agent_performance_service.py -> agent-management
- Create new systemd service for agent-management
- Update reverse proxy (nginx) routes

### Phase 3: Extract Blockchain (Week 3-4)
- Move blockchain_context.py, contract_service.py, transaction_service.py -> blockchain
- Move escrow.py, persistent_spending_tracker.py, etc.
- Create blockchain systemd service

### Phase 4: Extract Enterprise (Week 4-5)
- Move enterprise_integration.py, compliance_engine.py, certification related -> enterprise
- Create enterprise systemd service

### Phase 5: Extract Identity (Week 5-6)
- Move auth/identity service files -> identity
- Create identity systemd service

### Phase 6: Extract AI Models (Week 6-7)
- Move advanced_*.py, multi_modal_fusion, ai verification -> ai-models
- Create ai-models systemd service

### Phase 7: Extract Computing & Payment (Week 7-8)
- Move gpu, resource, payment services to their own packages

### Phase 8: Final Integration (Week 8-9)
- Update all clients to use new service endpoints
- Test inter-service communication
- Update documentation
- Deprecate old monolith

## Files to Create/Modify

### New shared core (apps/coordinator-api/src/app/core/)
- config.py (extracted from existing config.py)
- logging.py (centralized logger setup)
- database.py (SQLAlchemy session, Base)
- exceptions.py (common exceptions)
- security.py (auth dependencies)

### New service apps (47 directories total)
Each: apps/<service>/src/app/{routers,services,models,main.py}

### Modified files
- Root pyproject.toml: add service packages
- Systemd: add 7 new .service files
- Nginx config: new upstream blocks
- Docker compose: add 7 new containers
- Monitoring: new service endpoints for health

## Rollback Plan
- Keep original monolith running alongside new services during transition
- Use feature flags to route traffic
- Comprehensive integration tests before cutover

## Success Criteria
- Each service < 3,000 LOC (target 1,500)
- Each service independently deployable
- API contracts stable and documented
- CI/CD per service
