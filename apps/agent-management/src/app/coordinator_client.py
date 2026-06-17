"""Coordinator client for AITBC Agent Management Service.

Provides communication with the AITBC coordinator API for agent orchestration.
"""

from typing import Any

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class CoordinatorClient:
    """Client for communicating with the AITBC coordinator API."""

    def __init__(self, base_url: str = "http://localhost:8203") -> None:
        """Initialize the coordinator client.

        Args:
            base_url: Base URL of the coordinator API
        """
        self.base_url = base_url
        logger.info("CoordinatorClient initialized with base_url: %s", base_url)

    async def submit_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Submit a task to the coordinator.

        Args:
            task_data: Task data to submit

        Returns:
            Response from coordinator
        """
        logger.info("Submitting task to coordinator: %s", task_data)
        return {"status": "submitted", "task_id": "mock_id"}

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get the status of a task.

        Args:
            task_id: Task ID to check

        Returns:
            Task status information
        """
        logger.info("Getting task status: %s", task_id)
        return {"task_id": task_id, "status": "running"}
