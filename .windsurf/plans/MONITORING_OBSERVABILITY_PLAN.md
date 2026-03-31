# Monitoring & Observability Implementation Plan

## 🎯 **Objective**
Implement comprehensive monitoring and observability to ensure system reliability, performance, and maintainability.

## 🔴 **Critical Priority - 4 Week Implementation**

---

## 📋 **Phase 1: Metrics Collection (Week 1-2)**

### **1.1 Prometheus Metrics Setup**
```python
# File: apps/coordinator-api/src/app/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_client.fastapi import metrics
from fastapi import FastAPI
import time
from functools import wraps

class ApplicationMetrics:
    def __init__(self):
        # Request metrics
        self.request_count = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code']
        )
        
        self.request_duration = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'endpoint']
        )
        
        # Business metrics
        self.active_users = Gauge(
            'active_users_total',
            'Number of active users'
        )
        
        self.ai_operations = Counter(
            'ai_operations_total',
            'Total AI operations performed',
            ['operation_type', 'status']
        )
        
        self.blockchain_transactions = Counter(
            'blockchain_transactions_total',
            'Total blockchain transactions',
            ['transaction_type', 'status']
        )
        
        # System metrics
        self.database_connections = Gauge(
            'database_connections_active',
            'Active database connections'
        )
        
        self.cache_hit_ratio = Gauge(
            'cache_hit_ratio',
            'Cache hit ratio'
        )
    
    def track_request(self, func):
        """Decorator to track request metrics"""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            method = kwargs.get('method', 'unknown')
            endpoint = kwargs.get('endpoint', 'unknown')
            
            try:
                result = await func(*args, **kwargs)
                status_code = getattr(result, 'status_code', 200)
                self.request_count.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
                return result
            except Exception as e:
                self.request_count.labels(method=method, endpoint=endpoint, status_code=500).inc()
                raise
            finally:
                duration = time.time() - start_time
                self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)
        
        return wrapper

# Initialize metrics
metrics_collector = ApplicationMetrics()

# FastAPI integration
app = FastAPI()

# Add default FastAPI metrics
metrics(app)

# Custom metrics endpoint
@app.get("/metrics")
async def custom_metrics():
    from prometheus_client import generate_latest
    return Response(generate_latest(), media_type="text/plain")
```

### **1.2 Business Metrics Collection**
```python
# File: apps/coordinator-api/src/app/monitoring/business_metrics.py
from sqlalchemy import func
from sqlmodel import Session
from datetime import datetime, timedelta
from typing import Dict, Any

class BusinessMetricsCollector:
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def get_user_metrics(self) -> Dict[str, Any]:
        """Collect user-related business metrics"""
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(weeks=1)
        
        # Daily active users
        daily_active = self.db.query(func.count(func.distinct(User.id)))\
            .filter(User.last_login >= day_ago).scalar()
        
        # Weekly active users
        weekly_active = self.db.query(func.count(func.distinct(User.id)))\
            .filter(User.last_login >= week_ago).scalar()
        
        # Total users
        total_users = self.db.query(func.count(User.id)).scalar()
        
        # New users today
        new_users_today = self.db.query(func.count(User.id))\
            .filter(User.created_at >= day_ago).scalar()
        
        return {
            'daily_active_users': daily_active,
            'weekly_active_users': weekly_active,
            'total_users': total_users,
            'new_users_today': new_users_today
        }
    
    def get_ai_operation_metrics(self) -> Dict[str, Any]:
        """Collect AI operation metrics"""
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        
        # Daily AI operations
        daily_operations = self.db.query(AIOperation)\
            .filter(AIOperation.created_at >= day_ago).all()
        
        # Operations by type
        operations_by_type = {}
        for op in daily_operations:
            op_type = op.operation_type
            if op_type not in operations_by_type:
                operations_by_type[op_type] = {'total': 0, 'success': 0, 'failed': 0}
            
            operations_by_type[op_type]['total'] += 1
            if op.status == 'success':
                operations_by_type[op_type]['success'] += 1
            else:
                operations_by_type[op_type]['failed'] += 1
        
        # Average processing time
        avg_processing_time = self.db.query(func.avg(AIOperation.processing_time))\
            .filter(AIOperation.created_at >= day_ago).scalar() or 0
        
        return {
            'daily_operations': len(daily_operations),
            'operations_by_type': operations_by_type,
            'avg_processing_time': float(avg_processing_time)
        }
    
    def get_blockchain_metrics(self) -> Dict[str, Any]:
        """Collect blockchain-related metrics"""
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        
        # Daily transactions
        daily_transactions = self.db.query(BlockchainTransaction)\
            .filter(BlockchainTransaction.created_at >= day_ago).all()
        
        # Transactions by type
        transactions_by_type = {}
        for tx in daily_transactions:
            tx_type = tx.transaction_type
            if tx_type not in transactions_by_type:
                transactions_by_type[tx_type] = 0
            transactions_by_type[tx_type] += 1
        
        # Average confirmation time
        avg_confirmation_time = self.db.query(func.avg(BlockchainTransaction.confirmation_time))\
            .filter(BlockchainTransaction.created_at >= day_ago).scalar() or 0
        
        # Failed transactions
        failed_transactions = self.db.query(func.count(BlockchainTransaction.id))\
            .filter(BlockchainTransaction.created_at >= day_ago)\
            .filter(BlockchainTransaction.status == 'failed').scalar()
        
        return {
            'daily_transactions': len(daily_transactions),
            'transactions_by_type': transactions_by_type,
            'avg_confirmation_time': float(avg_confirmation_time),
            'failed_transactions': failed_transactions
        }

# Metrics collection endpoint
@app.get("/metrics/business")
async def business_metrics():
    collector = BusinessMetricsCollector(get_db_session())
    
    metrics = {
        'timestamp': datetime.utcnow().isoformat(),
        'users': collector.get_user_metrics(),
        'ai_operations': collector.get_ai_operation_metrics(),
        'blockchain': collector.get_blockchain_metrics()
    }
    
    return metrics
```

