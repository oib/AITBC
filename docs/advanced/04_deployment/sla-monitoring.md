# SLA Monitoring Guide

This guide covers SLA (Service Level Agreement) monitoring and billing instrumentation for coordinator/pool hub services in the AITBC ecosystem.

## Overview

The SLA monitoring system provides:
- Real-time tracking of miner performance metrics
- Automated SLA violation detection and alerting
- Capacity planning with forecasting and scaling recommendations
- Integration with coordinator-api billing system
- Comprehensive API endpoints for monitoring and management

## Architecture

```
┌─────────────────┐
│   Pool-Hub      │
│                 │
│  SLA Collector  │──────┐
│  Capacity       │      │
│  Planner        │      │
│                 │      │
└────────┬────────┘      │
         │               │
         │ HTTP API      │
         │               │
┌────────▼────────┐     │
│ Coordinator-API  │◀────┘
│                 │
│ Usage Tracking  │
│ Billing Service  │
│ Multi-tenant DB │
└─────────────────┘
```

## SLA Metrics

### Miner Uptime
- **Definition**: Percentage of time a miner is available and responsive
- **Calculation**: Based on heartbeat intervals (5-minute threshold)
- **Threshold**: 95%
- **Alert Levels**:
  - Critical: <85.5% (threshold * 0.9)
  - High: <95% (threshold)

### Response Time
- **Definition**: Average time for miner to respond to match requests
- **Calculation**: Average of `eta_ms` from match results (last 100 results)
- **Threshold**: 1000ms (P95)
- **Alert Levels**:
  - Critical: >2000ms (threshold * 2)
  - High: >1000ms (threshold)

### Job Completion Rate
- **Definition**: Percentage of jobs completed successfully
- **Calculation**: Successful outcomes / total outcomes (last 7 days)
- **Threshold**: 90%
- **Alert Levels**:
  - Critical: <90% (threshold)

### Capacity Availability
- **Definition**: Percentage of miners available (not busy)
- **Calculation**: Active miners / Total miners
- **Threshold**: 80%
- **Alert Levels**:
  - High: <80% (threshold)

## Configuration

### Environment Variables

Add to pool-hub `.env`:

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

### Settings File

Configuration can also be set in `poolhub/settings.py`:

```python
class Settings(BaseSettings):
    # Coordinator-API Billing Integration
    coordinator_billing_url: str = Field(default="http://localhost:8011")
    coordinator_api_key: str | None = Field(default=None)

    # SLA Configuration
    sla_thresholds: Dict[str, float] = Field(
        default_factory=lambda: {
            "uptime_pct": 95.0,
            "response_time_ms": 1000.0,
            "completion_rate_pct": 90.0,
            "capacity_availability_pct": 80.0,
        }
    )

    # Capacity Planning Configuration
    capacity_forecast_hours: int = Field(default=168)
    capacity_alert_threshold_pct: float = Field(default=80.0)

    # Billing Sync Configuration
    billing_sync_interval_hours: int = Field(default=1)

    # SLA Collection Configuration
    sla_collection_interval_seconds: int = Field(default=300)
```

## Database Schema

### SLA Metrics Table

```sql
CREATE TABLE sla_metrics (
    id UUID PRIMARY KEY,
    miner_id VARCHAR(64) NOT NULL REFERENCES miners(miner_id) ON DELETE CASCADE,
    metric_type VARCHAR(32) NOT NULL,
    metric_value FLOAT NOT NULL,
    threshold FLOAT NOT NULL,
    is_violation BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX ix_sla_metrics_miner_id ON sla_metrics(miner_id);
CREATE INDEX ix_sla_metrics_timestamp ON sla_metrics(timestamp);
CREATE INDEX ix_sla_metrics_metric_type ON sla_metrics(metric_type);
```

### SLA Violations Table

