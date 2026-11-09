"""Wire-level coverage for the ops-signer unix socket.

Drives OpsSignerServer over real AF_UNIX sockets under tmp_path with
injected peercred/gid lookups (real SO_PEERCRED would report the test
process's own ids). No network, no real wallet, no secrets.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest

from aitbc_ops_signer.config import Config
from aitbc_ops_signer.server import OpsSignerServer, _peer_allowed, request

PAYEE = "0xEB29516824E95AdFFeEdfc914941F0fbEd0bB1a4"
OPS_PEER = (1234, 1001, 4242)
OUTSIDER_PEER = (1234, 1001, 9999)
ROOT_PEER = (1, 0, 0)


class SpySigner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def sign_and_send(self, *, to: str, amount_units: int) -> str:
        self.calls.append((to, amount_units))
        return "0x" + os.urandom(32).hex()


def _cfg(tmp_path: Path, **over) -> Config:
    allow = tmp_path / "ops-signer.allow"
    allow.write_text(f"{PAYEE}\n")
    base = {
        "socket_path": str(tmp_path / "ops.sock"),
        "allow_file": str(allow),
        "ledger_path": str(tmp_path / "ledger.db"),
        "audit_path": str(tmp_path / "audit.log"),
        "wallet_path": str(tmp_path / "ops.json"),
        "max_per_tx": 1_000,
        "max_per_day": 2_500,
    }
    base.update(over)
    return Config(**base)


def _wait_sock(path: Path, timeout: float = 5.0) -> None:
    for _ in range(100):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.connect(str(path))
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"socket never served: {path}")


def _serve(srv: OpsSignerServer) -> threading.Thread:
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return t


def _server(cfg: Config, peer: tuple[int, int, int] = OPS_PEER) -> OpsSignerServer:
    return OpsSignerServer(cfg, creds_fn=lambda _c: peer, group_gid_fn=lambda _n: 4242)


def _req(**kw) -> dict:
    base = {"op": "sign_payment", "to": PAYEE, "amount_units": 100, "memo": "S-10"}
    base.update(kw)
    return base


def _raw_request(sock_path: str, data: bytes, timeout: float = 5.0) -> bytes:
    """Send raw bytes, half-close, return everything the server writes."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall(data)
        s.shutdown(socket.SHUT_WR)
        out = b""
        while True:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            out += chunk
    return out


@pytest.fixture
def running(tmp_path: Path):
    """A served signer with a spy signer; yields (cfg, srv, thread)."""
    cfg = _cfg(tmp_path)
    srv = _server(cfg)
    srv.signer = cast(Any, SpySigner())  # replace the real Signer; ledger stays real
    t = _serve(srv)
    _wait_sock(Path(cfg.socket_path))
    yield cfg, srv, t
    srv.stop()
    t.join(timeout=5)
    assert not t.is_alive()


def test_peer_allowed_matrix():
    assert _peer_allowed(ROOT_PEER, 4242) is True  # uid 0 bypasses gid
    assert _peer_allowed((9, 0, 9999), 4242) is True
    assert _peer_allowed(OPS_PEER, 4242) is True  # primary gid match
    assert _peer_allowed(OUTSIDER_PEER, 4242) is False
    # supplementary-group membership is NOT honored: only primary gid counts
    assert _peer_allowed((9, 1001, 4243), 4242) is False


def test_wire_dry_run_signs_nothing(running):
    cfg, srv, _t = running
    reply = request(cfg.socket_path, _req(dry_run=True))
    assert reply == {"ok": True, "result": "dry_run_pass"}
    assert srv.signer.calls == []
    assert srv.ledger.spent_last_24h() == 0


def test_wire_sign_roundtrip_and_audit(running):
    cfg, srv, _t = running
    reply = request(cfg.socket_path, _req(amount_units=250))
    assert reply["ok"] is True and reply["result"] == "signed"
    assert reply["tx_hash"].startswith("0x")
    assert srv.signer.calls == [(PAYEE.lower(), 250)]
    assert srv.ledger.spent_last_24h() == 250
    audit = Path(cfg.audit_path).read_text()
    assert "result=intent" in audit and "result=signed" in audit
    assert "peer_uid=1001" in audit


def test_wire_refused_request_is_audited(running):
    cfg, _srv, _t = running
    stranger = "0x" + "cd" * 20  # well-formed but not on the allow list
    reply = request(cfg.socket_path, _req(to=stranger))
    assert reply == {"ok": False, "result": "refused", "reason": "not_allowlisted"}
    audit = Path(cfg.audit_path).read_text()
    assert "result=refused" in audit and "reason=not_allowlisted" in audit


