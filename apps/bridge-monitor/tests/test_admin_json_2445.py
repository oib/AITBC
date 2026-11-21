"""#2445 BRIDGE-SECURITY-STATUS-VALIDATORS-1 pins — admin.py --json + not-found rc.

``aitbc bridge deposits --output json`` shells ``bridge_monitor.admin``;
the admin needs a machine-readable mode, and an absent ``status`` row
must exit distinctly (3) so the CLI can map it to the shared not-found
exit code 2 instead of a generic failure (4).
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bridge_monitor import admin, storage  # noqa: E402


@pytest.fixture
def admin_db(tmp_path, monkeypatch):
    """Ledger DB pointed at tmp_path for admin.main() invocations."""
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "DB_PATH", str(tmp_path / "admin_deposits.db"))
    storage.init_db()
    return storage


def _run_admin(monkeypatch, tmp_path, *argv: str) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        ["bridge-admin", "--env-file", str(tmp_path / "missing.env"), *argv],
    )
    return admin.main()


class TestAdminJson:
    def test_status_json_emits_row(self, admin_db, tmp_path, monkeypatch, capsys):
        admin_db.create_deposit("0xjs1", "0xf", "1", "")
        rc = _run_admin(monkeypatch, tmp_path, "--json", "status", "0xjs1")
        assert rc == 0
        row = json.loads(capsys.readouterr().out)
        assert row["eth_tx_hash"] == "0xjs1"
        assert "signed_tx" not in row or row["signed_tx"] in ("", None, "<0 chars>")

    def test_status_json_redacts_signed_tx(self, admin_db, tmp_path, monkeypatch, capsys):
        admin_db.create_deposit("0xjs2", "0xf", "1", "")
        admin_db.update_deposit("0xjs2", signed_tx="0xsignedblob")
        rc = _run_admin(monkeypatch, tmp_path, "--json", "status", "0xjs2")
        assert rc == 0
        row = json.loads(capsys.readouterr().out)
        assert row["signed_tx"] == "<12 chars>"

    def test_status_missing_row_exits_3(self, admin_db, tmp_path, monkeypatch, capsys):
        rc = _run_admin(monkeypatch, tmp_path, "--json", "status", "0xabsent")
        assert rc == 3
        body = json.loads(capsys.readouterr().out)
        assert body == {"error": "not_found", "tx_hash": "0xabsent"}

    def test_list_json_emits_rows(self, admin_db, tmp_path, monkeypatch, capsys):
        admin_db.create_deposit("0xjl1", "0xf", "1", "")
        rc = _run_admin(monkeypatch, tmp_path, "--json", "list", "--limit", "5")
        assert rc == 0
        rows = json.loads(capsys.readouterr().out)
        assert [r["eth_tx_hash"] for r in rows] == ["0xjl1"]

    def test_list_bad_status_json_error(self, admin_db, tmp_path, monkeypatch, capsys):
        rc = _run_admin(monkeypatch, tmp_path, "--json", "list", "--status", "bogus")
        assert rc == 2
        body = json.loads(capsys.readouterr().out)
        assert body["error"] == "unknown_status"
