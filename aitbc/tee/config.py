"""TEE runtime configuration helpers."""

from __future__ import annotations

import os


def is_tee_attestation_enabled() -> bool:
    """Return whether TEE attestation is enabled.

    Defaults to ``False`` (fail-closed). Set ``TEE_ATTESTATION_ENABLED=true``
    to allow attestation submission, verification, and TEE-quoted jobs.
    """
    value = os.environ.get("TEE_ATTESTATION_ENABLED", "").lower()
    return value in ("true", "1", "yes", "on")
