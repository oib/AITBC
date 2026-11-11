"""CHECK-BIND-POLICY-1 (#1779): ``_table_ports`` must read only the Port
column, not every number in free-text cells.

The gate compared SERVICE_PORTS.md bind-all rows against ports harvested
from ALL cells of the policy tables — so ``127.0.0.1:7070`` inside a "Why"
prose cell authorized port 7070 even though the surface port was
``443 via nginx``. Mutation-verified bypass; these tests pin the fix.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "docs" / "check_bind_policy.py"
REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("check_bind_policy", SCRIPT)
assert _spec and _spec.loader
cbp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cbp)


POLICY_TABLE = """\
## Authorized public surfaces

| Surface | Port | Where | Why |
|---------|------|-------|-----|
| nginx (TLS) | 443, 80 | TLS terminator host | The entire customer-facing surface |
| Blockchain P2P / gossip | 443 via nginx | nginx host | The relay binds `127.0.0.1:7070` on the hub — no direct public 7070 listener |
| IPFS Swarm | 4002 | Island hosts | Private-swarm IPFS needs inbound peer connections |

## Known deviations

| Service | Port | Reason |
| --- | --- | --- |
| Postfix | 25 | Debian-default MTA; mention of 10.0.0.1:2525 in prose must not count |
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_table_ports_reads_only_port_column(tmp_path: Path) -> None:
    doc = _write(tmp_path, "policy.md", POLICY_TABLE)
    allowed = cbp._table_ports(doc, cbp.AUTHORIZED_HEADING)
    assert allowed == {80, 443, 4002}
    deviations = cbp._table_ports(doc, cbp.DEVIATION_HEADING)
    assert deviations == {25}  # 2525 lives in the Reason prose cell — ignored


def test_real_policy_doc_extracts_declared_ports_only() -> None:
    doc = REPO / cbp.POLICY_DOC
    allowed = cbp._table_ports(doc, cbp.AUTHORIZED_HEADING)
    assert {80, 443, 4001, 4002} <= allowed
    # The gossip relay's loopback port appears only in the Why prose — it must
    # NOT be harvested as an authorized surface (the #1779 bypass).
    assert 7070 not in allowed
    deviations = cbp._table_ports(doc, cbp.DEVIATION_HEADING)
    assert {25, 9090, 9100, 9121, 9187, 8201, 9115, 3478, 5355} <= deviations


def _ports_doc_with_bind_all(port: int) -> str:
    return f"""\
## Live service binds

| Service | Port | Bind | Notes |
|---------|------|------|-------|
| P2P gossip | {port} | `0.0.0.0` | bind-all |
"""


def _policy_authorizing_only_443_via_nginx() -> str:
    return """\
## Authorized public surfaces

| Surface | Port | Where | Why |
|---------|------|-------|-----|
| Blockchain P2P / gossip | 443 via nginx | nginx host | The relay binds `127.0.0.1:7070` on the hub — verified live; no direct public 7070 listener |
"""


def test_bind_all_ignores_prose_mentions(tmp_path: Path) -> None:
    """Mirror-image bypass: ``0.0.0.0`` inside a Notes sentence must not mark
    the row bind-all — only a cell that IS a bind spelling counts."""
    doc = _write(
        tmp_path,
        "ports.md",
        """\
## Live service binds

| Service | Port | Bind | Notes |
|---------|------|------|-------|
| Loopback svc | 9000 | `127.0.0.1` | Earlier drift ran `0.0.0.0` until 2026-11; now pinned |
| Wildcard svc | 9001 | `*` (all) | package default all-interfaces |
| Coturn-like | 9002 | `10.0.0.5` + `127.0.0.1` | LAN-scoped (not `0.0.0.0`) |
""",
    )
    found = cbp.bind_all_services(doc)
    assert found == {"wildcard svc": 9001}


def test_real_ports_doc_bind_all_set() -> None:
    found = cbp.bind_all_services(REPO / cbp.PORTS_DOC)
    # Real bind-all rows only — prose mentions of `0.0.0.0` in the gossip
    # relay, API gateway and coTURN notes must not flag them.
    assert "blockchain p2p (gossip relay)" not in found
    assert "api gateway" not in found
    assert "coturn (stun/turn)" not in found
    assert found["ipfs swarm"] == 4002
    assert found["llmnr"] == 5355
    assert found["postfix"] == 25


def test_main_fails_when_port_appears_only_in_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exact #1779 mutation: a 0.0.0.0 bind on 7070 must FAIL even though
    '7070' appears in the policy's Why cell — the surface port is 443."""
    ports_doc = _write(tmp_path, "SERVICE_PORTS.md", _ports_doc_with_bind_all(7070))
    policy_doc = _write(tmp_path, "NETWORK_POLICY.md", _policy_authorizing_only_443_via_nginx())
    monkeypatch.setattr(cbp, "PORTS_DOC", ports_doc)
    monkeypatch.setattr(cbp, "POLICY_DOC", policy_doc)
    assert cbp.main() == 1
    out = capsys.readouterr().out
    assert "p2p gossip (7070)" in out


def test_main_passes_when_port_column_authorizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ports_doc = _write(tmp_path, "SERVICE_PORTS.md", _ports_doc_with_bind_all(7070))
    policy_doc = _write(
        tmp_path,
        "NETWORK_POLICY.md",
        """\
## Authorized public surfaces

| Surface | Port | Where | Why |
|---------|------|-------|-----|
| Blockchain P2P | 7070 | hub | Direct bind-all surface, reviewed |
""",
    )
    monkeypatch.setattr(cbp, "PORTS_DOC", ports_doc)
    monkeypatch.setattr(cbp, "POLICY_DOC", policy_doc)
    assert cbp.main() == 0
