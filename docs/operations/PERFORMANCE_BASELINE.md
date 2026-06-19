# Performance Baseline

**Last Updated:** 2026-06-19
**Version:** v0.5.1

## Overview

This document describes the performance baseline for AITBC services, including load testing procedures, target metrics, and measurement guidelines.

## Target Performance Metrics

### Coordinator API

| Endpoint | Target RPS | Description |
|----------|------------|-------------|
| Job Submit | 100 req/s | API endpoint for submitting training jobs |
| Miner Heartbeat | 1000 req/s | High-frequency miner status updates |
| Health Check | 500 req/s | Service health monitoring |
| List Jobs | 200 req/s | Query job status |
| List Miners | 200 req/s | Query miner information |

### Database Performance

| Metric | Target | Description |
|--------|--------|-------------|
| Connection Pool | 10 base + 20 overflow | DB connection pool limits |
| Query Count | < 10 per API call | Maximum queries per request |
| Query Latency | < 100ms (p95) | Database query response time |
| Connection Timeout | 30s | Database connection timeout |
| Pool Recycle | 3600s | Connection recycling interval |

## Load Testing

### CI Integration

Load tests are integrated into GitHub Actions CI and run nightly:

```yaml
schedule:
  # Run load tests nightly at 2 AM UTC
  - cron: '0 2 * * *'
```

The load test job:
- Starts coordinator API in test mode
- Runs locust load tests for 60 seconds
- Generates HTML reports
- Uploads reports as artifacts (30-day retention)

### Manual Load Testing

Run load tests locally:

```bash
# Start coordinator API
cd apps/coordinator-api
source /opt/aitbc/venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# In another terminal, run load tests
cd tests/load
locust -f test_coordinator_api.py --headless --users 100 --spawn-rate 10 --run-time 60s --host http://127.0.0.1:8000 --html load-test-report.html
```

### Load Test Profiles

**Normal Load:**
- Users: 100
- Spawn rate: 10
- Duration: 60s
- Target: Simulate normal production traffic

**Stress Load:**
- Users: 500
- Spawn rate: 50
- Duration: 30s
- Target: Test system under high load

**Spike Load:**
- Users: 1000
- Spawn rate: 100
- Duration: 20s
- Target: Test system resilience to traffic spikes

## Measurement Procedures

### 1. Baseline Measurement

Before making performance changes, establish a baseline:

```bash
# Run normal load test
cd tests/load
locust -f test_coordinator_api.py --headless --users 100 --spawn-rate 10 --run-time 60s --host http://127.0.0.1:8000 --html baseline-report.html

# Record metrics:
# - Average response time
# - 95th percentile response time
# - Requests per second (RPS)
# - Error rate
# - CPU/memory usage
```

### 2. Post-Change Measurement

After performance changes, measure again:

```bash
# Run same load test
locust -f test_coordinator_api.py --headless --users 100 --spawn-rate 10 --run-time 60s --host http://127.0.0.1:8000 --html post-change-report.html

# Compare with baseline
# - Response time improvement
# - RPS improvement
# - Error rate reduction
```

### 3. Continuous Monitoring

Monitor performance in production:

```bash
# Check Prometheus metrics
curl http://localhost:8000/prometheus

# Key metrics to monitor:
# - http_request_duration_seconds (histogram)
# - http_requests_total (counter)
# - http_errors_total (counter)
# - rpc_request_duration_seconds (histogram)
# - rpc_requests_total (counter)
```

## Alert Routing for SLOs

### SLO Alerting Strategy

Alerts are configured based on the performance baseline targets to ensure service-level objectives (SLOs) are met.

### Alert Thresholds

#### Coordinator API Alerts

| Metric | Warning Threshold | Critical Threshold | Alert Channel | Escalation |
|--------|------------------|-------------------|--------------|------------|
| Job Submit Latency (p95) | > 200ms | > 500ms | #ops-alerts | 15min → #ops-lead |
| Miner Heartbeat Latency (p95) | > 50ms | > 100ms | #ops-alerts | 15min → #ops-lead |
| Health Check Latency (p95) | > 100ms | > 200ms | #ops-alerts | 15min → #ops-lead |
| Error Rate | > 1% | > 5% | #ops-alerts | 5min → #ops-lead |
| Request Rate Drop | < 80% of baseline | < 50% of baseline | #ops-alerts | 5min → #ops-lead |

#### Database Alerts

| Metric | Warning Threshold | Critical Threshold | Alert Channel | Escalation |
|--------|------------------|-------------------|--------------|------------|
| Query Latency (p95) | > 150ms | > 300ms | #ops-alerts | 15min → #ops-lead |
| Connection Pool Usage | > 80% | > 95% | #ops-alerts | 10min → #ops-lead |
| Connection Errors | > 0.1% | > 1% | #ops-alerts | 5min → #ops-lead |
| Query Count per Request | > 15 | > 25 | #ops-alerts | 15min → #ops-lead |