### **1.3 Custom Application Metrics**
```python
# File: apps/coordinator-api/src/app/monitoring/custom_metrics.py
from prometheus_client import Counter, Histogram, Gauge
from contextlib import asynccontextmanager

class CustomMetrics:
    def __init__(self):
        # AI service metrics
        self.ai_model_inference_time = Histogram(
            'ai_model_inference_duration_seconds',
            'Time spent on AI model inference',
            ['model_name', 'model_type']
        )
        
        self.ai_model_requests = Counter(
            'ai_model_requests_total',
            'Total AI model requests',
            ['model_name', 'model_type', 'status']
        )
        
        # Blockchain metrics
        self.block_sync_time = Histogram(
            'block_sync_duration_seconds',
            'Time to sync blockchain blocks'
        )
        
        self.transaction_queue_size = Gauge(
            'transaction_queue_size',
            'Number of transactions in queue'
        )
        
        # Database metrics
        self.query_execution_time = Histogram(
            'database_query_duration_seconds',
            'Database query execution time',
            ['query_type', 'table']
        )
        
        self.cache_operations = Counter(
            'cache_operations_total',
            'Total cache operations',
            ['operation', 'result']
        )
    
    @asynccontextmanager
    async def time_ai_inference(self, model_name: str, model_type: str):
        """Context manager for timing AI inference"""
        start_time = time.time()
        try:
            yield
            self.ai_model_requests.labels(
                model_name=model_name,
                model_type=model_type,
                status='success'
            ).inc()
        except Exception:
            self.ai_model_requests.labels(
                model_name=model_name,
                model_type=model_type,
                status='error'
            ).inc()
            raise
        finally:
            duration = time.time() - start_time
            self.ai_model_inference_time.labels(
                model_name=model_name,
                model_type=model_type
            ).observe(duration)
    
    @asynccontextmanager
    async def time_database_query(self, query_type: str, table: str):
        """Context manager for timing database queries"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.query_execution_time.labels(
                query_type=query_type,
                table=table
            ).observe(duration)

# Usage in services
custom_metrics = CustomMetrics()

class AIService:
    async def process_request(self, request: dict):
        model_name = request.get('model', 'default')
        model_type = request.get('type', 'text')
        
        async with custom_metrics.time_ai_inference(model_name, model_type):
            # AI processing logic
            result = await self.ai_model.process(request)
        
        return result
```

---

## 📋 **Phase 2: Logging & Alerting (Week 2-3)**

