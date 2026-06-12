"""
Circuit breaker pattern for external services
"""
import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any
from aitbc import get_logger
logger = get_logger(__name__)

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'

class CircuitBreakerError(Exception):
    """Custom exception for circuit breaker failures"""
    pass

class CircuitBreaker:
    """Circuit breaker implementation for external service calls"""

    def __init__(self, failure_threshold: int=5, timeout_seconds: int=60, expected_exception: type[BaseException]=Exception, name: str='circuit_breaker') -> None:
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.expected_exception = expected_exception
        self.name = name
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time: datetime | None = None
        self.success_count = 0
        self.stats = {'total_calls': 0, 'successful_calls': 0, 'failed_calls': 0, 'circuit_opens': 0, 'circuit_closes': 0}

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection"""
        self.stats['total_calls'] += 1
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker '%s' entering HALF_OPEN state", self.name)
            else:
                self.stats['failed_calls'] += 1
                raise CircuitBreakerError(f"Circuit breaker '{self.name}' is OPEN")
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            self.stats['successful_calls'] += 1
            return result
        except Exception as e:
            if not isinstance(e, self.expected_exception):
                raise
            self._on_failure()
            self.stats['failed_calls'] += 1
            logger.warning("Circuit breaker '%s' failure: %s", self.name, e)
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt circuit reset"""
        if self.last_failure_time is None:
            return True
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout_seconds)

    def _on_success(self) -> None:
        """Handle successful call"""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.success_count = 0
            self.stats['circuit_closes'] += 1
            logger.info("Circuit breaker '%s' CLOSED (recovered)", self.name)
        elif self.state == CircuitState.CLOSED:
            self.failures = 0

    def _on_failure(self) -> None:
        """Handle failed call"""
        self.failures += 1
        self.last_failure_time = datetime.now()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.error("Circuit breaker '%s' OPEN (half-open test failed)", self.name)
        elif self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.stats['circuit_opens'] += 1
            logger.error("Circuit breaker '%s' OPEN after %s failures", self.name, self.failures)

    def get_state(self) -> dict[str, Any]:
        """Get current circuit breaker state and statistics"""
        return {'name': self.name, 'state': self.state.value, 'failures': self.failures, 'failure_threshold': self.failure_threshold, 'timeout_seconds': self.timeout_seconds, 'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None, 'stats': self.stats.copy(), 'success_rate': self.stats['successful_calls'] / self.stats['total_calls'] * 100 if self.stats['total_calls'] > 0 else 0}

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state"""
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = None
        self.success_count = 0
        logger.info("Circuit breaker '%s' manually reset to CLOSED", self.name)

def circuit_breaker(failure_threshold: int=5, timeout_seconds: int=60, expected_exception: type[BaseException]=Exception, name: str | None=None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for adding circuit breaker protection to functions"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        breaker_name = name or f'{func.__module__}.{func.__name__}'
        breaker = CircuitBreaker(failure_threshold=failure_threshold, timeout_seconds=timeout_seconds, expected_exception=expected_exception, name=breaker_name)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await breaker.call(func, *args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return asyncio.run(breaker.call(func, *args, **kwargs))
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

class CircuitBreakers:
    """Collection of pre-configured circuit breakers"""

    def __init__(self) -> None:
        self.blockchain_rpc = CircuitBreaker(failure_threshold=3, timeout_seconds=30, expected_exception=ConnectionError, name='blockchain_rpc')
        self.exchange_api = CircuitBreaker(failure_threshold=5, timeout_seconds=60, expected_exception=Exception, name='exchange_api')
        self.wallet_daemon = CircuitBreaker(failure_threshold=3, timeout_seconds=45, expected_exception=ConnectionError, name='wallet_daemon')
        self.payment_processor = CircuitBreaker(failure_threshold=2, timeout_seconds=120, expected_exception=Exception, name='payment_processor')

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Get state of all circuit breakers"""
        return {'blockchain_rpc': self.blockchain_rpc.get_state(), 'exchange_api': self.exchange_api.get_state(), 'wallet_daemon': self.wallet_daemon.get_state(), 'payment_processor': self.payment_processor.get_state()}

    def reset_all(self) -> None:
        """Reset all circuit breakers"""
        self.blockchain_rpc.reset()
        self.exchange_api.reset()
        self.wallet_daemon.reset()
        self.payment_processor.reset()
        logger.info('All circuit breakers reset')
circuit_breakers = CircuitBreakers()

class ProtectedServiceClient:
    """Example of a service client with circuit breaker protection"""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=60, name=f'service_client_{base_url}')

    @circuit_breaker(failure_threshold=3, timeout_seconds=60)
    async def call_api(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """Protected API call"""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(f'{self.base_url}{endpoint}', json=data)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    def get_health_status(self) -> dict[str, Any]:
        """Get health status including circuit breaker state"""
        return {'service_url': self.base_url, 'circuit_breaker': self.circuit_breaker.get_state()}

async def get_circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers (for monitoring)"""
    return circuit_breakers.get_all_states()

async def reset_circuit_breaker(breaker_name: str) -> dict[str, str]:
    """Reset a specific circuit breaker (for admin operations)"""
    breaker_map = {'blockchain_rpc': circuit_breakers.blockchain_rpc, 'exchange_api': circuit_breakers.exchange_api, 'wallet_daemon': circuit_breakers.wallet_daemon, 'payment_processor': circuit_breakers.payment_processor}
    if breaker_name not in breaker_map:
        raise ValueError(f'Unknown circuit breaker: {breaker_name}')
    breaker_map[breaker_name].reset()
    logger.info("Circuit breaker '%s' reset via admin API", breaker_name)
    return {'status': 'reset', 'breaker': breaker_name}

async def monitor_circuit_breakers() -> None:
    """Background task to monitor circuit breaker health"""
    while True:
        try:
            states = circuit_breakers.get_all_states()
            for name, state in states.items():
                if state['state'] == 'open':
                    logger.warning("Circuit breaker '%s' is OPEN - check service health", name)
                elif state['state'] == 'half_open':
                    logger.info("Circuit breaker '%s' is HALF_OPEN - testing recovery", name)
            for name, state in states.items():
                if state['stats']['total_calls'] > 10:
                    success_rate = state['success_rate']
                    if success_rate < 80:
                        logger.warning("Circuit breaker '%s' has low success rate: %s%", name, success_rate)
            await asyncio.sleep(30)
        except Exception as e:
            logger.error('Circuit breaker monitoring error: %s', e)
            await asyncio.sleep(60)