```sql
CREATE TABLE sla_violations (
    id UUID PRIMARY KEY,
    miner_id VARCHAR(64) NOT NULL REFERENCES miners(miner_id) ON DELETE CASCADE,
    violation_type VARCHAR(32) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    metric_value FLOAT NOT NULL,
    threshold FLOAT NOT NULL,
    violation_duration_ms INTEGER,
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX ix_sla_violations_miner_id ON sla_violations(miner_id);
CREATE INDEX ix_sla_violations_created_at ON sla_violations(created_at);
CREATE INDEX ix_sla_violations_severity ON sla_violations(severity);
```

### Capacity Snapshots Table

```sql
CREATE TABLE capacity_snapshots (
    id UUID PRIMARY KEY,
    total_miners INTEGER NOT NULL,
    active_miners INTEGER NOT NULL,
    total_parallel_capacity INTEGER NOT NULL,
    total_queue_length INTEGER NOT NULL,
    capacity_utilization_pct FLOAT NOT NULL,
    forecast_capacity INTEGER NOT NULL,
    recommended_scaling VARCHAR(32) NOT NULL,
    scaling_reason TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX ix_capacity_snapshots_timestamp ON capacity_snapshots(timestamp);
```

## Database Migration

Run the migration to add SLA and capacity tables:

```bash
cd apps/pool-hub
alembic upgrade head
```

## API Endpoints

### SLA Metrics Endpoints

#### Get SLA Metrics for a Miner
```bash
GET /sla/metrics/{miner_id}?hours=24
```

Response:
```json
[
  {
    "id": "uuid",
    "miner_id": "miner_001",
    "metric_type": "uptime_pct",
    "metric_value": 98.5,
    "threshold": 95.0,
    "is_violation": false,
    "timestamp": "2026-04-22T15:00:00Z",
    "metadata": {}
  }
]
```

#### Get All SLA Metrics
```bash
GET /sla/metrics?hours=24
```

#### Get SLA Violations
```bash
GET /sla/violations?resolved=false&miner_id=miner_001
```

#### Trigger SLA Metrics Collection
```bash
POST /sla/metrics/collect
```

Response:
```json
{
  "miners_processed": 10,
  "metrics_collected": [...],
  "violations_detected": 2,
  "capacity": {
    "total_miners": 10,
    "active_miners": 8,
    "capacity_availability_pct": 80.0
  }
}
```

### Capacity Planning Endpoints

#### Get Capacity Snapshots
```bash
GET /sla/capacity/snapshots?hours=24
```

#### Get Capacity Forecast
```bash
GET /sla/capacity/forecast?hours_ahead=168
```

Response:
```json
{
  "forecast_horizon_hours": 168,
  "current_capacity": 1000,
  "projected_capacity": 1500,
  "recommended_scaling": "+50%",
  "confidence": 0.85,
  "source": "coordinator_api"
}
```

#### Get Scaling Recommendations
```bash
GET /sla/capacity/recommendations
```

Response:
```json
{
  "current_state": "healthy",
  "recommendations": [
    {
      "action": "add_miners",
      "quantity": 2,
      "reason": "Projected capacity shortage in 2 weeks",
      "priority": "medium"
    }
  ],
  "source": "coordinator_api"
}
```

#### Configure Capacity Alerts
```bash
POST /sla/capacity/alerts/configure
```

Request:
```json
{
  "threshold_pct": 80.0,
  "notification_email": "admin@example.com"
}
```

### Billing Integration Endpoints

#### Get Billing Usage
```bash
GET /sla/billing/usage?hours=24&tenant_id=tenant_001
```

#### Sync Billing Usage
```bash
POST /sla/billing/sync
```

Request:
```json
{
  "miner_id": "miner_001",
  "hours_back": 24
}
```

#### Record Usage Event
```bash
POST /sla/billing/usage/record
```

Request:
```json
{
  "tenant_id": "tenant_001",
  "resource_type": "gpu_hours",
  "quantity": 10.5,
  "unit_price": 0.50,
  "job_id": "job_123",
  "metadata": {}
}
```

