# App Shell Classification

**Last Updated:** 2026-05-28

> **Historical record.** Package paths below predate the per-service package
> rename — `src/app/domain/` is now `src/shared_domain/`, `src/app/core/` is
> `src/shared_core/`, and `src/app/` in each app became a per-service package
> (`agent_app`, `coordinator_api`, …). The `aitbc-agent-management` consumer
> no longer exists as a unit. The classification decisions still apply; the
> paths do not.

This document classifies app shells and thin services in the AITBC repository.

## Classification

### Active Services

| Service | Status | Purpose | Dependencies |
|---------|--------|---------|--------------|
| `shared-domain` | **ACTIVE** | Shared domain models (agent, performance, portfolio, etc.) used by agent-management and other services | Used by `aitbc-agent-management` |
| `shared-core` | **ACTIVE** | Shared core utilities (config, database, logging, security) for microservices | Used by root aitbc package |
| `market-service` | **ACTIVE** | Production GPU market service with proper packaging | Standard Poetry app |
| `docs/enterprise` | **ACTIVE** | Enterprise integration documentation | Documentation only |

### Candidates for Removal

| Service | Status | Reason | Action |
|---------|--------|--------|--------|
| `market-debug` | **REMOVE** | Debug variant without pyproject.toml; redundant given market-service exists | Remove directory |

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

### market-service

- **Purpose**: Production GPU market service
- **Contents**: FastAPI app with market operations
- **Location**: `/opt/aitbc/apps/market/`

## Actions Taken

- [x] Classified `shared-domain` as ACTIVE
- [x] Classified `shared-core` as ACTIVE
- [x] Classified `market-service` as ACTIVE
- [x] Classified `market-debug` for removal
- [x] Documented `docs/enterprise` as active documentation
- [ ] Remove `market-debug` directory

## References

- Roadmap: `/root/.windsurf/plans/aitbc-codebase-remediation-roadmap-5659ea.md`
- Analysis: `.agent/plans/2026-05-12_102100-aitbc-codebase-analysis.md`
