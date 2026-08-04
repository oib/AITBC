"""TEE-backed GPU enclaves for compliance-sensitive compute (v0.15.2 §B1).

ponytail: This is an attestation-policy skeleton. Real GPU TEEs need
NVIDIA H100 confidential computing or equivalent and a remote attestation
protocol to prove the enclave image and isolation before admission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aitbc.compliance.errors import PolicyViolationError
from aitbc.compliance.policies import ComplianceFramework, DataClassification, normalize_classification
from aitbc.tee import Enclave, EnclaveConfig


class GPUEnclaveStatus(StrEnum):
    """Status of a compliance GPU enclave."""

    PENDING = "pending"
    ATTESTED = "attested"
    RUNNING = "running"
    STOPPED = "stopped"


@dataclass
class ComplianceGPUEnclave:
    """GPU enclave that only runs workloads matching a compliance policy."""

    enclave_id: str
    policy_framework: ComplianceFramework = ComplianceFramework.HIPAA
    allowed_classifications: set[DataClassification] = field(default_factory=set)
    attested: bool = False
    status: GPUEnclaveStatus = GPUEnclaveStatus.PENDING
    enclave: Enclave | None = None

    def __post_init__(self) -> None:
        if not self.enclave_id:
            raise ValueError("enclave_id is required")
        self.allowed_classifications = {normalize_classification(c) for c in self.allowed_classifications}
        self.enclave = Enclave(
            config=EnclaveConfig(enclave_id=self.enclave_id, image=f"{self.policy_framework.value}-gpu-enclave")
        )

    def allows(self, classification: DataClassification | str) -> bool:
        """Return True if the enclave accepts the data classification."""
        if not self.allowed_classifications:
            return True
        return normalize_classification(classification) in self.allowed_classifications

    def attest(self, measurement: str) -> None:
        """Attest the enclave and mark it as trusted."""
        if self.enclave is None:
            raise ValueError("enclave not initialized")
        self.enclave.build()
        self.enclave.launch()
        self.attested = True
        self.status = GPUEnclaveStatus.ATTESTED

    def run(
        self,
        workload_id: str,
        classification: DataClassification | str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a workload inside the enclave after attestation and policy checks."""
        if not self.attested or self.enclave is None or self.enclave.status.value != "running":
            raise PolicyViolationError(f"enclave {self.enclave_id} is not attested/running")
        if not self.allows(classification):
            raise PolicyViolationError(f"enclave {self.enclave_id} does not accept classification {classification}")
        self.status = GPUEnclaveStatus.RUNNING
        return {
            "workload_id": workload_id,
            "enclave_id": self.enclave_id,
            "classification": str(classification),
            "result": payload,
            "attested": self.attested,
        }

    def stop(self) -> None:
        """Stop the enclave."""
        if self.enclave is not None:
            self.enclave.teardown()
        self.status = GPUEnclaveStatus.STOPPED
