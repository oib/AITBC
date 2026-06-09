# AITBC Performance Monitoring Setup

## Overview

This document describes the performance monitoring setup for AITBC, including block processing time, job processing time, and uptime monitoring using systemd services.

## Monitoring Infrastructure

### Components

1. **Prometheus** - Metrics collection and storage (systemd service)
2. **Grafana** - Visualization and dashboards (systemd service)
3. **Node Exporter** - System-level metrics (systemd service)
4. **Custom Metrics Exporters** - Application-specific metrics

### Systemd Service Management

AITBC uses systemd for service orchestration. Monitoring services are managed as systemd units.

#### Starting Monitoring Services

```bash
# Start Prometheus
sudo systemctl start prometheus
sudo systemctl enable prometheus

# Start Grafana
sudo systemctl start grafana
sudo systemctl enable grafana

# Start Node Exporter
sudo systemctl start node-exporter
sudo systemctl enable node-exporter

# Check service status
sudo systemctl status prometheus
sudo systemctl status grafana
sudo systemctl status node-exporter
```

## Block Processing Time Monitoring

### Metrics to Track

- `block_processing_duration_seconds` - Time to process a block
- `block_height` - Current blockchain height
- `block_validation_duration_seconds` - Time to validate a block
- `block_propagation_duration_seconds` - Time to propagate block to peers

### Implementation

Add metrics to blockchain node:

```python
from prometheus_client import Counter, Histogram, Gauge

block_processing_duration = Histogram(
    'block_processing_duration_seconds',
    'Time to process a block',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

block_height = Gauge(
    'block_height',
    'Current blockchain height'
)

block_validation_duration = Histogram(
    'block_validation_duration_seconds',
    'Time to validate a block',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0]
)

block_propagation_duration = Histogram(
    'block_propagation_duration_seconds',
    'Time to propagate block to peers',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)
```

### Monitoring Endpoint

Add `/metrics` endpoint to blockchain node:

```python
from prometheus_client import make_asgi_app

metrics_app = make_asgi_app()

# In FastAPI app
app.mount("/metrics", metrics_app)
```

## Job Processing Time Monitoring

### Metrics to Track

- `job_submission_duration_seconds` - Time to submit a job
- `job_processing_duration_seconds` - Time to complete a job
- `job_queue_duration_seconds` - Time job spends in queue
- `job_execution_duration_seconds` - Time for actual GPU execution
- `jobs_total` - Total number of jobs processed
- `jobs_failed_total` - Total number of failed jobs

### Implementation

Add metrics to coordinator API:

```python
from prometheus_client import Counter, Histogram, Gauge

job_submission_duration = Histogram(
    'job_submission_duration_seconds',
    'Time to submit a job',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

job_processing_duration = Histogram(
    'job_processing_duration_seconds',
    'Time to complete a job from submission to result',
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
)

job_queue_duration = Histogram(
    'job_queue_duration_seconds',
    'Time job spends in queue before assignment',
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0]
)

job_execution_duration = Histogram(
    'job_execution_duration_seconds',
    'Time for actual GPU execution',
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0]
)

jobs_total = Counter(
    'jobs_total',
    'Total number of jobs processed',
    ['status']
)

jobs_in_queue = Gauge(
    'jobs_in_queue',
    'Number of jobs currently in queue'
)
```

### Instrumentation Points

1. **Job Submission** - Track submission duration
2. **Job Assignment** - Track queue duration
3. **Job Execution** - Track execution duration
4. **Job Completion** - Track total processing duration

## Uptime Monitoring

### Metrics to Track

- `up` - Service availability (1 = up, 0 = down)
- `service_uptime_seconds` - Total uptime duration
- `service_downtime_seconds` - Total downtime duration
- `service_restart_count` - Number of service restarts

### Implementation

Use Prometheus blackbox exporter for external uptime monitoring:

```yaml
scrape_configs:
  - job_name: 'blackbox'
    metrics_path: /probe
    params:
      module: [http_2xx]
    static_configs:
      - targets:
        - http://coordinator-api:8203/v1/health
        - http://blockchain-node:8080/v1/health
        - http://marketplace:8102/v1/health
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
        replacement: '$1'
```

### Internal Uptime Metrics

Add to each service:

```python
from prometheus_client import Gauge, Counter

service_uptime = Gauge(
    'service_uptime_seconds',
    'Service uptime in seconds'
)

service_restart_count = Counter(
    'service_restart_count',
    'Number of service restarts'
)
```

## Alerting Rules

### Critical Alerts

