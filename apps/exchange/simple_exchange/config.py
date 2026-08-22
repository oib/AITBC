"""AITBC simple-exchange runtime configuration (no secrets).

Values are read from the environment or from `/etc/aitbc/blockchain.env` via
`python-dotenv`. No private keys, seeds, or API tokens are stored in this file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BridgeConfig:
    """Public bridge configuration used by handlers.

    The custodian model is the current default: ETH->AIT deposits are accepted
    by a hub-controlled deposit address.  Multisig settings may be enabled by
    operators for stronger custody; until then the exchange reports the
    custodian mode honestly.
    """

    bridge_eth_address: str = ""
    bridge_contract_address: str = ""
    deposit_enabled: bool = True
    withdraw_enabled: bool = False
    custodian: bool = True
    multisig_enabled: bool = False
    multisig_threshold: int = 0
    signers: tuple[str, ...] = ()
    safe_address: str = ""
    fee_rate: float = 0.005
    min_eth_deposit: str = "0.001"
    eth_network: str = "sepolia"

    @property
    def status_message(self) -> str:
        if self.bridge_contract_address:
            return "Bridge contract deployed on-chain"
        if self.bridge_eth_address:
            return "Bridge configured in trusted-custodian mode; contract not deployed"
        return "Bridge not configured; set BRIDGE_ETH_ADDRESS or deploy a contract"

    def as_status(self) -> dict[str, Any]:
        return {
            "bridge": "CrossChainBridge",
            "status": "deployed" if self.bridge_contract_address else "configured",
            "direction": "ETH -> AIT (deposits only)",
            "supported_chains": ["ethereum", "aitbc"],
            "deposit_address": self.bridge_eth_address or None,
            "withdraw_address": None,
            "withdraw_enabled": self.withdraw_enabled,
            "fee_rate": self.fee_rate,
            "contract_address": self.bridge_contract_address or None,
            "custodian": self.custodian,
            "multisig_enabled": self.multisig_enabled,
            "multisig_threshold": self.multisig_threshold,
            "multisig_signers_count": len(self.signers),
            "safe_address": self.safe_address or None,
            "message": self.status_message,
            "note": (
                "Withdrawals (AIT -> ETH) are currently disabled. "
                "Only ETH deposits to AIT are supported."
            ),
        }


def _env_list(name: str, default: str = "") -> tuple[str, ...]:
    value = os.getenv(name, default)
    if not value:
        return ()
    return tuple(s.strip() for s in value.replace(";", ",").split(",") if s.strip())


def _load_bridge_config() -> BridgeConfig:
    try:
        # Try to load the same env file the systemd unit uses.  This is
        # intentionally best-effort; unit tests usually set env vars directly.
        from dotenv import load_dotenv

        load_dotenv("/etc/aitbc/blockchain.env", override=False)
    except Exception:
        pass

    threshold_raw = os.getenv("BRIDGE_MULTISIG_THRESHOLD", "0")
    try:
        threshold = int(threshold_raw)
    except ValueError:
        threshold = 0

    signers = _env_list("BRIDGE_SIGNERS", "")
    if not signers and os.getenv("BRIDGE_MULTISIG_SIGNERS"):
        signers = _env_list("BRIDGE_MULTISIG_SIGNERS", "")

    multisig_enabled = os.getenv("BRIDGE_MULTISIG_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    # If an explicit threshold and signer list are set, turn on the flag for
    # an honest status report even if BRIDGE_MULTISIG_ENABLED is missing.
    if threshold > 0 and len(signers) >= threshold:
        multisig_enabled = True

    fee_raw = os.getenv("BRIDGE_FEE_RATE", "0.005")
    try:
        fee_rate = float(fee_raw)
    except ValueError:
        fee_rate = 0.005

    return BridgeConfig(
        bridge_eth_address=os.getenv("BRIDGE_ETH_ADDRESS", ""),
        bridge_contract_address=os.getenv("BRIDGE_CONTRACT_ADDRESS", ""),
        deposit_enabled=os.getenv("BRIDGE_DEPOSIT_ENABLED", "true").lower()
        in ("1", "true", "yes"),
        withdraw_enabled=os.getenv("BRIDGE_WITHDRAW_ENABLED", "false").lower()
        in ("1", "true", "yes"),
        custodian=os.getenv("BRIDGE_CUSTODIAN_MODE", "true").lower()
        in ("1", "true", "yes"),
        multisig_enabled=multisig_enabled,
        multisig_threshold=threshold,
        signers=signers,
        safe_address=os.getenv("BRIDGE_SAFE_ADDRESS", ""),
        fee_rate=fee_rate,
        min_eth_deposit=os.getenv("MIN_ETH_DEPOSIT", "0.001"),
        eth_network=os.getenv("ETH_NETWORK", "sepolia"),
    )


bridge_config = _load_bridge_config()