### **2.1 Structured Logging Setup**
```python
# File: apps/coordinator-api/src/app/logging/structured_logging.py
import structlog
import logging
from pythonjsonlogger import jsonlogger
from typing import Dict, Any
import uuid
from fastapi import Request

# Configure structured logging
def configure_logging():
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    json_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s'
    )
    
    handler = logging.StreamHandler()
    handler.setFormatter(json_formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

# Request correlation middleware
class CorrelationIDMiddleware:
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Generate or extract correlation ID
            correlation_id = scope.get("headers", {}).get(b"x-correlation-id")
            if correlation_id:
                correlation_id = correlation_id.decode()
            else:
                correlation_id = str(uuid.uuid4())
            
            # Add to request state
            scope["state"] = scope.get("state", {})
            scope["state"]["correlation_id"] = correlation_id
            
            # Add correlation ID to response headers
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-correlation-id", correlation_id.encode()))
                    message["headers"] = headers
                await send(message)
            
            await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)

# Logging context manager
class LoggingContext:
    def __init__(self, logger, **kwargs):
        self.logger = logger
        self.context = kwargs
    
    def __enter__(self):
        return self.logger.bind(**self.context)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.error("Exception occurred", exc_info=(exc_type, exc_val, exc_tb))

# Usage in services
logger = structlog.get_logger()

class AIService:
    async def process_request(self, request_id: str, user_id: str, request: dict):
        with LoggingContext(logger, request_id=request_id, user_id=user_id, service="ai_service"):
            logger.info("Processing AI request", request_type=request.get('type'))
            
            try:
                result = await self.ai_model.process(request)
                logger.info("AI request processed successfully", 
                           model=request.get('model'), 
                           processing_time=result.get('duration'))
                return result
            except Exception as e:
                logger.error("AI request failed", error=str(e), error_type=type(e).__name__)
                raise
```

### **2.2 Alert Management System**
```python
# File: apps/coordinator-api/src/app/monitoring/alerts.py
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import asyncio
import aiohttp
from dataclasses import dataclass

class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertStatus(str, Enum):
    FIRING = "firing"
    RESOLVED = "resolved"
    SILENCED = "silenced"

@dataclass
class Alert:
    name: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    starts_at: datetime
    ends_at: Optional[datetime] = None
    fingerprint: str = ""

class AlertManager:
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.notification_channels = []
        self.alert_rules = []
    
    def add_notification_channel(self, channel):
        """Add notification channel (Slack, email, PagerDuty, etc.)"""
        self.notification_channels.append(channel)
    
    def add_alert_rule(self, rule):
        """Add alert rule"""
        self.alert_rules.append(rule)
    
    async def check_alert_rules(self):
        """Check all alert rules and create alerts if needed"""
        for rule in self.alert_rules:
            try:
                should_fire = await rule.evaluate()
                alert_key = rule.get_alert_key()
                
                if should_fire and alert_key not in self.alerts:
                    # Create new alert
                    alert = Alert(
                        name=rule.name,
                        severity=rule.severity,
                        status=AlertStatus.FIRING,
                        message=rule.message,
                        labels=rule.labels,
                        annotations=rule.annotations,
                        starts_at=datetime.utcnow(),
                        fingerprint=alert_key
                    )
                    
                    self.alerts[alert_key] = alert
                    await self.send_notifications(alert)
                
                elif not should_fire and alert_key in self.alerts:
                    # Resolve alert
                    alert = self.alerts[alert_key]
                    alert.status = AlertStatus.RESOLVED
                    alert.ends_at = datetime.utcnow()
                    await self.send_notifications(alert)
                    del self.alerts[alert_key]
                    
            except Exception as e:
                logger.error("Error evaluating alert rule", rule=rule.name, error=str(e))
    
    async def send_notifications(self, alert: Alert):
        """Send alert to all notification channels"""
        for channel in self.notification_channels:
            try:
                await channel.send_notification(alert)
            except Exception as e:
                logger.error("Error sending notification", 
                           channel=channel.__class__.__name__, 
                           error=str(e))

# Alert rule examples
class HighErrorRateRule:
    def __init__(self):
        self.name = "HighErrorRate"
        self.severity = AlertSeverity.HIGH
        self.message = "Error rate is above 5%"
        self.labels = {"service": "coordinator-api", "type": "error_rate"}
        self.annotations = {"description": "Error rate has exceeded 5% threshold"}
    
    async def evaluate(self) -> bool:
        # Get error rate from metrics
        error_rate = await self.get_error_rate()
        return error_rate > 0.05  # 5%
    
    async def get_error_rate(self) -> float:
        # Query Prometheus for error rate
        # Implementation depends on your metrics setup
        return 0.0  # Placeholder
    
    def get_alert_key(self) -> str:
        return f"{self.name}:{self.labels['service']}"

# Notification channels
class SlackNotificationChannel:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send_notification(self, alert: Alert):
        payload = {
            "text": f"🚨 {alert.severity.upper()} Alert: {alert.name}",
            "attachments": [{
                "color": self.get_color(alert.severity),
                "fields": [
                    {"title": "Message", "value": alert.message, "short": False},
                    {"title": "Severity", "value": alert.severity.value, "short": True},
                    {"title": "Status", "value": alert.status.value, "short": True},
                    {"title": "Started", "value": alert.starts_at.isoformat(), "short": True}
                ]
            }]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.webhook_url, json=payload) as response:
                if response.status != 200:
                    raise Exception(f"Failed to send Slack notification: {response.status}")
    
    def get_color(self, severity: AlertSeverity) -> str:
        colors = {
            AlertSeverity.LOW: "good",
            AlertSeverity.MEDIUM: "warning",
            AlertSeverity.HIGH: "danger",
            AlertSeverity.CRITICAL: "danger"
        }
        return colors.get(severity, "good")

# Initialize alert manager
alert_manager = AlertManager()

# Add notification channels
# alert_manager.add_notification_channel(SlackNotificationChannel(slack_webhook_url))

# Add alert rules
# alert_manager.add_alert_rule(HighErrorRateRule())
```

