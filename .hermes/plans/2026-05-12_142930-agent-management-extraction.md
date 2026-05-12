# Agent-Management Service Extraction Plan

## Overview

Extract the agent-related functionality from the coordinator-api monolith into a standalone microservice while maintaining operational continuity.

## Current State

**Monolith:** `apps/coordinator-api/src/app/`
- Services: 46,594 LOC across 89 files
- Domain layer: `domain/` contains all business entities (Agent, AgentExecution, AgentStatus, etc.)
- Target agent files to extract: **18 files** (6 routers, 12 services)
- Largest files: agent_service.py (1,159 LOC), agent_integration.py (1,117 LOC), agent_communication.py (988 LOC)

## Bounded Context: Agent-Management

**Responsibility:** AI agent lifecycle, orchestration, performance tracking, security, and marketplace registry.

**In-Scope Files:**

### Services (12)
```
services/agent_service.py (1,159 LOC)
services/agent_integration.py (1,117 LOC)
services/agent_communication.py (988 LOC)
services/agent_orchestrator.py
services/agent_performance_service.py
services/agent_security.py
services/agent_portfolio_manager.py
services/agent_service_marketplace.py
services/advanced_rl/agents.py (+ sub-agents: ppo_agent.py, rainbow_dqn_agent.py, sac_agent.py)
```

### Routers (6)
```
routers/agent_router.py
routers/agent_integration_router.py
routers/agent_performance.py
routers/agent_creativity.py
routers/agent_security_router.py
routers/services.py (agent services listing endpoint)
```

## Critical Dependencies

1. **Domain Layer** (`app.domain`)
   - All agent services import from `..domain.agent` (AgentExecution, AgentStatus, AIAgentWorkflow, etc.)
   - Solution: Keep domain/ in monolith for now; new service imports via a **shared-domain package** to be created
   - Create `apps/shared-domain/src/app/domain/` as a symlink or copy that both services can import
   - Long-term: Extract entire domain layer to shared-domain package

2. **aitbc package**
   - Already available as root package. Use directly.

3. **SQLModel/SQLAlchemy**
   - Already in dependencies via root pyproject.toml

4. **Other monolith services**
   - Some routers may call agent endpoints. These will need to be updated to use HTTP client to new service (Phase 3 internal routing via nginx)

## Implementation Steps

### Step 0: Prepare Shared Domain Package (Prerequisite)
- Create `apps/shared-domain/src/app/domain/`
- Copy all files from coordinator-api's `domain/` EXCEPT non-agent ones if desired
- Or simpler: symlink entire domain directory: `ln -s ../../coordinator-api/src/app/domain apps/shared-domain/src/app/`
- Update imports in new service to use `from shared-domain.app.domain.agent import ...`
- Add `shared-domain` to pyproject.toml dependencies in consuming services

**Recommendation:** Use symlink for rapid iteration, then formalize package later.

### Step 1: Create agent-management Service Skeleton
```
apps/agent-management/
├── pyproject.toml
├── README.md
└── src/
    └── app/
        ├── __init__.py
        ├── main.py
        ├── core/
        │   ├── __init__.py
        │   ├── config.py (import from shared-core)
        │   ├── logging.py (import from shared-core)
        │   └── database.py (import from shared-core)
        ├── domain/ → symlink to ../../shared-domain/src/app/domain
        ├── routers/
        │   ├── __init__.py
        │   ├── agent_router.py (copied & adapted)
        │   ├── agent_integration_router.py
        │   ├── agent_performance.py
        │   ├── agent_creativity.py
        │   ├── agent_security_router.py
        │   └── services.py
        └── services/
            ├── __init__.py
            ├── agent_service.py
            ├── agent_orchestrator.py
            ├── agent_communication.py
            ├── agent_performance_service.py
            ├── agent_security.py
            ├── agent_integration.py
            ├── agent_portfolio_manager.py
            ├── agent_service_marketplace.py
            └── advanced_rl/
                ├── __init__.py
                ├── agents.py
                └── ppo_agent.py, rainbow_dqn_agent.py, sac_agent.py
```

### Step 2: Adapt Code for Service Boundaries

**Changes needed per file:**