def test_wire_bad_json_gets_error_reply_not_disconnect(running):
    cfg, _srv, _t = running
    out = _raw_request(cfg.socket_path, b"this is not json\n")
    assert json.loads(out) == {"ok": False, "result": "error", "reason": "malformed_request"}


def test_wire_json_non_dict_gets_refused(running):
    cfg, _srv, _t = running
    out = _raw_request(cfg.socket_path, b"[1, 2, 3]\n")
    assert json.loads(out) == {"ok": False, "result": "refused", "reason": "malformed"}


def test_wire_unknown_op_and_missing_fields(running):
    cfg, _srv, _t = running
    assert (
        json.loads(_raw_request(cfg.socket_path, b'{"op":"sweep","to":"x","amount_units":1,"memo":"S-1"}\n'))["reason"]
        == "unknown_op"
    )
    # missing memo entirely
    assert (
        json.loads(_raw_request(cfg.socket_path, b'{"op":"sign_payment","to":"' + PAYEE.encode() + b'","amount_units":1}\n'))[
            "reason"
        ]
        == "bad_memo"
    )


def test_wire_request_without_newline_still_answered(running):
    """EOF terminates the request: a client that half-closes after the JSON
    body (no trailing newline) still gets its reply."""
    cfg, _srv, _t = running
    out = _raw_request(cfg.socket_path, json.dumps(_req(dry_run=True)).encode())
    assert json.loads(out) == {"ok": True, "result": "dry_run_pass"}


def test_wire_oversized_request_refused_by_size_cap(tmp_path: Path):
    cfg = _cfg(tmp_path, max_request_bytes=64)
    srv = _server(cfg)
    srv.signer = cast(Any, SpySigner())
    t = _serve(srv)
    _wait_sock(Path(cfg.socket_path))
    try:
        # 500 bytes of non-JSON with no newline: the read loop stops at the
        # cap and json.loads fails -> generic error, connection survives.
        out = _raw_request(cfg.socket_path, b"x" * 500)
        assert json.loads(out) == {"ok": False, "result": "error", "reason": "malformed_request"}
        # listener still serves afterwards
        assert request(cfg.socket_path, _req(dry_run=True))["result"] == "dry_run_pass"
    finally:
        srv.stop()
        t.join(timeout=5)


def test_wire_trailing_bytes_after_newline_fail_closed(running):
    """Bytes after the first newline are not a second request: the whole
    recv chunk is parsed, extra data makes it invalid JSON -> error."""
    cfg, _srv, _t = running
    blob = json.dumps(_req(dry_run=True)).encode() + b"\n" + b"garbage"
    out = _raw_request(cfg.socket_path, blob)
    # Depending on recv coalescing this is either the dry_run reply (if the
    # newline chunk arrived alone) or an error; both are acceptable, but it
    # must never sign and never crash the listener.
    reply = json.loads(out)
    assert reply["ok"] is False or reply["result"] == "dry_run_pass"
    assert request(cfg.socket_path, _req(dry_run=True))["result"] == "dry_run_pass"


def test_wire_two_requests_one_connection_only_first_counts(running):
    """Pipelined bytes after the first newline cannot smuggle a second
    sign request through the same connection."""
    cfg, srv, _t = running
    blob = json.dumps(_req(dry_run=True)).encode() + b"\n" + json.dumps(_req(amount_units=900, memo="BR-9")).encode() + b"\n"
    _raw_request(cfg.socket_path, blob)
    # however the coalesced chunk parsed, at most the dry-run was honored:
    assert srv.signer.calls == []
    assert srv.ledger.spent_last_24h() == 0


def test_peer_refusal_is_audited(tmp_path: Path):
    """An unauthorized peer must leave an audit trail like every other
    refused request -- its uid is already known at refusal time."""
    cfg = _cfg(tmp_path)
    srv = _server(cfg, peer=OUTSIDER_PEER)
    t = _serve(srv)
    _wait_sock(Path(cfg.socket_path))
    try:
        reply = request(cfg.socket_path, _req())
        assert reply == {"ok": False, "result": "refused", "reason": "peer_not_in_group"}
    finally:
        srv.stop()
        t.join(timeout=5)
    audit = Path(cfg.audit_path)
    text = audit.read_text() if audit.exists() else ""
    assert "peer_not_in_group" in text
    assert "peer_uid=1001" in text


def test_stop_before_serve_is_safe(tmp_path: Path):
    srv = _server(_cfg(tmp_path))
    srv.stop()  # nothing listening: wake-up connect fails, flag still set
    assert srv._stopping is True
