# Monitor

## Status
✅ Operational

## Overview
System monitoring and alerting service for tracking application health, performance metrics, and generating alerts for critical events.

## Architecture

### Core Components
- **Health Check Service**: Periodic health checks for all services
- **Metrics Collector**: Collects performance metrics from applications
- **Alert Manager**: Manages alert rules and notifications
- **Dashboard**: Web dashboard for monitoring visualization
- **Log Aggregator**: Aggregates logs from all services
- **Notification Service**: Sends alerts via email, Slack, etc.

## Quick Start (End Users)

### Prerequisites
- Python 3.13+
- Access to application endpoints
- Notification service credentials (email, Slack webhook)

### Installation
```bash
cd /opt/aitbc/apps/monitor
.venv/bin/pip install -r requirements.txt
```

### Configuration
Set environment variables in `.env`:
```bash
MONITOR_INTERVAL=60
ALERT_EMAIL=admin@example.com
SLACK_WEBHOOK=https://hooks.slack.com/services/...
PROMETHEUS_URL=http://localhost:9090
```

### Running the Service
```bash
.venv/bin/python main.py
```

### Access Dashboard
Open `http://localhost:8080` in a browser to access the monitoring dashboard.

## Developer Guide

### Development Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Configure monitoring targets
5. Run tests: `pytest tests/`

### Project Structure
```
monitor/
├── src/
│   ├── health_check/        # Health check service
│   ├── metrics_collector/   # Metrics collection
│   ├── alert_manager/       # Alert management
│   ├── dashboard/           # Web dashboard
│   ├── log_aggregator/      # Log aggregation
│   └── notification/        # Notification service
├── tests/                   # Test suite
└── pyproject.toml           # Project configuration
```

### Testing
```bash
# Run all tests
pytest tests/

# Run health check tests
pytest tests/test_health_check.py

# Run alert manager tests
pytest tests/test_alerts.py
```

## API Reference

### Health Checks

#### Run Health Check
```http
GET /api/v1/monitor/health/{service_name}
```

#### Get All Health Status
```http
GET /api/v1/monitor/health
```

#### Add Health Check Target
```http
POST /api/v1/monitor/health/targets
Content-Type: application/json

{
  "service_name": "string",
  "endpoint": "http://localhost:8000/health",
  "interval": 60,
  "timeout": 10
}
```

### Metrics

#### Get Metrics
```http
GET /api/v1/monitor/metrics?service=blockchain-node
```

#### Query Prometheus
```http
POST /api/v1/monitor/metrics/query
Content-Type: application/json

{
  "query": "up{job=\"blockchain-node\"}",
  "range": "1h"
}
```

### Alerts

#### Create Alert Rule
```http
POST /api/v1/monitor/alerts/rules
Content-Type: application/json

{
  "name": "high_cpu_usage",
  "condition": "cpu_usage > 80",
  "duration": 300,
  "severity": "warning|critical",
  "notification": "email|slack"
}
```

#### Get Active Alerts
```http
GET /api/v1/monitor/alerts/active
```

#### Acknowledge Alert
```http
POST /api/v1/monitor/alerts/{alert_id}/acknowledge
```

### Logs

#### Query Logs
```http
POST /api/v1/monitor/logs/query
Content-Type: application/json

{
  "service": "blockchain-node",
  "level": "ERROR",
  "time_range": "1h",
  "query": "error"
}
```

#### Get Log Statistics
```http
GET /api/v1/monitor/logs/stats?service=blockchain-node
```

## Configuration

### Environment Variables
- `MONITOR_INTERVAL`: Interval for health checks (default: 60s)
- `ALERT_EMAIL`: Email address for alert notifications
- `SLACK_WEBHOOK`: Slack webhook for notifications
- `PROMETHEUS_URL`: Prometheus server URL
- `LOG_RETENTION_DAYS`: Log retention period (default: 30 days)
- `ALERT_COOLDOWN`: Alert cooldown period (default: 300s)

### Monitoring Targets
- **Services**: List of services to monitor
- **Endpoints**: Health check endpoints for each service
- **Intervals**: Check intervals for each service

### Alert Rules
- **CPU Usage**: Alert when CPU usage exceeds threshold
- **Memory Usage**: Alert when memory usage exceeds threshold
- **Disk Usage**: Alert when disk usage exceeds threshold
- **Service Down**: Alert when service is unresponsive

## Troubleshooting

**Health check failing**: Verify service endpoint and network connectivity.

**Alerts not triggering**: Check alert rule configuration and notification settings.

**Metrics not collecting**: Verify Prometheus integration and service metrics endpoints.

**Logs not appearing**: Check log aggregation configuration and service log paths.

## Security Notes

- Secure access to monitoring dashboard
- Use authentication for API endpoints
- Encrypt alert notification credentials
- Implement role-based access control
- Regularly review alert rules
- Monitor for unauthorized access attempts
