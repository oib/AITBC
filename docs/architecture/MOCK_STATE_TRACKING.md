# Mock State Tracking

**Status**: Temporary — all in-memory mock state must be migrated to DB/Redis in v0.5.0.

## Active Mock State

| File | Variable | Type | Gated by debug? | Migration target |
|------|----------|------|-------------------|------------------|
| `routers/training.py` | `_mock_jobs` | `dict[str, dict]` | ✅ `settings.debug \| \| settings.enable_mock_training` | Redis job queue |
| `routers/agent.py` | `_mock_agents` | `dict[str, dict]` | ✅ `settings.debug \| \| settings.enable_mock_agent` | Redis agent registry |
| `routers/agent.py` | `_mock_messages` | `dict[str, list]` | ✅ `settings.debug \| \| settings.enable_mock_agent` | Redis message stream |
| `contexts/agent_coordination/routers/swarm.py` | `_mock_nodes` | `dict[str, dict]` | ✅ `settings.debug` | Redis node registry |
| `contexts/agent_coordination/routers/swarm.py` | `_mock_tasks` | `dict[str, dict]` | ✅ `settings.debug` | Redis task queue |

## Safety

All mock routes are **disabled in production**:
- `training.py`: `settings.debug \| \| settings.enable_mock_training`
- `agent.py`: `settings.debug \| \| settings.enable_mock_agent`
- `swarm.py` (router): `settings.debug \| \| settings.enable_mock_swarm`
- `swarm.py` (context): `settings.debug`

`settings.debug` defaults to `False`. The `enable_mock_*` flags default to `False` and are validated to reject `True` in production.

## Migration Plan

See `docs/releases/v0.5.0/change.log` — Goal: DB/Redis Backing for Mock State.