---

## 📋 **Phase 3: Health Checks & SLA (Week 3-4)**

### **3.1 Comprehensive Health Checks**
```python
# File: apps/coordinator-api/src/app/health/health_checks.py
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime
from enum import Enum
import asyncio
from sqlalchemy import text

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class HealthCheck:
    def __init__(self, name: str, check_function, timeout: float = 5.0):
        self.name = name
        self.check_function = check_function
        self.timeout = timeout
    
    async def run(self) -> Dict[str, Any]:
        start_time = datetime.utcnow()
        try:
            result = await asyncio.wait_for(self.check_function(), timeout=self.timeout)
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "name": self.name,
                "status": HealthStatus.HEALTHY,
                "message": "OK",
                "duration": duration,
                "timestamp": start_time.isoformat(),
                "details": result
            }
        except asyncio.TimeoutError:
            duration = (datetime.utcnow() - start_time).total_seconds()
            return {
                "name": self.name,
                "status": HealthStatus.UNHEALTHY,
                "message": "Timeout",
                "duration": duration,
                "timestamp": start_time.isoformat()
            }
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            return {
                "name": self.name,
                "status": HealthStatus.UNHEALTHY,
                "message": str(e),
                "duration": duration,
                "timestamp": start_time.isoformat()
            }

class HealthChecker:
    def __init__(self):
        self.checks: List[HealthCheck] = []
    
    def add_check(self, check: HealthCheck):
        self.checks.append(check)
    
    async def run_all_checks(self) -> Dict[str, Any]:
        results = await asyncio.gather(*[check.run() for check in self.checks])
        
        overall_status = HealthStatus.HEALTHY
        failed_checks = []
        
        for result in results:
            if result["status"] == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                failed_checks.append(result["name"])
            elif result["status"] == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED
        
        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": results,
            "failed_checks": failed_checks,
            "total_checks": len(self.checks),
            "passed_checks": len(self.checks) - len(failed_checks)
        }

# Health check implementations
async def database_health_check():
    """Check database connectivity"""
    async with get_db_session() as session:
        result = await session.execute(text("SELECT 1"))
        return {"database": "connected", "query_result": result.scalar()}

async def redis_health_check():
    """Check Redis connectivity"""
    redis_client = get_redis_client()
    await redis_client.ping()
    return {"redis": "connected"}

async def external_api_health_check():
    """Check external API connectivity"""
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.openai.com/v1/models", timeout=5) as response:
            if response.status == 200:
                return {"openai_api": "connected", "status_code": response.status}
            else:
                raise Exception(f"API returned status {response.status}")

async def ai_service_health_check():
    """Check AI service health"""
    # Test AI model availability
    model = get_ai_model()
    test_result = await model.test_inference("test input")
    return {"ai_service": "healthy", "model_response_time": test_result.get("duration")}

async def blockchain_health_check():
    """Check blockchain connectivity"""
    blockchain_client = get_blockchain_client()
    latest_block = blockchain_client.get_latest_block()
    return {
        "blockchain": "connected",
        "latest_block": latest_block.number,
        "block_time": latest_block.timestamp
    }

# Initialize health checker
health_checker = HealthChecker()

# Add health checks
health_checker.add_check(HealthCheck("database", database_health_check))
health_checker.add_check(HealthCheck("redis", redis_health_check))
health_checker.add_check(HealthCheck("external_api", external_api_health_check))
health_checker.add_check(HealthCheck("ai_service", ai_service_health_check))
health_checker.add_check(HealthCheck("blockchain", blockchain_health_check))

# Health check endpoints
health_router = APIRouter(prefix="/health", tags=["health"])

@health_router.get("/")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@health_router.get("/detailed")
async def detailed_health_check():
    """Detailed health check with all components"""
    return await health_checker.run_all_checks()

@health_router.get("/readiness")
async def readiness_check():
    """Readiness probe for Kubernetes"""
    result = await health_checker.run_all_checks()
    
    if result["status"] == HealthStatus.HEALTHY:
        return {"status": "ready"}
    else:
        raise HTTPException(status_code=503, detail="Service not ready")

@health_router.get("/liveness")
async def liveness_check():
    """Liveness probe for Kubernetes"""
    # Simple check if the service is responsive
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
```

