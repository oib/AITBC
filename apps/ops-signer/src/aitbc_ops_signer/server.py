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
import logging
import signal
import socket
import stat
import struct
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .audit import audit_line
from .config import Config
from .ledger import DailyLedger
from .policy import PaymentRequest, Refused, check_amount, check_recipient, load_allowlist, parse_request
from .signer import Signer

PeerCred = tuple[int, int, int]  # (pid, uid, gid)

log = logging.getLogger(__name__)


def peer_credentials(conn: socket.socket) -> PeerCred:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)


def _prepare_socket_path(path: str | Path) -> None:
    """Clear the way for bind(): remove a stale socket, refuse anything else.

    A leftover socket file (previous process died without unlinking) is the
    classic EADDRINUSE-on-restart. It is stale when nothing accepts a
    connection on it (connect -> ConnectionRefusedError). A live listener
    means a second instance tried to start -- refuse. Anything that is not
    a socket (regular file, dir, ...) is never removed -- refuse too.
    """
    p = Path(path)
    try:
        st = p.stat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(st.st_mode):
        raise RuntimeError(f"socket path {p} exists and is not a socket; refusing to remove it")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(str(p))
    except FileNotFoundError:
        return  # vanished between stat and probe
    except ConnectionRefusedError:
        p.unlink(missing_ok=True)
        return
    except OSError as e:
        raise RuntimeError(f"socket path {p} could not be probed: {e.strerror or e.errno}") from e
    finally:
        probe.close()
    raise RuntimeError(f"socket path {p} has a live listener; refusing to start a second instance")


def _sigterm_exit(signum, frame):  # noqa: ARG001 - signal handler signature
    raise SystemExit(0)


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
        log.warning("sign request refused: %s: %s", type(e).__name__, e.reason)
        result, reason = "refused", e.reason
        return {"ok": False, "result": result, "reason": reason}
    except Exception as e:
        # fail closed: refuse with a generic reason, never leak internals --
        # but the journal needs the failure cause (class + message only;
        # our exception types carry controlled, secret-free text).
        log.warning("sign request failed: %s: %s", type(e).__name__, e)
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
        self._stopping = False

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

    def stop(self) -> None:
        """Graceful shutdown for tests/admin: flag + wake the blocked accept."""
        self._stopping = True
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as wake:
                wake.connect(self.config.socket_path)
        except OSError:
            pass

    def serve_forever(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock = sock
        bound = False
        try:
            try:
                _prepare_socket_path(self.config.socket_path)
            except RuntimeError as e:
                log.error("not starting: %s", e)
                raise
            sock.bind(self.config.socket_path)
            bound = True
            import os

            os.chmod(self.config.socket_path, self.config.socket_mode)
            try:
                os.chown(self.config.socket_path, 0, self._group_gid_fn(self.config.peer_group))
            except (OSError, KeyError):
                pass  # group may not exist pre-provisioning; root still owns it
            sock.listen(16)
            try:
                signal.signal(signal.SIGTERM, _sigterm_exit)
            except ValueError:
                pass  # not the main thread (tests) -- callers use stop()
            while not self._stopping:
                conn, _ = sock.accept()
                threading.Thread(target=self._serve_conn, args=(conn,), daemon=True).start()
        finally:
            sock.close()
            if bound:
                try:
                    Path(self.config.socket_path).unlink(missing_ok=True)
                except OSError:
                    pass


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
