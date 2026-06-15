"""
Orchestration protocols for agent workflow execution.
These protocols define the interface for agent orchestration services.
"""

from abc import ABC, abstractmethod
from typing import Any


class IAgentOrchestrator(ABC):
    """Protocol for agent orchestration"""

    @abstractmethod
    async def execute_workflow(self, workflow_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """
        Execute an agent workflow.

        Args:
            workflow_id: ID of the workflow to execute
            inputs: Input parameters for the workflow

        Returns:
            Execution result with status and output
        """
        ...

    @abstractmethod
    async def get_status(self, execution_id: str) -> dict[str, Any]:
        """
        Get the status of a workflow execution.

        Args:
            execution_id: ID of the execution to query

        Returns:
            Current execution status and metadata
        """
        ...
