---
name: hermes-autonomy-testing
description: Test and diagnose Hermes agent autonomy features — distributed decisions, self-healing, resource management on AITBC coordinator.
---

# Hermes Autonomy Testing

## Service: aitbc-coordinator-api (port 8011)

All endpoints at `http://localhost:8011/v1/hermes/*` require `X-Api-Key` header.
API key: read from `/run/aitbc/secrets/.env` → `COORDINATOR_API_KEY=value`

## Known Bugs (2026-06-02)

### Bug 1: Self-healing crash (health_service_db.py)
- `_trigger_recovery()` line ~156: `action_id = uuid.uuid4()` not wrapped in `str()`
- Effect: every degraded/unhealthy health report and every high/critical error crashes with
  `sqlite3.ProgrammingError: type 'UUID' is not supported`
- `hermes_recovery_results` table stays empty (0 rows)

### Bug 2: Resource pools crash (resource_service_db.py)
- `get_resource_pools()` line ~297: `resource.resource_type.value` called on plain String column
- Effect: `GET /v1/hermes/resource/pools` returns 500
  `'str' object has no attribute 'value'`
- Fix: change to `resource.resource_type` (it's already a string)

### Bug 3: Fallback db_pg import (resource_service_db.py)
- `get_allocations()` has fallback `from ....storage.db_pg import SessionLocal`
- `db_pg.py` imports `config_pg.py` which doesn't exist as a loaded module
- Effect: would crash if session not injected (currently mitigated by router always injecting)

### Bug 4: Stale bytecode cache
- Coordinator started at 11:06, patches written at 11:32
- Old `.pyc` cache (11:06) is what Python loaded
- **Fix: `systemctl restart aitbc-coordinator-api`**
- Always restart after modifying Python files under coordinator-api

### Bug 5: Marketplace services not wired
- `plugin_manager`, `resource_matcher`, `market_analytics`, `external_providers`
  exist as service files but have NO router registration
- Not accessible via HTTP

## Test Commands

```bash
KEY=$(grep COORDINATOR_API_KEY /run/aitbc/secrets/.env | cut -d= -f2)
BASE=http://localhost:8011

# Decision propose
curl -s -X POST $BASE/v1/hermes/decision/propose \
  -H "Content-Type: application/json" -H "X-Api-Key: $KEY" \
  -d '{"decision_type":"resource_allocation","title":"Test","description":"Test decision","proposed_by":"agent-1","voting_deadline":"2026-06-03T12:00:00Z"}'

# Decision vote
curl -s -X POST $BASE/v1/hermes/decision/vote \
  -H "Content-Type: application/json" -H "X-Api-Key: $KEY" \
  -d '{"decision_id":"UUID","agent_id":"agent-2","vote":"approve","weight":1.5,"reason":"test"}'

# Health report (triggers self-healing on degraded/unhealthy)
curl -s -X POST $BASE/v1/hermes/health/report \
  -H "Content-Type: application/json" -H "X-Api-Key: $KEY" \
  -d '{"agent_id":"agent-1","service_name":"test-svc","status":"healthy","response_time_ms":45.0}'

# Report error (triggers self-healing on high/critical)
curl -s -X POST $BASE/v1/hermes/health/error \
  -H "Content-Type: application/json" -H "X-Api-Key: $KEY" \
  -d '{"agent_id":"agent-1","service_name":"test-svc","error_type":"network_error","severity":"high","error_message":"timeout","context":{"retry":3}}'

# Resource register + allocate
curl -s -X POST $BASE/v1/hermes/resource/register \
  -H "Content-Type: application/json" -H "X-Api-Key: $KEY" \
  -d '{"resource_id":"GPU-TEST-001","resource_type":"gpu","agent_id":"agent-1","status":"available","capacity":100.0}'

curl -s -X POST $BASE/v1/hermes/resource/allocate \
  -H "Content-Type: application/json" -H "X-Api-Key: $KEY" \
  -d '{"resource_type":"gpu","agent_id":"agent-2","required_capacity":20.0,"strategy":"demand_based","priority":8,"duration_hours":4.0}'
```

## DB Verification

```python
import sqlite3
conn = sqlite3.connect('/var/lib/aitbc/data/coordinator.db')
cur = conn.cursor()
for t in ['hermes_decisions','hermes_votes','hermes_health_checks',
          'hermes_error_reports','hermes_recovery_results',
          'hermes_resources','hermes_resource_allocations','hermes_pricing_adjustments']:
    cur.execute(f'SELECT count(*) FROM {t}')
    print(f'{t}: {cur.fetchone()[0]}')
conn.close()
```

## Decision Types
`resource_allocation`, `pricing_adjustment`, `task_assignment`, `consensus_vote`, `emergency_response`

## Vote Options
`approve`, `reject`, `abstain`

## Error Types
`network_error`, `timeout_error`, `authentication_error`, `resource_error`, `service_unavailable`, `database_error`, `unknown_error`

## Severity Levels
`low`, `medium`, `high`, `critical`

## Health Status Values
`healthy`, `degraded`, `unhealthy`, `recovering`

## Resource Status Values
`available`, `allocated`, `reserved`, `maintenance`, `offline`

## Allocation Strategies
`demand_based`, `priority_based`, `round_robin`, `least_loaded`
