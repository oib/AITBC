import time

from .auth.middleware import security_headers
from .monitoring.prometheus_metrics import performance_monitor


def register_middleware(app):
    @app.middleware("http")
    async def metrics_middleware(request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        performance_monitor.record_request(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
            duration=duration,
        )
        return response

    @app.middleware("http")
    async def security_headers_middleware(request, call_next):
        response = await call_next(request)
        headers = security_headers.get_security_headers()
        for header, value in headers.items():
            response.headers[header] = value
        return response
