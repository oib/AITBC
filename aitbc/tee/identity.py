"""TEE enclave identity and key provisioning skeleton (v0.14.1 §A1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SealedKeyBundle:
    """A sealed secret key bundle bound to an enclave measurement."""

    enclave_id: str
    sealed_blob: bytes
    public_key: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class KeyProvisioningPolicy:
    """Policy controlling how keys are provisioned to an enclave."""

    enclave_id: str
    allowed_measurements: list[str] = field(default_factory=list)
    max_uses: int = 0

    def authorize(self, measurement: str) -> bool:
        """Return True if the measurement is allowed to receive keys."""
        if not self.allowed_measurements:
            return True
        return measurement in self.allowed_measurements


@dataclass
class EnclaveIdentity:
    """Public identity of an enclave."""

    enclave_id: str
    public_key: str
    measurement: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