#### Generate Invoice
```bash
POST /sla/billing/invoice/generate
```

Request:
```json
{
  "tenant_id": "tenant_001",
  "period_start": "2026-03-01T00:00:00Z",
  "period_end": "2026-03-31T23:59:59Z"
}
```

### Status Endpoint

#### Get SLA Status
```bash
GET /sla/status
```

Response:
```json
{
  "status": "healthy",
  "active_violations": 0,
  "recent_metrics_count": 50,
  "timestamp": "2026-04-22T15:00:00Z"
}
```

## Automated Collection

### SLA Collection Scheduler

The SLA collector can be run as a background service to automatically collect metrics:

```python
from poolhub.services.sla_collector import SLACollector, SLACollectorScheduler
from poolhub.database import get_db

# Initialize
db = next(get_db())
sla_collector = SLACollector(db)
scheduler = SLACollectorScheduler(sla_collector)

# Start automated collection (every 5 minutes)
await scheduler.start(collection_interval_seconds=300)
```

### Billing Sync Scheduler

The billing integration can be run as a background service to automatically sync usage:

```python
from poolhub.services.billing_integration import BillingIntegration, BillingIntegrationScheduler
from poolhub.database import get_db

# Initialize
db = next(get_db())
billing_integration = BillingIntegration(db)
scheduler = BillingIntegrationScheduler(billing_integration)

# Start automated sync (every 1 hour)
await scheduler.start(sync_interval_hours=1)
```

## Monitoring and Alerting

### Prometheus Metrics

SLA metrics are exposed to Prometheus with the namespace `poolhub`:

- `poolhub_sla_uptime_pct` - Miner uptime percentage
- `poolhub_sla_response_time_ms` - Response time in milliseconds
- `poolhub_sla_completion_rate_pct` - Job completion rate percentage
- `poolhub_sla_capacity_availability_pct` - Capacity availability percentage
- `poolhub_sla_violations_total` - Total SLA violations
- `poolhub_billing_sync_errors_total` - Billing sync errors

### Alert Rules

Example Prometheus alert rules:

```yaml
groups:
  - name: poolhub_sla
    rules:
      - alert: HighSLAViolationRate
        expr: rate(poolhub_sla_violations_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: High SLA violation rate

      - alert: LowMinerUptime
        expr: poolhub_sla_uptime_pct < 95
        for: 5m
        labels:
          severity: high
        annotations:
          summary: Miner uptime below threshold

      - alert: HighResponseTime
        expr: poolhub_sla_response_time_ms > 1000
        for: 5m
        labels:
          severity: high
        annotations:
          summary: Response time above threshold
```

## Troubleshooting

### SLA Metrics Not Recording

**Symptom**: SLA metrics are not being recorded in the database

**Solutions**:
1. Check SLA collector is running: `ps aux | grep sla_collector`
2. Verify database connection: Check pool-hub database logs
3. Check SLA collection interval: Ensure `sla_collection_interval_seconds` is configured
4. Verify miner heartbeats: Check `miner_status.last_heartbeat_at` is being updated

### Billing Sync Failing

**Symptom**: Billing sync to coordinator-api is failing

**Solutions**:
1. Verify coordinator-api is accessible: `curl http://localhost:8011/health`
2. Check API key: Ensure `COORDINATOR_API_KEY` is set correctly
3. Check network connectivity: Ensure pool-hub can reach coordinator-api
4. Review billing integration logs: Check for HTTP errors or timeouts

### Capacity Alerts Not Triggering

**Symptom**: Capacity alerts are not being generated

**Solutions**:
1. Verify capacity snapshots are being created: Check `capacity_snapshots` table
2. Check alert thresholds: Ensure `capacity_alert_threshold_pct` is configured
3. Verify alert configuration: Check alert configuration endpoint
4. Review coordinator-api capacity planning: Ensure it's receiving pool-hub data

## Testing

Run the SLA and billing integration tests:

