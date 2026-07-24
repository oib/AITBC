"""GPU-side TEE confidential compute task runner for Agent B v0.14.1 B2.

ponytail: This is a skeleton executor. Real deployment needs a TEE-capable
GPU runtime (e.g. NVIDIA Confidential Computing or a local simulator) and a
remote-attestation handshake before any payload is decrypted.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TEEExecutionStatus(StrEnum):
    """Lifecycle status of a TEE compute task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TEETask:
    """Confidential compute task payload."""

    task_id: str
    agent_id: str
    payload: dict[str, Any]
    status: TEEExecutionStatus = TEEExecutionStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    def add_log(self, message: str) -> None:
        self.logs.append(message)


def submit_tee_task(
    task: TEETask,
    coordinator_url: str = "http://localhost:8000",
    api_key: str = "",
    timeout: float = 10.0,
) -> TEETask:
    """Submit a TEE task report to the coordinator API.

    The actual confidential execution happens inside an enclave; this helper
    only reports the outcome and best-effort propagates capacity updates.
    """
    url = f"{coordinator_url.rstrip('/')}/v1/tee/tasks"
    data = json.dumps(
        {
            "task_id": task.task_id,
            "agent_id": task.agent_id,
            "status": task.status.value,
            "result": task.result,
            "logs": task.logs,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except urllib.error.URLError as exc:
        task.add_log(f"coordinator submission failed: {exc}")
    return task


def run_tee_task(
    task_id: str,
    agent_id: str,
    payload: dict[str, Any] | None = None,
    coordinator_url: str = "http://localhost:8000",
    api_key: str = "",
) -> TEETask:
    """Launch (simulate) a confidential compute task and report the result."""
    task = TEETask(
        task_id=task_id,
        agent_id=agent_id,
        payload=payload or {},
        status=TEEExecutionStatus.RUNNING,
    )
    task.add_log("enclave initialized")
    try:
        # Skeleton: real implementation would enter the GPU TEE enclave here.
        task.result = {"executed": True, "payload_keys": list(task.payload.keys())}
        task.status = TEEExecutionStatus.COMPLETED
        task.add_log("execution completed inside TEE")
    except Exception as exc:
        task.status = TEEExecutionStatus.FAILED
        task.add_log(f"execution error: {exc}")
    submit_tee_task(task, coordinator_url=coordinator_url, api_key=api_key)
    return task
