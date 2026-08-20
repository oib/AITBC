"""AITBC TEE helpers."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EnclaveConfig:
    """Stub enclave configuration."""

    name: str = ""
    mode: str = "simulation"
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Enclave:
    """Stub enclave."""

    enclave_id: str = ""
    config: EnclaveConfig | None = None


@dataclass
class AttestationQuote:
    """Stub attestation quote."""

    quote_id: str = ""
    enclave_id: str = ""
    data: bytes = b""


class QuoteGenerator:
    """Stub quote generator."""

    def generate(self, enclave: Enclave) -> AttestationQuote:
        return AttestationQuote(enclave_id=enclave.enclave_id, data=b"stub")


__all__ = ["AttestationQuote", "Enclave", "EnclaveConfig", "QuoteGenerator"]