- Update all `from ..domain.agent import X` to `from shared-domain.app.domain.agent import X`
- Remove any imports from other monolith services (e.g., `from ..services.other_service import X`)
- Replace internal service calls with HTTP client calls or event bus (defer to later phase)
- Update `ServiceSettings` to use agent-management specific defaults (port 8012)
- Add health check endpoint (already in template)
- Verify database setup: AgentExecution etc use shared Base. Need to call `Base.metadata.create_all(bind=engine)` on startup

**Special Case: advanced_rl/**
- These are AI model inference services. Consider moving to `ai-models` service instead.
- For now, keep in agent-management to maintain functionality.

### Step 3: Update Monolith to Proxy Requests (During Transition)

**Option A: Nginx Routing**
- Add nginx upstream for agent-management on port 8012
- Change coordinator-api routes for `/api/v1/agent/*` to proxy to agent-management
- Monolith no longer handles agent endpoints

**Option B: In-app Redirection**
- Keep routers in monolith but replace handlers with `HTTPClient` calls to new service
- More gradual migration but adds latency

**Recommendation:** Option A - cleaner separation, easier to rollback.

### Step 4: Create Systemd Service

```
/etc/systemd/system/aitbc-agent-management.service
[Unit]
Description=AITBC Agent Management Service
After=network.target

[Service]
Type=simple
User=aitbc
WorkingDirectory=/opt/aitbc/apps/agent-management
Environment=PATH=/opt/aitbc/venv/bin
Environment=PYTHONPATH=/opt/aitbc
ExecStart=/opt/aitbc/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8012
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Step 5: Database Migration

- Agent domain models likely already have tables defined via SQLModel
- In `main.py` startup event, call `Base.metadata.create_all(bind=engine)` to ensure tables exist
- Ensure the new service uses same database as monolith (coordinator.db) initially
- Later: separate database (Phase 8)

### Step 6: Integration Testing

1. Start agent-management service
2. Verify health endpoint: `curl http://localhost:8012/health`
3. Test agent creation via API
4. Verify coordinator-api can still access agent data (through new service or direct DB if keeping shared DB)
5. Run existing integration tests against new service

### Step 7: Update Coordinator-API

- Remove the 18 extracted files from monolith
- Remove domain/agent related imports from remaining monolith services if they now use agent-management API
- Update any remaining references to agent endpoints to use HTTP client or nginx proxy

### Step 8: Documentation & Monitoring

- Update README with agent-management API docs
- Add metrics endpoint if enabled
- Update deployment scripts

## Rollback Plan

1. Keep monolith files in git history (do not delete, just move)
2. Keep nginx config either/or - can revert upstream routing
3. Database shared initially, so data is accessible to both
4. Systemd service can be disabled; monolith still runs

## Success Criteria

- [ ] Agent-management service starts and health check passes on port 8012
- [ ] Can create/query agents via API
- [ ] Existing coordinator-api functionality that depends on agents still works
- [ ] No errors in logs during integration test
- [ ] Systemd service auto-restarts on failure

## Open Questions

1. **RL Agents**: Should advanced_rl be part of agent-management or ai-models?
   - Recommendation: Keep in agent-management for now (AI agent inference is part of agent runtime). Can split later if ai-models becomes a separate inference service.

2. **Database**: Separate or shared?
   - Phase 1: Shared (same coordinator.db) for simplicity
   - Phase 8: Split to dedicated agent-management database

3. **Cross-service calls**: Currently agent integration uses other services directly (imports). Need to replace with HTTP or event bus.
   - Defer until Phase 8 (Final Integration) to avoid breaking existing flow

4. **Domain extraction**: The domain models are currently in monolith. Should we extract entire domain to a package?
   - Immediate need: Create shared-domain package (symlink) to break import cycle
   - Future: Extract domain to true package with independent version

## Timeline Estimate

- Step 0 (shared-domain): 2h
- Step 1 (skeleton): 4h
- Step 2 (adaptation): 8h (bulk of work - fixing imports, resolving dependencies)
- Step 3 (nginx routing): 2h
- Step 4 (systemd): 1h
- Step 5 (DB): 1h
- Step 6 (testing): 4h
- Step 7 (monolith cleanup): 4h
- Step 8 (docs): 2h

**Total: ~28 hours (3-4 days)**

## Risks

- Hidden dependencies on other monolith services may cause runtime import errors
- Domain models may have cross-references that require co-migration
- Database migrations may be needed if agent tables don't exist yet
- Existing integration tests may fail and need updating
- Breaking changes if API contracts differ from original
