# App Shell Classification

**Last Updated:** 2026-05-28

This document classifies app shells and thin services in the AITBC repository.

## Classification

### Active Services

| Service | Status | Purpose | Dependencies |
|---------|--------|---------|--------------|
| `shared-domain` | **ACTIVE** | Shared domain models (agent, performance, portfolio, etc.) used by agent-management and other services | Used by `aitbc-agent-management` |
| `shared-core` | **ACTIVE** | Shared core utilities (config, database, logging, security) for microservices | Used by root aitbc package |
| `marketplace-service` | **ACTIVE** | Production GPU marketplace service with proper packaging | Standard Poetry app |
| `docs/enterprise` | **ACTIVE** | Enterprise integration documentation | Documentation only |

### Candidates for Removal

| Service | Status | Reason | Action |
|---------|--------|--------|--------|
| `marketplace-service-debug` | **REMOVE** | Debug variant without pyproject.toml; redundant given marketplace-service exists | Remove directory |

### Non-Existent

| Service | Status | Reason |
|---------|--------|--------|
| `docs/ai-models` | N/A | Directory does not exist |

## Service Boundaries

### shared-domain
- **Purpose**: Centralized domain models for AITBC microservices
- **Contents**: Agent, performance, portfolio, AMM, analytics, bounty, certification, reputation, trading, etc.
- **Consumers**: `aitbc-agent-management`
- **Location**: `/opt/aitbc/apps/shared-domain/src/app/domain/`

### shared-core
- **Purpose**: Shared core utilities (config, database, logging, security)
- **Contents**: Configuration management, database utilities, structured logging, security helpers
- **Consumers**: Root aitbc package and microservices
- **Location**: `/opt/aitbc/apps/shared-core/src/app/core/`

### marketplace-service
- **Purpose**: Production GPU marketplace service
- **Contents**: FastAPI app with marketplace operations
- **Location**: `/opt/aitbc/apps/marketplace-service/`

## Actions Taken

- [x] Classified `shared-domain` as ACTIVE
- [x] Classified `shared-core` as ACTIVE
- [x] Classified `marketplace-service` as ACTIVE
- [x] Classified `marketplace-service-debug` for removal
- [x] Documented `docs/enterprise` as active documentation
- [ ] Remove `marketplace-service-debug` directory

## References

- Roadmap: `/root/.windsurf/plans/aitbc-codebase-remediation-roadmap-5659ea.md`
- Analysis: `.hermes/plans/2026-05-12_102100-aitbc-codebase-analysis.md`
