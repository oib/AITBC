"""
AITBC Metrics Module
Provides Prometheus metrics for monitoring
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_client import make_asgi_app
from functools import wraps
import time
from typing import Callable, Any

# Service Information
service_info = Info(
    'service_info',
    'Service information'
)

# Block Processing Metrics
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

# Job Processing Metrics
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

jobs_failed_total = Counter(
    'jobs_failed_total',
    'Total number of failed jobs'
)

jobs_in_queue = Gauge(
    'jobs_in_queue',
    'Number of jobs currently in queue'
)

# API Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Uptime Metrics
service_uptime_seconds = Gauge(
    'service_uptime_seconds',
    'Service uptime in seconds'
)

service_restart_count = Counter(
    'service_restart_count',
    'Number of service restarts'
)


# Decorators for instrumentation
def track_block_processing(func: Callable) -> Callable:
    """Decorator to track block processing time"""
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            block_processing_duration.observe(duration)
            return result
        except Exception as e:
            duration = time.time() - start_time
            block_processing_duration.observe(duration)
            raise e
    return wrapper


def track_job_processing(func: Callable) -> Callable:
    """Decorator to track job processing time"""
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            job_processing_duration.observe(duration)
            jobs_total.labels(status='completed').inc()
            return result
        except Exception as e:
            duration = time.time() - start_time
            job_processing_duration.observe(duration)
            jobs_total.labels(status='failed').inc()
            jobs_failed_total.inc()
            raise e
    return wrapper


def track_http_request(func: Callable) -> Callable:
    """Decorator to track HTTP request duration"""
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            http_request_duration.observe(duration)
            # Extract status from result if available
            if hasattr(result, 'status_code'):
                http_requests_total.labels(
                    method='POST',
                    endpoint='unknown',
                    status=result.status_code
                ).inc()
            return result
        except Exception as e:
            duration = time.time() - start_time
            http_request_duration.observe(duration)
            http_requests_total.labels(
                method='POST',
                endpoint='unknown',
                status=500
            ).inc()
            raise e
    return wrapper


def update_block_height(height: int) -> None:
    """Update blockchain height metric"""
    block_height.set(height)


def update_jobs_in_queue(count: int) -> None:
    """Update jobs in queue metric"""
    jobs_in_queue.set(count)


def increment_service_restarts() -> None:
    """Increment service restart counter"""
    service_restart_count.inc()


# Create ASGI app for metrics endpoint
metrics_app = make_asgi_app()


def setup_service_info(service_name: str, version: str) -> None:
    """Set up service information"""
    service_info.info({
        'service': service_name,
        'version': version
    })
