"""Reference healthcare (HIPAA) TEE enclave for PHI processing.

ponytail: This is a Python simulator of an enclave workload. A real deployment
compiles a minimal enclave binary and runs it under SGX/TDX/SEV with remote
attestation before any PHI enters the trust boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aitbc.tee import Enclave, EnclaveConfig
from aitbc.tee.errors import TEEError


@dataclass
class PHIRecord:
    """A synthetic PHI record processed inside the healthcare enclave."""

    patient_id: str
    data: dict[str, Any] = field(default_factory=dict)
    authorized: bool = False

    def redact(self) -> dict[str, Any]:
        """Return a redacted view of the record for external consumption."""
        if not self.authorized:
            raise TEEError("PHI access denied: enclave not authorized")
        return {"patient_id": self.patient_id} | dict.fromkeys(self.data, "REDACTED")


class HIPAAEnclave:
    """Reference healthcare enclave that verifies attestation before PHI access."""

    def __init__(self, enclave_id: str, image: str = "hipaa-enclave:latest") -> None:
        self.enclave = Enclave(config=EnclaveConfig(enclave_id=enclave_id, image=image))

    def start(self) -> None:
        """Build and launch the enclave."""
        self.enclave.build()
        self.enclave.launch()

    def process(self, record: PHIRecord) -> dict[str, Any]:
        """Authorize and redact a PHI record inside the enclave boundary."""
        if self.enclave.status.value != "running":
            raise TEEError("enclave is not running")
        record.authorized = True
        return record.redact()
