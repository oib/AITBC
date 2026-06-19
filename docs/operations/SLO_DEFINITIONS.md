# Service Level Objectives (SLOs) and Alert Thresholds

## Coordinator API SLOs

### Performance SLOs
- **p50 latency**: < 10ms
- **p95 latency**: < 50ms
- **p99 latency**: < 200ms
- **p99.9 latency**: < 500ms

### Availability SLOs
- **Uptime**: 99.9% (43.2 minutes downtime/month)
- **Error rate**: < 0.1% (1 error per 1000 requests)

### Throughput SLOs
- **Health endpoint**: > 100 req/s
- **Training job submission**: > 10 req/s (when debug mode enabled)
- **Miner heartbeat**: > 100 req/s

## Alert Thresholds

### Critical Alerts (Page immediately)
- **Error rate > 1%**: Service experiencing significant errors
- **p99 latency > 500ms**: Performance degradation
- **Service down**: Service not responding to health checks
- **Redis connection failure**: State management unavailable

### Warning Alerts (Notify within 15 minutes)
- **Error rate > 0.5%**: Elevated error rate
- **p95 latency > 100ms**: Performance degradation
- **Memory usage > 80%**: Resource pressure
- **CPU usage > 80%**: Resource pressure

### Info Alerts (Log for investigation)
- **Error rate > 0.1%**: Baseline error rate exceeded
- **p95 latency > 50ms**: Performance baseline exceeded
- **Memory usage > 60%**: Resource monitoring
- **CPU usage > 60%**: Resource monitoring

## PrometheusRule Example

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: coordinator-api-alerts
  labels:
    app: coordinator-api
spec:
  groups:
    - name: coordinator-api-critical
      rules:
        - alert: CoordinatorAPIHighErrorRate
          expr: |
            rate(http_requests_total{service="coordinator-api",status=~"5.."}[5m])
            /
            rate(http_requests_total{service="coordinator-api"}[5m]) > 0.01
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Coordinator API error rate > 1%"
            description: "Error rate is {{ $value | humanizePercentage }}"

        - alert: CoordinatorAPIHighLatency
          expr: |
            histogram_quantile(0.99,
              rate(http_request_duration_seconds_bucket{service="coordinator-api"}[5m])
            ) > 0.5
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Coordinator API p99 latency > 500ms"
            description: "p99 latency is {{ $value }}s"

        - alert: CoordinatorAPIDown
          expr: up{job="coordinator-api"} == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Coordinator API is down"
            description: "Service has been down for 1 minute"

        - alert: CoordinatorAPIRedisDown
          expr: redis_up{service="coordinator-api"} == 0
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Coordinator API Redis connection down"
            description: "Redis connection has been down for 1 minute"

    - name: coordinator-api-warning
      rules:
        - alert: CoordinatorAPIElevatedErrorRate
          expr: |
            rate(http_requests_total{service="coordinator-api",status=~"5.."}[5m])
            /
            rate(http_requests_total{service="coordinator-api"}[5m]) > 0.005
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Coordinator API error rate > 0.5%"
            description: "Error rate is {{ $value | humanizePercentage }}"

        - alert: CoordinatorAPIElevatedLatency
          expr: |
            histogram_quantile(0.95,
              rate(http_request_duration_seconds_bucket{service="coordinator-api"}[5m])
            ) > 0.1
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Coordinator API p95 latency > 100ms"
            description: "p95 latency is {{ $value }}s"

        - alert: CoordinatorAPIHighMemory
          expr: |
            container_memory_usage_bytes{container="coordinator-api"}
            /
            container_spec_memory_limit_bytes{container="coordinator-api"} > 0.8
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Coordinator API memory usage > 80%"
            description: "Memory usage is {{ $value | humanizePercentage }}"

        - alert: CoordinatorAPIHighCPU
          expr: |
            rate(container_cpu_usage_seconds_total{container="coordinator-api"}[5m])
            > 0.8
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Coordinator API CPU usage > 80%"
            description: "CPU usage is {{ $value | humanizePercentage }}"
```

## Alertmanager Routing

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'

  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
      continue: false

    - match:
        severity: warning
      receiver: 'slack'
      continue: false

receivers:
  - name: 'default'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/...'
        channel: '#alerts'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '...'
        description: '{{ .CommonAnnotations.summary }}'

  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/...'
        channel: '#alerts'
        title: '{{ .CommonAnnotations.summary }}'
        text: '{{ .CommonAnnotations.description }}'
```

## Implementation Status

- ✅ SLOs defined for coordinator API
- ✅ Alert thresholds defined
- ✅ PrometheusRule example provided
- ✅ Alertmanager routing example provided
- ⏳ Apply to other services (blockchain-node, marketplace)
- ⏳ Deploy to monitoring infrastructure