```yaml
groups:
  - name: critical
    rules:
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.instance }} is down"
          
      - alert: BlockProcessingTooSlow
        expr: histogram_quantile(0.95, block_processing_duration_seconds) > 1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Block processing time exceeds 1s (p95)"
          
      - alert: JobProcessingTooSlow
        expr: histogram_quantile(0.95, job_processing_duration_seconds) > 5
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Job processing time exceeds 5s (p95)"
```

### Warning Alerts

```yaml
  - name: warnings
    rules:
      - alert: HighJobQueue
        expr: jobs_in_queue > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Job queue backlog exceeds 100 jobs"
          
      - alert: HighFailureRate
        expr: rate(jobs_failed_total[5m]) / rate(jobs_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Job failure rate exceeds 5%"
```

## Grafana Dashboards

### Dashboard: AITBC System Overview

**Panels:**
1. Service Uptime (uptime gauge)
2. Request Rate (requests per second)
3. Error Rate (errors per second)
4. Response Time (p50, p95, p99)
5. Queue Length (jobs in queue)
6. Blockchain Height (current block)
7. Block Processing Time (histogram)
8. Job Processing Time (histogram)

### Dashboard: Blockchain Performance

**Panels:**
1. Block Processing Time (p95)
2. Block Validation Time (p95)
3. Block Propagation Time (p95)
4. Block Height (current)
5. Transactions per Block
6. Network Peer Count

### Dashboard: Job Processing Performance

**Panels:**
1. Job Submission Rate (jobs/second)
2. Job Processing Time (p95)
3. Job Queue Duration (p95)
4. Job Execution Time (p95)
5. Jobs in Queue (current)
6. Job Success Rate (percentage)

## Installation

### Prerequisites

```bash
# Install Prometheus (available in Debian stable)
sudo apt update
sudo apt install prometheus promtool prometheus-node-exporter

# Grafana is NOT available in Debian stable
# Install from official Grafana repository or download .deb
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt update
sudo apt install grafana
```

### Setup

```bash
# Create systemd service for Prometheus
sudo tee /etc/systemd/system/prometheus.service > /dev/null <<EOF
[Unit]
Description=Prometheus
After=network.target

[Service]
Type=simple
User=prometheus
ExecStart=/usr/local/bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo useradd --no-create-home --shell /bin/false prometheus
sudo chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus
sudo systemctl daemon-reload
sudo systemctl enable prometheus
sudo systemctl start prometheus

# Access Grafana
# URL: http://localhost:3000
# Username: admin
# Password: admin
```

### Import Dashboards

1. Navigate to Grafana
2. Go to Dashboards → Import
3. Import dashboard JSON files from `infra/monitoring/grafana/dashboards/`

## Configuration Files

### Prometheus Config

Location: `infra/monitoring/prometheus.yml`

### Grafana Datasources

Location: `infra/monitoring/grafana/datasources/prometheus.yml`

### Grafana Dashboards

Location: `infra/monitoring/grafana/dashboards/`

## Testing

### Verify Metrics Endpoint

```bash
# Test coordinator API metrics
curl http://localhost:8203/metrics

# Test blockchain node metrics
curl http://localhost:8080/metrics

# Test marketplace metrics
curl http://localhost:8102/metrics
```

### Verify Prometheus

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Query metrics
curl http://localhost:9090/api/v1/query?query=up
```

## Maintenance

### Regular Tasks

1. **Review Alerts** - Weekly review of alert rules
2. **Update Dashboards** - Monthly dashboard updates
3. **Review Retention** - Quarterly review of data retention policies
4. **Capacity Planning** - Quarterly review of storage needs

### Backup

```bash
# Backup Prometheus data
sudo tar -czf /tmp/prometheus-backup.tar.gz /var/lib/prometheus

# Backup Grafana data
sudo tar -czf /tmp/grafana-backup.tar.gz /var/lib/grafana
```

## Troubleshooting

### Metrics Not Appearing

1. Check service is running: `sudo systemctl status prometheus`
2. Check metrics endpoint: `curl http://service:port/metrics`
3. Check Prometheus logs: `sudo journalctl -u prometheus -n 50`
4. Check Prometheus targets: http://localhost:9090/targets

### High Memory Usage

1. Reduce retention period in prometheus.yml
2. Reduce scrape interval
3. Add more storage to Prometheus

### Alerts Not Firing

1. Check alert rules syntax
2. Check alert manager configuration
3. Check Grafana notification channels

### Service Won't Start

1. Check service logs: `sudo journalctl -u [service] -n 50`
2. Check configuration: `sudo systemctl cat [service]`
3. Check port conflicts: `sudo netstat -tulpn`

## Next Steps

1. Implement metrics instrumentation in services
2. Create Grafana dashboards
3. Set up alert notifications
4. Configure external uptime monitoring (e.g., UptimeRobot, Pingdom)
5. Integrate with incident management system
