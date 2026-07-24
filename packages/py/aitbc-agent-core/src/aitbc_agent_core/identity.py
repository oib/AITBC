"""Portable decentralized identity for white-label agents."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class AgentIdentity:
    """Minimal DID-style identity that can travel across agent front-ends."""

    public_key: str
    method: str = "did:aitbc"

    def did(self) -> str:
        """Return the full decentralized identifier string."""
        return f"{self.method}:{self.public_key}"
