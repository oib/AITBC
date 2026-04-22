# Pool Hub

## Purpose & Scope

Matchmaking gateway between coordinator job requests and available miners. See `docs/bootstrap/pool_hub.md` for architectural guidance.

## Development Setup

- Create a Python virtual environment under `apps/pool-hub/.venv`.
- Install FastAPI, Redis (optional), and PostgreSQL client dependencies once requirements are defined.
- Implement routers and registry as described in the bootstrap document.

## SLA Monitoring and Billing Integration

Pool-Hub now includes comprehensive SLA monitoring and billing integration with coordinator-api:

### SLA Metrics

- **Miner Uptime**: Tracks miner availability based on heartbeat intervals
- **Response Time**: Monitors average response time from match results
- **Job Completion Rate**: Tracks successful vs failed job outcomes
- **Capacity Availability**: Monitors overall pool capacity utilization

### SLA Thresholds

Default thresholds (configurable in settings):
- Uptime: 95%
- Response Time: 1000ms
- Completion Rate: 90%
- Capacity Availability: 80%

### Billing Integration

Pool-Hub integrates with coordinator-api's billing system to:
- Record usage data (gpu_hours, api_calls, compute_hours)
- Sync miner usage to tenant billing
- Generate invoices via coordinator-api
- Track billing metrics and costs

### API Endpoints

SLA and billing endpoints are available under `/sla/`:
- `GET /sla/metrics/{miner_id}` - Get SLA metrics for a miner
- `GET /sla/metrics` - Get SLA metrics across all miners
- `GET /sla/violations` - Get SLA violations
- `POST /sla/metrics/collect` - Trigger SLA metrics collection
- `GET /sla/capacity/snapshots` - Get capacity planning snapshots
- `GET /sla/capacity/forecast` - Get capacity forecast
- `GET /sla/capacity/recommendations` - Get scaling recommendations
- `GET /sla/billing/usage` - Get billing usage data
- `POST /sla/billing/sync` - Trigger billing sync with coordinator-api

### Configuration

Add to `.env`:
```bash
# Coordinator-API Billing Integration
COORDINATOR_BILLING_URL=http://localhost:8011
COORDINATOR_API_KEY=your_api_key_here

# SLA Configuration
SLA_UPTIME_THRESHOLD=95.0
SLA_RESPONSE_TIME_THRESHOLD=1000.0
SLA_COMPLETION_RATE_THRESHOLD=90.0
SLA_CAPACITY_THRESHOLD=80.0

# Capacity Planning
CAPACITY_FORECAST_HOURS=168
CAPACITY_ALERT_THRESHOLD_PCT=80.0

# Billing Sync
BILLING_SYNC_INTERVAL_HOURS=1

# SLA Collection
SLA_COLLECTION_INTERVAL_SECONDS=300
```

### Database Migration

Run the database migration to add SLA and capacity tables:
```bash
cd apps/pool-hub
alembic upgrade head
```

### Testing

Run tests for SLA and billing integration:
```bash
cd apps/pool-hub
pytest tests/test_sla_collector.py
pytest tests/test_billing_integration.py
pytest tests/test_sla_endpoints.py
pytest tests/test_integration_coordinator.py
```
