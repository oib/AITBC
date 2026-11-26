# P4: Agent-Coordinator Service Boundary Decision

**Date:** 2026-06-24
**Status:** Decision — **keep flat structure (no bounded contexts)**

---

## Context

The coordinator-api was restructured into 36 bounded contexts (`app/contexts/`) to manage its complexity (27 domain models, 50+ services, 200+ routes). The question is whether agent-coordinator should undergo the same restructuring.

## Agent-Coordinator Profile

| Metric | Value |
|---|---|
| Total lines | ~10,000 |
| Python files | 43 |
| Subpackages | 11 (ai, auth, consensus, encryption, monitoring, protocols, routers, routing, services, storage, websocket, workflow) |
| Routes | 103 across 15 router files |
| Domain models | 0 (no `domain/` package — uses `models.py` flat file) |
| Cross-service imports | 0 (does not import from coordinator-api or vice versa) |
| Largest file | `routing/load_balancer.py` (658 lines) |

## Internal Coupling Analysis

Subpackage-to-subpackage imports are **low**:

| Subpackage | Imported by |
|---|---|
| `ai` | routers/ai, routers/consensus |
| `auth` | routers/alerts, routers/auth, routers/monitoring, routers/users |
| `consensus` | routers/consensus |
| `monitoring` | routers/alerts, routers/monitoring |
| `protocols` | routers/messages, routing/agent_discovery, routing/load_balancer |
| `routing` | routers/agents, routers/messages, routers/tasks |
| `services` | websocket/agent_stream |

**Key observation:** Subpackages don't import from each other — only routers import from subpackages. This is a clean layered architecture (routers → services → storage), not a tangled web of cross-context dependencies.

## Decision: Keep Flat Structure

**Rationale:**

1. **Focused scope**: Agent-coordinator handles one concern — agent coordination (discovery, routing, messaging, consensus). It doesn't have the multi-domain complexity that drove coordinator-api's context split (marketplace, trading, governance, reputation, etc.).

2. **Low coupling**: The 11 subpackages are already well-separated. Only routers import from subpackages; subpackages don't import from each other. There's no coupling problem to solve.

3. **No domain models**: The service uses a single `models.py` file, not 27 domain model files. There's no domain ownership ambiguity to resolve.

4. **Size is manageable**: 10K lines across 43 files is within the range where a flat structure works. Coordinator-api was 30K+ lines with 27 domain models when it was split.

5. **Restructuring cost > benefit**: Moving to bounded contexts would require creating context directories, moving files, updating all imports, and adding context boilerplate — for zero coupling reduction.

## What Was Done Instead

- **P2**: Fixed 10 broken cross-context imports in coordinator-api (the actual coupling problem)
- **P3**: Added `__all__` to 27 domain modules + 34 context READMEs in coordinator-api
- **E501 cleanup**: 5 line-too-long violations in agent-coordinator (separate task, low priority)

## P5 Status

**P5 (agent-coordinator restructure) is cancelled** — gated on P4, and P4 decided no restructure. The agent-coordinator's flat structure is the correct architecture for its scope and coupling profile.

## Recommendations for Agent-Coordinator

Instead of restructuring, focus on:

1. **Decompose largest files** — `load_balancer.py` (658 lines), `agent_stream.py` (583 lines), `alerting.py` (549 lines) are candidates for splitting if they grow further.
2. **Add `__all__` to `models.py`** — declare public API surface (same pattern as P3 for coordinator-api domain modules).
3. **Keep the layered architecture** — routers → services → storage is working well. Don't introduce cross-subpackage imports.
