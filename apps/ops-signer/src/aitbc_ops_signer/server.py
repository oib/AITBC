"""Unix-socket server: SO_PEERCRED group check, one request shape, fail closed.

Protocol: one JSON object per connection on a unix datagram-free stream,
reply one JSON object, close. The only operation is sign_payment.
The peer is admitted when its uid is 0 or its primary gid is the
configured group's gid (the unit runs as root; group members get the
socket via the 0660 group ownership anyway -- the peercred check is the
second, code-enforced wall).
"""

from __future__ import annotations

import grp
import json
import socket
import struct
import threading
from collections.abc import Callable
from typing import Any

from .audit import audit_line
from .config import Config
from .ledger import DailyLedger
from .policy import PaymentRequest, Refused, check_amount, check_recipient, load_allowlist, parse_request
from .signer import Signer

PeerCred = tuple[int, int, int]  # (pid, uid, gid)


def peer_credentials(conn: socket.socket) -> PeerCred:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)


def _peer_allowed(peer: PeerCred, group_gid: int) -> bool:
    _pid, uid, gid = peer
    return uid == 0 or gid == group_gid


def handle_request(
    payload: dict,
    *,
    config: Config,
    ledger: DailyLedger,
    signer: Signer,
    peer: PeerCred,
    peer_gid: int,
) -> dict[str, Any]:
    """Validate, enforce policy, optionally sign. Always answers; never raises."""
    memo = "-"
    to = "-"
    amount = 0
    result = "error"
    reason = "internal"
    tx_hash = "-"
    try:
        req: PaymentRequest = parse_request(payload)
        memo, to, amount = req.memo, req.to, req.amount_units
        check_amount(req, max_per_tx=config.max_per_tx)
        check_recipient(req, load_allowlist(config.allow_file))
        if req.dry_run:
            if ledger.spent_last_24h() + req.amount_units > config.max_per_day:
                raise Refused("over_day_cap")
            result, reason = "dry_run_pass", "-"
            return {"ok": True, "result": result}
        row_id = ledger.admit(req.amount_units, memo=req.memo, to_addr=req.to, max_per_day=config.max_per_day)
        if row_id is None:
            raise Refused("over_day_cap")
        try:
            tx_hash = signer.sign_and_send(to=req.to, amount_units=req.amount_units)
        except Exception:
            ledger.release(row_id)
            raise
        ledger.record_tx_hash(row_id, tx_hash)
        result = "signed"
        reason = "-"
        return {"ok": True, "result": result, "tx_hash": tx_hash}
    except Refused as e:
        result, reason = "refused", e.reason
        return {"ok": False, "result": result, "reason": reason}
    except Exception:
        # fail closed: refuse with a generic reason, never leak internals
        result, reason = "error", "internal"
        return {"ok": False, "result": result, "reason": reason}
    finally:
        try:
            audit_line(
                config.audit_path,
                memo=memo,
                to=to,
                amount_units=amount,
                result=result,
                reason=reason,
                tx_hash=tx_hash,
                peer_uid=peer[1],
            )
        except OSError:
            pass


class OpsSignerServer:
    def __init__(
        self,
        config: Config,
        *,
        creds_fn: Callable[[socket.socket], PeerCred] = peer_credentials,
        group_gid_fn: Callable[[str], int] | None = None,
    ) -> None:
        self.config = config
        self._creds_fn = creds_fn
        self._group_gid_fn = group_gid_fn or (lambda name: grp.getgrnam(name).gr_gid)
        self.ledger = DailyLedger(config.ledger_path)
        self.signer = Signer(config)
        self._sock: socket.socket | None = None

    def _serve_conn(self, conn: socket.socket) -> None:
        with conn:
            try:
                peer = self._creds_fn(conn)
                gid = self._group_gid_fn(self.config.peer_group)
                if not _peer_allowed(peer, gid):
                    conn.sendall(b'{"ok":false,"result":"refused","reason":"peer_not_in_group"}')
                    return
                chunks: list[bytes] = []
                while sum(len(c) for c in chunks) <= self.config.max_request_bytes:
                    data = conn.recv(4096)
                    if not data:
                        break
                    chunks.append(data)
                    if b"\n" in data:
                        break
                payload = json.loads(b"".join(chunks).strip() or b"{}")
                reply = handle_request(
                    payload,
                    config=self.config,
                    ledger=self.ledger,
                    signer=self.signer,
                    peer=peer,
                    peer_gid=gid,
                )
                conn.sendall(json.dumps(reply).encode() + b"\n")
            except Exception:
                try:
                    conn.sendall(b'{"ok":false,"result":"error","reason":"internal"}\n')
                except OSError:
                    pass

    def serve_forever(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock = sock
        try:
            sock.bind(self.config.socket_path)
            import os

            os.chmod(self.config.socket_path, self.config.socket_mode)
            try:
                os.chown(self.config.socket_path, 0, self._group_gid_fn(self.config.peer_group))
            except (OSError, KeyError):
                pass  # group may not exist pre-provisioning; root still owns it
            sock.listen(16)
            while True:
                conn, _ = sock.accept()
                threading.Thread(target=self._serve_conn, args=(conn,), daemon=True).start()
        finally:
            sock.close()


def request(sock_path: str, payload: dict, timeout: float = 15.0) -> dict:
    """Client helper for the runbook's canary/dry-run commands."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall(json.dumps(payload).encode() + b"\n")
        out = b""
        while chunk := s.recv(4096):
            out += chunk
        result: dict = json.loads(out)
        return result