### **3.2 SLA Monitoring**
```python
# File: apps/coordinator-api/src/app/monitoring/sla.py
from datetime import datetime, timedelta
from typing import Dict, Any, List
from dataclasses import dataclass
from enum import Enum

class SLAStatus(str, Enum):
    COMPLIANT = "compliant"
    VIOLATED = "violated"
    WARNING = "warning"

@dataclass
class SLAMetric:
    name: str
    target: float
    current: float
    unit: str
    status: SLAStatus
    measurement_period: str

class SLAMonitor:
    def __init__(self):
        self.metrics: Dict[str, SLAMetric] = {}
        self.sla_definitions = {
            "availability": {"target": 99.9, "unit": "%", "period": "30d"},
            "response_time": {"target": 200, "unit": "ms", "period": "24h"},
            "error_rate": {"target": 1.0, "unit": "%", "period": "24h"},
            "throughput": {"target": 1000, "unit": "req/s", "period": "1h"}
        }
    
    async def calculate_availability(self) -> SLAMetric:
        """Calculate service availability"""
        # Get uptime data from the last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Query metrics for availability
        total_time = 30 * 24 * 60 * 60  # 30 days in seconds
        downtime = await self.get_downtime(thirty_days_ago)
        uptime = total_time - downtime
        
        availability = (uptime / total_time) * 100
        
        target = self.sla_definitions["availability"]["target"]
        status = self.get_sla_status(availability, target)
        
        return SLAMetric(
            name="availability",
            target=target,
            current=availability,
            unit="%",
            status=status,
            measurement_period="30d"
        )
    
    async def calculate_response_time(self) -> SLAMetric:
        """Calculate average response time"""
        # Get response time metrics from the last 24 hours
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        
        # Query Prometheus for average response time
        avg_response_time = await self.get_average_response_time(twenty_four_hours_ago)
        
        target = self.sla_definitions["response_time"]["target"]
        status = self.get_sla_status(avg_response_time, target, reverse=True)
        
        return SLAMetric(
            name="response_time",
            target=target,
            current=avg_response_time,
            unit="ms",
            status=status,
            measurement_period="24h"
        )
    
    async def calculate_error_rate(self) -> SLAMetric:
        """Calculate error rate"""
        # Get error metrics from the last 24 hours
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        
        total_requests = await self.get_total_requests(twenty_four_hours_ago)
        error_requests = await self.get_error_requests(twenty_four_hours_ago)
        
        error_rate = (error_requests / total_requests) * 100 if total_requests > 0 else 0
        
        target = self.sla_definitions["error_rate"]["target"]
        status = self.get_sla_status(error_rate, target, reverse=True)
        
        return SLAMetric(
            name="error_rate",
            target=target,
            current=error_rate,
            unit="%",
            status=status,
            measurement_period="24h"
        )
    
    async def calculate_throughput(self) -> SLAMetric:
        """Calculate system throughput"""
        # Get request metrics from the last hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        requests_per_hour = await self.get_total_requests(one_hour_ago)
        requests_per_second = requests_per_hour / 3600
        
        target = self.sla_definitions["throughput"]["target"]
        status = self.get_sla_status(requests_per_second, target)
        
        return SLAMetric(
            name="throughput",
            target=target,
            current=requests_per_second,
            unit="req/s",
            status=status,
            measurement_period="1h"
        )
    
    def get_sla_status(self, current: float, target: float, reverse: bool = False) -> SLAStatus:
        """Determine SLA status based on current and target values"""
        if reverse:
            # For metrics where lower is better (response time, error rate)
            if current <= target:
                return SLAStatus.COMPLIANT
            elif current <= target * 1.1:  # 10% tolerance
                return SLAStatus.WARNING
            else:
                return SLAStatus.VIOLATED
        else:
            # For metrics where higher is better (availability, throughput)
            if current >= target:
                return SLAStatus.COMPLIANT
            elif current >= target * 0.9:  # 10% tolerance
                return SLAStatus.WARNING
            else:
                return SLAStatus.VIOLATED
    
    async def get_sla_report(self) -> Dict[str, Any]:
        """Generate comprehensive SLA report"""
        metrics = await asyncio.gather(
            self.calculate_availability(),
            self.calculate_response_time(),
            self.calculate_error_rate(),
            self.calculate_throughput()
        )
        
        # Calculate overall SLA status
        overall_status = SLAStatus.COMPLIANT
        for metric in metrics:
            if metric.status == SLAStatus.VIOLATED:
                overall_status = SLAStatus.VIOLATED
                break
            elif metric.status == SLAStatus.WARNING and overall_status == SLAStatus.COMPLIANT:
                overall_status = SLAStatus.WARNING
        
        return {
            "overall_status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {metric.name: metric for metric in metrics},
            "sla_definitions": self.sla_definitions
        }

# SLA monitoring endpoints
@router.get("/monitoring/sla")
async def sla_report():
    """Get SLA compliance report"""
    monitor = SLAMonitor()
    return await monitor.get_sla_report()

@router.get("/monitoring/sla/{metric_name}")
async def get_sla_metric(metric_name: str):
    """Get specific SLA metric"""
    monitor = SLAMonitor()
    
    if metric_name == "availability":
        return await monitor.calculate_availability()
    elif metric_name == "response_time":
        return await monitor.calculate_response_time()
    elif metric_name == "error_rate":
        return await monitor.calculate_error_rate()
    elif metric_name == "throughput":
        return await monitor.calculate_throughput()
    else:
        raise HTTPException(status_code=404, detail=f"Metric {metric_name} not found")
```