```bash
cd apps/pool-hub

# Run all SLA and billing tests
pytest tests/test_sla_collector.py
pytest tests/test_billing_integration.py
pytest tests/test_sla_endpoints.py
pytest tests/test_integration_coordinator.py

# Run with coverage
pytest --cov=poolhub.services.sla_collector tests/test_sla_collector.py
pytest --cov=poolhub.services.billing_integration tests/test_billing_integration.py
```

## Best Practices

1. **Monitor SLA Metrics Regularly**: Set up automated monitoring dashboards to track SLA metrics in real-time
2. **Configure Appropriate Thresholds**: Adjust SLA thresholds based on your service requirements
3. **Review Violations Promptly**: Investigate and resolve SLA violations quickly to maintain service quality
4. **Plan Capacity Proactively**: Use capacity forecasting to anticipate scaling needs
5. **Test Billing Integration**: Regularly test billing sync to ensure accurate usage tracking
6. **Keep Documentation Updated**: Maintain up-to-date documentation for SLA configurations and procedures

## Integration with Existing Systems

### Coordinator-API Integration

The pool-hub integrates with coordinator-api's billing system via HTTP API:

1. **Usage Recording**: Pool-hub sends usage events to coordinator-api's `/api/billing/usage` endpoint
2. **Billing Metrics**: Pool-hub can query billing metrics from coordinator-api
3. **Invoice Generation**: Pool-hub can trigger invoice generation in coordinator-api
4. **Capacity Planning**: Pool-hub provides capacity data to coordinator-api's capacity planning system

### Prometheus Integration

SLA metrics are automatically exposed to Prometheus:
- Metrics are labeled by miner_id, metric_type, and other dimensions
- Use Prometheus query language to create custom dashboards
- Set up alert rules based on SLA thresholds

### Alerting Integration

SLA violations can trigger alerts through:
- Prometheus Alertmanager
- Custom webhook integrations
- Email notifications (via coordinator-api)
- Slack/Discord integrations (via coordinator-api)

## Security Considerations

1. **API Key Security**: Store coordinator-api API keys securely (use environment variables or secret management)
2. **Database Access**: Ensure database connections use SSL/TLS in production
3. **Rate Limiting**: Implement rate limiting on billing sync endpoints to prevent abuse
4. **Audit Logging**: Enable audit logging for SLA and billing operations
5. **Access Control**: Restrict access to SLA and billing endpoints to authorized users

## Performance Considerations

1. **Batch Operations**: Use batch operations for billing sync to reduce HTTP overhead
2. **Index Optimization**: Ensure database indexes are properly configured for SLA queries
3. **Caching**: Use Redis caching for frequently accessed SLA metrics
4. **Async Processing**: Use async operations for SLA collection and billing sync
5. **Data Retention**: Implement data retention policies for SLA metrics and capacity snapshots

## Maintenance

### Regular Tasks

1. **Review SLA Thresholds**: Quarterly review and adjust SLA thresholds based on service performance
2. **Clean Up Old Data**: Regularly clean up old SLA metrics and capacity snapshots (e.g., keep 90 days)
3. **Review Capacity Forecasts**: Monthly review of capacity forecasts and scaling recommendations
4. **Audit Billing Records**: Monthly audit of billing records for accuracy
5. **Update Documentation**: Keep documentation updated with any configuration changes

### Backup and Recovery

1. **Database Backups**: Ensure regular backups of SLA and billing tables
2. **Configuration Backups**: Backup configuration files and environment variables
3. **Recovery Procedures**: Document recovery procedures for SLA and billing systems
4. **Testing Backups**: Regularly test backup and recovery procedures

## References

- [Pool-Hub README](/opt/aitbc/apps/pool-hub/README.md)
- [Coordinator-API Billing Documentation](/opt/aitbc/apps/coordinator-api/README.md)
- [Roadmap](/opt/aitbc/docs/beginner/02_project/2_roadmap.md)
- [Deployment Guide](/opt/aitbc/docs/advanced/04_deployment/0_index.md)
