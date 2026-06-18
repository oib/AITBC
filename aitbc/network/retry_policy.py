"""
Retry policy with exponential backoff for HTTP client
"""

import asyncio
import time
from typing import Any, Callable

from ..aitbc_logging import get_logger
from ..exceptions import RetryError


class RetryPolicy:
    """Retry policy with exponential backoff"""

    def __init__(self, max_retries: int = 3, enable_logging: bool = False):
        """
        Initialize retry policy.

        Args:
            max_retries: Maximum number of retry attempts
            enable_logging: Enable logging of retry attempts
        """
        self.max_retries = max_retries
        self.enable_logging = enable_logging
        self.logger = get_logger(__name__)

    def execute(self, request_func: Callable, *args, **kwargs) -> Any:
        """
        Execute request with retry logic and exponential backoff.

        Args:
            request_func: Function to execute
            *args: Positional arguments for request_func
            **kwargs: Keyword arguments for request_func

        Returns:
            Result of request_func

        Raises:
            RetryError: If all retry attempts exhausted
        """
        import requests

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    backoff_time = 2 ** (attempt - 1)
                    if self.enable_logging:
                        self.logger.info("Retry attempt %s/%s after %ss backoff", attempt, self.max_retries, backoff_time)
                    time.sleep(backoff_time)
                return request_func(*args, **kwargs)
            except requests.HTTPError as e:
                if e.response is not None and 400 <= e.response.status_code < 500:
                    raise
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
            except requests.RequestException as e:
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
        raise RetryError(f"Request failed: {last_error}")

    async def execute_async(self, request_func: Callable, *args, **kwargs) -> Any:
        """
        Execute async request with retry logic and exponential backoff.

        Args:
            request_func: Async function to execute
            *args: Positional arguments for request_func
            **kwargs: Keyword arguments for request_func

        Returns:
            Result of request_func

        Raises:
            RetryError: If all retry attempts exhausted
        """
        import requests

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    backoff_time = 2 ** (attempt - 1)
                    if self.enable_logging:
                        self.logger.info("Retry attempt %s/%s after %ss backoff", attempt, self.max_retries, backoff_time)
                    await asyncio.sleep(backoff_time)
                return await request_func(*args, **kwargs)
            except requests.HTTPError as e:
                if e.response is not None and 400 <= e.response.status_code < 500:
                    raise
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
            except requests.RequestException as e:
                last_error = e
                if attempt < self.max_retries:
                    if self.enable_logging:
                        self.logger.warning("Request failed (attempt %s/%s): %s", attempt + 1, self.max_retries + 1, e)
                    continue
                else:
                    if self.enable_logging:
                        self.logger.error("All retry attempts exhausted: %s", e)
                    raise RetryError(f"Retry attempts exhausted: {e}") from e
        raise RetryError(f"Request failed: {last_error}")
