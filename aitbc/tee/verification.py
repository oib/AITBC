"""TEE verification helpers."""

from enum import Enum
from typing import Any


class VerificationMode(str, Enum):
    SIMULATION = "simulation"
    HARDWARE = "hardware"
    HYBRID = "hybrid"


class DualVerificationPolicy:
    """Stub dual-mode verification policy."""

    def __init__(self, mode: VerificationMode = VerificationMode.SIMULATION):
        self.mode = mode


def verify_with_policy(quote: Any, policy: DualVerificationPolicy) -> dict[str, Any]:
    """Verify a quote under a policy."""
    return {"valid": True, "mode": policy.mode.value}


__all__ = ["DualVerificationPolicy", "VerificationMode", "verify_with_policy"]
