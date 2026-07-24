"""TEE-backed confidential compute task abstractions (v0.14.1 §A3).

Provides ``TEETask``, ``TEETaskInput``, ``TEETaskResult``, and
``TEETaskRunner`` primitives. A real runner enters a GPU/CPU TEE enclave and
executes the payload there; the in-memory runner is a simulator that validates
the attestation quote and invokes a callable inside the enclave trust boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from collections.abc import Callable
from typing import Any

from aitbc.tee.attestation import AttestationQuote, AttestationStatus
from aitbc.tee.enclave import Enclave, EnclaveStatus
from aitbc.tee.errors import TEEError


class TEEExecutionStatus(StrEnum):
    """Lifecycle status of a TEE compute task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TEETaskInput:
    """Input payload and enclave binding for a confidential compute task."""

    task_id: str
    agent_id: str
    payload: dict[str, Any]
    enclave_id: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TEETaskResult:
    """Result of executing a TEE compute task."""

    task_id: str
    status: TEEExecutionStatus | str
    output: dict[str, Any]
    logs: list[str] = field(default_factory=list)
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = TEEExecutionStatus(self.status)


@dataclass
class TEETask:
    """A confidential execution task scheduled inside a TEE enclave."""

    input: TEETaskInput
    status: TEEExecutionStatus | str = TEEExecutionStatus.PENDING
    quote: AttestationQuote | None = None
    enclave: Enclave | None = None
    result: TEETaskResult | None = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    logs: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = TEEExecutionStatus(self.status)

    def attest(self, quote: AttestationQuote) -> None:
        """Bind the task to a valid attestation quote."""
        if quote.status != AttestationStatus.VALID:
            raise TEEError(f"invalid attestation quote status {quote.status}")
        if quote.is_expired():
            raise TEEError("attestation quote has expired")
        self.quote = quote

    def bind_enclave(self, enclave: Enclave) -> None:
        """Bind the task to a running enclave."""
        if enclave.status != EnclaveStatus.RUNNING:
            raise TEEError(f"enclave is not running: {enclave.status}")
        self.enclave = enclave

    def log(self, message: str) -> None:
        """Append a log line to the task."""
        self.logs.append(message)


class TEETaskRunner:
    """Simulated TEE task runner.

    The runner validates attestation and enclave state, then calls the
    provided executor callable. In production the executor is the entry point
    of the enclave binary.
    """

    def run(
        self,
        task: TEETask,
        executor: Callable[[TEETaskInput], dict[str, Any]],
    ) -> TEETaskResult:
        """Run a TEE-bound task and return its result."""
        if task.status != TEEExecutionStatus.PENDING:
            raise TEEError(f"task must be pending to run, got {task.status}")
        if task.quote is None:
            raise TEEError("task must be attested before execution")
        if task.enclave is None:
            raise TEEError("task must be bound to a running enclave")

        task.status = TEEExecutionStatus.RUNNING
        task.started_at = datetime.now(UTC)
        task.log("enclave execution started")

        try:
            output = executor(task.input)
            task.status = TEEExecutionStatus.COMPLETED
            task.completed_at = datetime.now(UTC)
            task.log("enclave execution completed")
            result = TEETaskResult(
                task_id=task.input.task_id,
                status=TEEExecutionStatus.COMPLETED,
                output=output,
                logs=list(task.logs),
                completed_at=task.completed_at,
            )
        except Exception as exc:
            task.status = TEEExecutionStatus.FAILED
            task.completed_at = datetime.now(UTC)
            task.log(f"enclave execution failed: {exc}")
            result = TEETaskResult(
                task_id=task.input.task_id,
                status=TEEExecutionStatus.FAILED,
                output={},
                logs=list(task.logs),
                completed_at=task.completed_at,
            )

        task.result = result
        return result
