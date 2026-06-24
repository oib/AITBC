# Agent-Coordinator Service Boundary Decision

**Produced**: 2026-06-24 (P4, v0.5.13 Phase 4)
**Question**: Should `apps/agent-coordinator/` (61 .py files, port 9001, Core Service: No) remain a separate microservice, or fold into `apps/coordinator-api/` (485 .py files, port 8203, Core Service: Yes) as a bounded context?

---

## Recommendation: Keep Separate

**Decision**: `agent-coordinator` should remain a separate microservice. Do NOT fold it into `coordinator-api`.

**Rationale**: The two services have no runtime coupling — no shared database, no API calls between them, independent deployment, and serve fundamentally different responsibilities. Folding them together would increase the coordinator-api blast radius without eliminating any actual coupling.

---

## Evidence

### 1. No API coupling between the services

| Direction | Finding |
|-----------|---------|
| coordinator-api → agent-coordinator | **Zero API calls.** All 7 files in coordinator-api referencing port 9001 use it only in CORS `allow_origins` lists — not as an HTTP client target. No `httpx`/`requests`/`AITBCHTTPClient` calls to 9001 exist. |
| agent-coordinator → coordinator-api | **Zero API calls.** The only reference is `COORDINATOR_API_KEY` env var in `coin_requests.py:44` — an API key name, not a URL. No HTTP calls to port 8203. |

### 2. No shared database

| Service | Database | ORM | Path |
|---------|----------|-----|------|
| agent-coordinator | Own SQLite, coin_requests only | stdlib `sqlite3` | `AGENT_DB_PATH` → `/var/lib/aitbc/data/agent_coin_requests.db` |
| coordinator-api | Own SQLAlchemy DB | SQLModel/SQLAlchemy | `coordinator.db` via `DatabaseConfig.effective_url` |

The agent-coordinator's DB is a single-table SQLite for coin request tracking. The coordinator-api's DB holds the full domain model (25+ tables). They don't share a database file, schema, or ORM.

### 3. Redis: different databases

| Service | Redis URL |
|---------|-----------|
| agent-coordinator | `redis://localhost:6379/1` (db 1) |
| coordinator-api | `redis://localhost:6379/0` (db 0, via `RedisConfig`) |

They share a Redis instance but use different logical databases. No key-space overlap.

### 4. Independent deployment

| Aspect | agent-coordinator | coordinator-api |
|--------|-------------------|-----------------|
| Port | 9001 | 8203 |
| systemd service | `aitbc-agent-coordinator.service` (file exists, **not symlinked**, not enabled) | `aitbc-coordinator-api.service` (symlinked, active) |
| Dependencies | `redis.service`, `aitbc-blockchain-node.service` | `aitbc-blockchain-node.service` |
| Working directory | `/opt/aitbc` | `/opt/aitbc` |
| PYTHONPATH | `/opt/aitbc:/opt/aitbc/apps/agent-coordinator/src` | `src` (relative) |

The services have independent systemd units with different dependency chains. Agent-coordinator depends on Redis; coordinator-api does not.

### 5. Different responsibilities

| Service | Responsibility | Endpoints |
|---------|---------------|-----------|
| agent-coordinator | Agent communication, presence, message routing, WebSocket streaming, coin requests | 103 endpoints across 15 routers |
| coordinator-api | Central API hub for agents, miners, marketplace, governance, all core services | 24+ routes (via contexts) |

Agent-coordinator is a **real-time messaging and agent lifecycle** service (WebSocket-heavy, 103 endpoints). Coordinator-api is a **REST API gateway** for the broader ecosystem. Their domains don't overlap.

### 6. External clients

The CLI (`cli/aitbc_cli/commands/agent_sdk.py`) calls agent-coordinator directly at `http://localhost:9001` for agent discovery, registration, and management. These are direct client-to-service calls that bypass coordinator-api entirely. Folding agent-coordinator into coordinator-api would break this direct access pattern.

---

## What folding in WOULD require (cost analysis)

If we were to fold agent-coordinator into coordinator-api:
1. Migrate 61 .py files + 103 endpoints into `contexts/agent_coordination/`
2. Merge the coin_requests SQLite DB into coordinator-api's SQLAlchemy DB (schema migration)
3. Repoint CLI from `localhost:9001` to `localhost:8203/v1/agents/*`
4. Merge two auth systems (PyJWT with dict returns → PyJWT with HTTPException)
5. Merge two rate-limiting setups (already shared via `aitbc.rate_limiting`, but config differs)
6. Unify Redis usage (db 1 → db 0 or shared)
7. Create a new systemd unit or modify the existing coordinator-api unit

**Benefit gained**: One fewer service to deploy. One fewer port to manage.
**Cost**: Large migration with high blast radius, breaking CLI changes, DB schema merge, for zero coupling reduction (there is no coupling to reduce).

---

## Action Items (based on "keep separate" decision)

1. **P5 is skipped** — no restructure into a bounded context needed.
2. **Fix the missing systemd symlink** — `aitbc-agent-coordinator.service` file exists at `apps/agent-coordinator/aitbc-agent-coordinator.service` but is NOT symlinked into `/etc/systemd/system/` (unlike the 12 other aitbc services). This is a deployment gap, not a code issue. Recommend: `ln -s /opt/aitbc/apps/agent-coordinator/aitbc-agent-coordinator.service /etc/systemd/system/aitbc-agent-coordinator.service`
3. **README already exists** — `apps/agent-coordinator/README.md` is present with the correct status-table pattern. One fix needed: it says "48 Python file(s)" but the actual count is 61.
4. **CORS cleanup opportunity** (low priority) — the 7 coordinator-api files that list `localhost:9001` in CORS origins could remove it if no browser client ever makes cross-origin requests to agent-coordinator via coordinator-api's CORS policy. This is cosmetic, not a boundary issue.

---

## Verification

- [x] Investigated coordinator-api → agent-coordinator API calls (zero found)
- [x] Investigated agent-coordinator → coordinator-api API calls (zero found)
- [x] Checked shared database (none — different DBs, different ORMs)
- [x] Checked Redis coupling (shared instance, different logical DBs)
- [x] Checked systemd dependency chain (independent units)
- [x] Checked external client access (CLI calls agent-coordinator directly)
- [x] Checked README existence (present, minor file count error)
- [x] Decision documented with rationale
