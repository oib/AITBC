"""Service configuration.

Every value is operator-owned. Defaults below match the SEC-1 paper's
rollout decisions (1 AIT per tx / 5 AIT per day in chain units where
1 AIT = 36,000,000 units); the real values live in the root-owned env
file /etc/aitbc/ops-signer.env, read by the unit. Nothing here is a
secret -- the only secret is the wallet password, delivered exclusively
through the systemd credential ops-wallet-pass.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENABLED_FLAG = "AITBC_OPS_SIGNER_ENABLED"
CREDENTIAL_NAME = "ops-wallet-pass"

DEFAULT_MAX_PER_TX = 36_000_000  # 1 AIT
DEFAULT_MAX_PER_DAY = 180_000_000  # 5 AIT
DEFAULT_FEE_UNITS = 3_600  # 0.0001 AIT -- the fee the CLI charges on a 0.01 send


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def enabled() -> bool:
    """The service does nothing unless the flag is explicitly true."""
    return os.getenv(ENABLED_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    socket_path: str = "/run/aitbc-ops-signer.sock"
    socket_mode: int = 0o660
    peer_group: str = "aitbc-ops"
    allow_file: str = "/etc/aitbc/ops-signer.allow"
    max_per_tx: int = DEFAULT_MAX_PER_TX
    max_per_day: int = DEFAULT_MAX_PER_DAY
    fee_units: int = DEFAULT_FEE_UNITS
    ledger_path: str = "/var/lib/aitbc/ops-signer-ledger.db"
    audit_path: str = "/var/lib/aitbc/ops-signer-audit.log"
    wallet_path: str = "/var/lib/aitbc/wallets/ops.json"
    rpc_url: str = "http://127.0.0.1:8202"
    chain_id: str = ""  # empty = resolved from the rpc /health at sign time
    max_request_bytes: int = 65_536

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            socket_path=os.getenv("OPS_SIGNER_SOCK", cls.socket_path),
            peer_group=os.getenv("OPS_SIGNER_GROUP", cls.peer_group),
            allow_file=os.getenv("OPS_SIGNER_ALLOW_FILE", cls.allow_file),
            max_per_tx=_env_int("OPS_MAX_PER_TX", cls.max_per_tx),
            max_per_day=_env_int("OPS_MAX_PER_DAY", cls.max_per_day),
            fee_units=_env_int("OPS_FEE_UNITS", cls.fee_units),
            ledger_path=os.getenv("OPS_LEDGER_PATH", cls.ledger_path),
            audit_path=os.getenv("OPS_AUDIT_LOG", cls.audit_path),
            wallet_path=os.getenv("OPS_WALLET_PATH", cls.wallet_path),
            rpc_url=os.getenv("OPS_SIGNER_RPC_URL", cls.rpc_url),
            chain_id=os.getenv("OPS_CHAIN_ID", cls.chain_id),
        )
