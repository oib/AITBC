"""Wallet access, signing and submission.

Reuses the exact wire format of `cli/aitbc_cli/commands/wallet/basic.py`'s
`send` (same field set, same keccak-over-sorted-JSON signature the node
verifier expects) and the CLI's decrypt helper
(`aitbc.security.encryption.decrypt_value`). The password arrives via the
systemd credential ops-wallet-pass ($CREDENTIALS_DIRECTORY) or, on LXC
hosts where credential mounts yield nothing, via `systemd-creds decrypt`
on the sealed file: never env, never argv, never a log line.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CREDENTIAL_NAME, Config

_CREDENTIAL_TIMEOUT_S = 10.0


class CredentialMissing(Exception):
    """The systemd credential file is absent or empty -- refuse to sign."""


def _check_credential_file(path: Path) -> None:
    """The sealed credential must be an absolute, root-owned 0600 file."""
    if not path.is_absolute():
        raise CredentialMissing("credential path not absolute")
    try:
        st = path.stat()
    except OSError:
        raise CredentialMissing("credential file missing or unreadable") from None
    if st.st_uid != 0:
        raise CredentialMissing("credential file not root-owned")
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise CredentialMissing("credential file mode not 0600")


def _systemd_creds_decrypt(credential_file: Path) -> str:
    """LXC fallback: decrypt the sealed credential file ourselves.

    LoadCredentialEncrypted does nothing on LXC (hub): no
    CREDENTIALS_DIRECTORY and an inaccessible /run/credentials mount, so
    the unit must run ``systemd-creds decrypt`` directly. Fixed argv, no
    shell; the password never enters argv, env, logs or exception text.
    """
    _check_credential_file(credential_file)
    argv = ["systemd-creds", "decrypt", f"--name={CREDENTIAL_NAME}", str(credential_file), "-"]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=_CREDENTIAL_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        raise CredentialMissing("systemd-creds decrypt timed out") from None
    except OSError:
        raise CredentialMissing("systemd-creds not available") from None
    if proc.returncode != 0:
        raise CredentialMissing(f"systemd-creds decrypt failed rc={proc.returncode}")
    try:
        password = proc.stdout.decode()
    except UnicodeDecodeError:
        raise CredentialMissing("systemd-creds output undecodable") from None
    if password.endswith("\n"):
        password = password[:-1]
    if not password:
        raise CredentialMissing("systemd-creds decrypt produced empty secret")
    return password


def _credential_password(credential_file: str | Path) -> str:
    cred_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if cred_dir:
        path = Path(cred_dir) / CREDENTIAL_NAME
        try:
            password = path.read_text().rstrip("\n")
        except OSError:
            password = None
        if password is not None:
            if not password:
                raise CredentialMissing(f"{path} is empty")
            return password
    return _systemd_creds_decrypt(Path(credential_file))


def _load_wallet(path: str | Path, password: str) -> dict[str, Any]:
    """Same wallet JSON the CLI reads: address + private_key (encrypted or hex)."""
    from aitbc.security.encryption import decrypt_value  # repo path

    data: dict[str, Any] = json.loads(Path(path).read_text())
    priv = data.get("private_key")
    if isinstance(priv, dict):
        data["private_key"] = decrypt_value(priv, password)
    elif not isinstance(priv, str):
        raise ValueError("wallet carries no private_key")
    return data


def _private_key(wallet: dict[str, Any]) -> Any:
    from eth_keys import keys

    hexkey = str(wallet["private_key"])
    if hexkey.startswith("0x"):
        hexkey = hexkey[2:]
    return keys.PrivateKey(bytes.fromhex(hexkey))


def resolve_chain_id(http: Any) -> str:
    """Chain id from the node's /health -- same source the CLI's get_chain_id uses."""
    health = http.get("/health")
    chains = health.get("supported_chains") or []
    if len(chains) != 1:
        raise ValueError(f"cannot resolve chain id from /health: {chains!r}")
    return str(chains[0])


def fetch_nonce(http: Any, address: str) -> int:
    account = http.get(f"/rpc/account/{address}")
    nonce = account.get("nonce")
    if nonce is None:
        raise ValueError("account response carried no nonce")
    return int(nonce)


def build_transfer(*, chain_id: str, sender: str, to: str, amount_units: int, nonce: int, fee_units: int) -> dict[str, Any]:
    """Identical field set to cli basic.py send()."""
    return {
        "type": "TRANSFER",
        "chain_id": chain_id,
        "from": sender,
        "to": to,
        "amount": amount_units,
        "nonce": nonce,
        "fee": fee_units,
        "payload": {"amount": amount_units},
    }


def sign_transaction(tx: dict[str, Any], private_key: Any) -> dict[str, Any]:
    from eth_utils import keccak

    signed_fields = {k: v for k, v in tx.items() if k != "signature"}
    message = json.dumps(signed_fields, sort_keys=True, separators=(",", ":")).encode()
    tx["signature"] = private_key.sign_msg_hash(keccak(message)).to_bytes().hex()
    return tx


@dataclass
class Signer:
    config: Config
    http_factory: Any = None  # injectable for tests: () -> http client

    def _http(self) -> Any:
        if self.http_factory is not None:
            return self.http_factory()
        from aitbc.network.client import AITBCHTTPClient

        return AITBCHTTPClient(base_url=self.config.rpc_url, timeout=30)

    def sign_and_send(self, *, to: str, amount_units: int) -> str:
        """Sign a TRANSFER and submit it. Returns the transaction hash only.

        The private key and password exist only inside this call frame.
        """
        password = _credential_password(self.config.credential_file)
        wallet = _load_wallet(self.config.wallet_path, password)
        key = _private_key(wallet)
        http = self._http()
        sender = wallet["address"]
        chain_id = self.config.chain_id or resolve_chain_id(http)
        nonce = fetch_nonce(http, sender)
        tx = build_transfer(
            chain_id=chain_id,
            sender=sender,
            to=to,
            amount_units=amount_units,
            nonce=nonce,
            fee_units=self.config.fee_units,
        )
        sign_transaction(tx, key)
        result = http.post("/rpc/transaction", json=tx)
        tx_hash = result.get("transaction_hash")
        if not tx_hash:
            raise ValueError("submission returned no transaction_hash")
        return str(tx_hash)