---

## 🎯 **Success Metrics & Testing**

### **Monitoring Testing Checklist**
```bash
# 1. Metrics collection testing
curl http://localhost:8000/metrics
curl http://localhost:8000/metrics/business

# 2. Health check testing
curl http://localhost:8000/health/
curl http://localhost:8000/health/detailed
curl http://localhost:8000/health/readiness
curl http://localhost:8000/health/liveness

# 3. SLA monitoring testing
curl http://localhost:8000/monitoring/sla
curl http://localhost:8000/monitoring/sla/availability

# 4. Alert system testing
# - Trigger alert conditions
# - Verify notification delivery
# - Test alert resolution
```

### **Performance Requirements**
- Metrics collection overhead < 5% CPU
- Health check response < 100ms
- SLA calculation < 500ms
- Alert delivery < 30 seconds

### **Reliability Requirements**
- 99.9% monitoring system availability
- Complete audit trail for all alerts
- Redundant monitoring infrastructure
- Automated failover for monitoring components

---

## 📅 **Implementation Timeline**

### **Week 1**
- [ ] Prometheus metrics setup
- [ ] Business metrics collection
- [ ] Custom application metrics

### **Week 2**
- [ ] Structured logging implementation
- [ ] Alert management system
- [ ] Notification channel setup

### **Week 3**
- [ ] Comprehensive health checks
- [ ] SLA monitoring implementation
- [ ] Dashboard configuration

### **Week 4**
- [ ] Testing and validation
- [ ] Documentation and deployment
- [ ] Performance optimization

---

**Last Updated**: March 31, 2026  
**Owner**: Infrastructure Team  
**Review Date**: April 7, 2026