#### Service Health Alerts

| Metric | Warning Threshold | Critical Threshold | Alert Channel | Escalation |
|--------|------------------|-------------------|--------------|------------|
| Service Down Time | > 30s | > 2min | #ops-alerts | 1min → #ops-lead |
| Memory Usage | > 80% | > 95% | #ops-alerts | 15min → #ops-lead |
| CPU Usage | > 70% | > 90% | #ops-alerts | 15min → #ops-lead |
| Disk Usage | > 80% | > 90% | #ops-alerts | 30min → #ops-lead |

### Alert Channels

#### Primary Channels

- **#ops-alerts**: Primary operations alert channel
  - All warning and critical alerts
  - On-call rotation: 24/7 coverage
  - Response time: < 5 minutes

- **#ops-lead**: Operations lead escalation channel
  - Critical alerts that don't resolve
  - Escalated from #ops-alerts after timeout
  - Response time: < 15 minutes

#### Secondary Channels

- **#dev-urgent**: Developer urgent issues
  - Code-related alerts only
  - Performance regressions
  - Memory leaks, deadlocks

- **#security-alerts**: Security incidents
  - Unauthorized access attempts
  - Secret rotation failures
  - Anomalous traffic patterns

### Alert Configuration (Prometheus)

#### Example Alert Rules

```yaml
groups:
  - name: coordinator_api_slo
    rules:
      - alert: CoordinatorAPIHighLatency
        expr: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket{endpoint="/v1/training/jobs"}[5m])
          ) > 0.5
        for: 5m
        labels:
          severity: critical
          service: coordinator-api
        annotations:
          summary: "Coordinator API job submission latency too high"
          description: "p95 latency for job submission is {{ $value }}s (threshold: 0.5s)"

      - alert: CoordinatorAPIHighErrorRate
        expr: |
          rate(http_errors_total{service="coordinator-api"}[5m]) /
          rate(http_requests_total{service="coordinator-api"}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
          service: coordinator-api
        annotations:
          summary: "Coordinator API error rate too high"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 5%)"

      - alert: DatabaseConnectionPoolExhausted
        expr: |
          db_pool_active_connections / db_pool_max_connections > 0.95
        for: 2m
        labels:
          severity: critical
          service: database
        annotations:
          summary: "Database connection pool nearly exhausted"
          description: "Pool usage is {{ $value | humanizePercentage }} (threshold: 95%)"
```

### Alert Routing Matrix

| Alert Type | Severity | Channel | On-Call | Escalation |
|------------|----------|---------|---------|------------|
| Service Down | Critical | #ops-alerts | Yes | 1min → #ops-lead |
| High Latency | Critical | #ops-alerts | Yes | 5min → #ops-lead |
| High Error Rate | Critical | #ops-alerts | Yes | 5min → #ops-lead |
| Memory Exhaustion | Critical | #ops-alerts | Yes | 5min → #ops-lead |
| Database Issues | Critical | #ops-alerts | Yes | 5min → #ops-lead |
| Security Incident | Critical | #security-alerts | Yes | Immediate |
| Performance Regression | Warning | #ops-alerts | No | 15min → #ops-lead |
| Capacity Issues | Warning | #ops-alerts | No | 30min → #ops-lead |
| Code Issues | Warning | #dev-urgent | No | 1hour → #ops-lead |

### Alert Response Procedures

#### Critical Alerts

1. **Immediate Response (< 5 minutes)**
   - Acknowledge alert in monitoring system
   - Check service status: `systemctl status <service>`
   - Check logs: `journalctl -u <service> -n 100`
   - Verify impact: Check error rates, latency metrics

2. **Investigation (< 15 minutes)**
   - Identify root cause using logs and metrics
   - Check recent deployments or configuration changes
   - Verify external dependencies (database, Redis, etc.)

3. **Resolution**
   - Apply fix or rollback if needed
   - Verify service recovery
   - Document incident in post-mortem

#### Warning Alerts

1. **Response (< 30 minutes)**
   - Acknowledge alert
   - Monitor trend
   - Plan remediation if trend continues

2. **Resolution**
   - Schedule fix during maintenance window
   - Update documentation if needed

### Alert Suppression

Alerts can be suppressed during planned maintenance:

```bash
# Suppress alerts for 1 hour during maintenance
curl -X POST http://alertmanager/api/v1/silences \
  -d '{
    "matchers": [{"name": "service", "value": "coordinator-api"}],
    "startsAt": "2026-06-19T10:00:00Z",
    "endsAt": "2026-06-19T11:00:00Z",
    "comment": "Planned maintenance window",
    "createdBy": "ops-team"
  }'
```

### Alert Testing

Regular alert testing ensures reliability:

```bash
# Test alert delivery
# 1. Simulate high latency
curl -X POST http://localhost:8000/test/slow-endpoint

# 2. Simulate high error rate
curl -X POST http://localhost:8000/test/error-endpoint

# 3. Verify alert received in #ops-alerts
# 4. Verify escalation to #ops-lead if not acknowledged
```

## Database Query Profiling

### Run Profiling Script

```bash
python scripts/performance/profile_db_queries.py
```

This script:
- Scans all router and service files
- Detects queries inside loops (potential N+1 issues)
- Reports total query counts and line numbers
- Provides recommendations for optimization

### Current Findings

As of v0.5.0:
- `admin.py`: 8 session.execute calls (stats, list jobs)
- `users.py`: 4 session.execute calls (register, login, profile)
- No N+1 issues detected in current codebase

## Performance Optimization Checklist

### Database Optimization

- [ ] Add indexes to frequently queried columns
- [ ] Optimize slow queries (EXPLAIN ANALYZE)
- [ ] Implement connection pooling
- [ ] Enable query caching where appropriate
- [ ] Monitor connection pool usage

### API Optimization

- [ ] Implement response caching
- [ ] Add pagination to list endpoints
- [ ] Optimize serialization (use orjson)
- [ ] Implement async operations where possible
- [ ] Add rate limiting to prevent abuse

### Infrastructure Optimization

- [ ] Enable HTTP/2
- [ ] Implement CDN for static assets
- [ ] Use compression (gzip, brotli)
- [ ] Optimize TLS configuration
- [ ] Implement load balancing

## Troubleshooting

### High Response Times

**Symptoms:** API endpoints responding slowly (> 500ms)

**Investigation:**
```bash
# Check database query performance
python scripts/performance/profile_db_queries.py

# Check slow queries in PostgreSQL
sudo -u postgres psql -c "SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"

# Check system resources
htop
iostat -x 1
vmstat 1
```

**Solutions:**
- Add database indexes
- Optimize queries
- Increase connection pool size
- Add caching
- Scale horizontally

### High Error Rates

**Symptoms:** 5xx errors increasing during load tests

**Investigation:**
```bash
# Check error logs
journalctl -u aitbc-coordinator-api -f

# Check error metrics
curl http://localhost:8000/prometheus | grep http_errors_total

# Check service health
curl http://localhost:8000/health
```

**Solutions:**
- Fix application errors
- Increase timeout values
- Add retry logic
- Implement circuit breakers
- Scale resources

### Memory Issues

**Symptoms:** Service crashes or OOM during load tests

**Investigation:**
```bash
# Check memory usage
systemctl status aitbc-coordinator-api
memory_peak=$(systemctl show aitbc-coordinator-api --property=MemoryPeak)

# Check for memory leaks
valgrind --leak-check=full python -m app.main

# Profile memory usage
python -m memory_profiler app.main
```

**Solutions:**
- Fix memory leaks
- Optimize data structures
- Increase memory limits
- Implement pagination
- Use streaming for large responses

## Performance Targets

### Acceptable Performance

For v0.5.0, the following performance targets are considered acceptable:

| Metric | Target | Acceptable Range |
|--------|--------|------------------|
| Job Submit RPS | 100 | 80-120 |
| Heartbeat RPS | 1000 | 800-1200 |
| Response Time (p50) | < 50ms | < 100ms |
| Response Time (p95) | < 200ms | < 500ms |
| Response Time (p99) | < 500ms | < 1000ms |
| Error Rate | < 1% | < 5% |
| CPU Usage | < 70% | < 90% |
| Memory Usage | < 80% | < 95% |

### Degraded Performance

If metrics fall outside acceptable range:

1. **Immediate Action:** Scale resources or reduce load
2. **Investigation:** Identify bottleneck (database, network, application)
3. **Optimization:** Apply performance improvements
4. **Retest:** Measure after changes
5. **Monitor:** Continuously track performance

## Reporting

### Load Test Report Template

```markdown
# Load Test Report - [Date]

## Test Configuration
- Test Type: [Normal/Stress/Spike]
- Users: [N]
- Spawn Rate: [N]
- Duration: [N]s
- Target: [URL]

## Results
- Average RPS: [N]
- Peak RPS: [N]
- Average Response Time: [N]ms
- p95 Response Time: [N]ms
- p99 Response Time: [N]ms
- Error Rate: [N]%

## Comparison with Baseline
- RPS Change: [+/- N%]
- Response Time Change: [+/- N%]
- Error Rate Change: [+/- N%]

## Issues Found
- [List any performance issues discovered]

## Recommendations
- [List recommendations for improvement]
```

## See Also

- [Load Test Script](../../tests/load/test_coordinator_api.py)
- [DB Profiling Script](../../scripts/performance/profile_db_queries.py)
- [Load Test Runner](../../scripts/performance/run_load_tests.sh)
- [Monitoring Guide](../deployment/health-checks.md)
