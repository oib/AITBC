"""AITBC bridge helpers."""

from dataclasses import dataclass
from typing import Any


@dataclass
class BridgeConfig:
    """Stub bridge configuration."""

    source_chain: str = ""
    target_chain: str = ""
    validator_set: list[str] | None = None


class BridgeClient:
    """Stub bridge client."""

    def __init__(self, config: BridgeConfig):
        self.config = config

    def transfer(self, amount: Any, recipient: str) -> dict[str, Any]:
        return {"status": "transferred", "recipient": recipient, "amount": str(amount)}

    def status(self, transfer_id: str) -> dict[str, Any]:
        return {"transfer_id": transfer_id, "status": "completed"}


__all__ = ["BridgeClient", "BridgeConfig"]
