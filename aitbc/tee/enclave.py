"""TEE enclave lifecycle skeleton (v0.14.1 §A1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .errors import TEEError


class EnclaveStatus(StrEnum):
    """Lifecycle status of an enclave."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class EnclaveConfig:
    """Configuration for launching an enclave."""

    enclave_id: str
    image: str = ""
    memory_mb: int = 256
    debug: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Enclave:
    """In-memory enclave handle."""

    config: EnclaveConfig
    status: EnclaveStatus = EnclaveStatus.PENDING
    measurement: str = ""

    def build(self) -> None:
        """Build the enclave image."""
        self.status = EnclaveStatus.PENDING

    def launch(self) -> None:
        """Launch the enclave."""
        if not self.config.image:
            raise TEEError("enclave image not configured")
        self.status = EnclaveStatus.RUNNING

    def teardown(self) -> None:
        """Stop and tear down the enclave."""
        self.status = EnclaveStatus.STOPPED
