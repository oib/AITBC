"""The authority balance exporter: ``scripts/monitoring/authority-balances-textfile.py``.

Hub's Prometheus had no balance series, so nothing warned that the escrow settlement
authority was running out of fee float. The exporter reads two accounts from the local RPC
and writes a node_exporter textfile; the alert rules in ``aitbc_rules.yml`` read it.

The tests run against a stub RPC server and check what lands on disk, plus the contract
between the three files that have to agree: the metric names and role labels the rules use
must be the ones the script emits and the unit file configures.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import re
import stat
import threading
from pathlib import Path

import pytest

MONITORING = Path(__file__).resolve().parents[2] / "scripts" / "monitoring"

_spec = importlib.util.spec_from_file_location("authority_balances_textfile", MONITORING / "authority-balances-textfile.py")
assert _spec is not None and _spec.loader is not None
exporter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exporter)

SETTLEMENT = "0x" + "03" * 20
BRIDGE = "0x" + "2b" * 20
UNKNOWN = "0x" + "ee" * 20


class _Handler(http.server.BaseHTTPRequestHandler):
    accounts: dict[str, object] = {}

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        address = self.path.rsplit("/", 1)[-1]
        if not self.path.startswith("/rpc/accounts/") or address not in self.accounts:
            self.send_response(404)
            self.end_headers()
            return
        body = self.accounts[address]
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:  # silence the test output
        pass


@pytest.fixture
def rpc():
    handler = type("Handler", (_Handler,), {"accounts": {}})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", handler.accounts
    finally:
        server.shutdown()
        server.server_close()


def _metrics(text: str) -> dict[str, float]:
    """``name{labels}`` -> value for every sample line."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            key, value = line.rsplit(" ", 1)
            out[key] = float(value)
    return out


class TestParseAccounts:
    def test_pairs_are_returned_in_order(self):
        assert exporter.parse_accounts(f"escrow_settlement:{SETTLEMENT}, bridge_release:{BRIDGE}") == [
            ("escrow_settlement", SETTLEMENT),
            ("bridge_release", BRIDGE),
        ]

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            " , ",
            SETTLEMENT,  # no role
            f"Escrow:{SETTLEMENT}",  # role must be lower-case snake
            "escrow:0x1234",  # short address
            f"escrow:{SETTLEMENT[:-1]}g",  # not hex
            f'es"crow:{SETTLEMENT}',  # a label value must never break the exposition format
        ],
    )
    def test_bad_entries_are_rejected(self, raw):
        with pytest.raises(ValueError):
            exporter.parse_accounts(raw)


class TestReadAccount:
    def test_reads_balance_and_nonce(self, rpc):
        url, accounts = rpc
        accounts[SETTLEMENT] = {"address": SETTLEMENT, "balance": 39_728_900, "nonce": 2}
        assert exporter.read_account(url, SETTLEMENT) == (39_728_900, 2)

    def test_unknown_account_is_a_failed_read(self, rpc):
        url, _ = rpc
        assert exporter.read_account(url, UNKNOWN) is None

    @pytest.mark.parametrize(
        "body",
        [
            b"not json",
            {"balance": 5},  # no nonce
            {"balance": "5", "nonce": 0},  # a string is not a balance
            {"balance": True, "nonce": 0},  # bool is an int in Python and must not pass
            {"balance": 5.0, "nonce": 0},
            [],
        ],
    )
    def test_unusable_answers_are_a_failed_read(self, rpc, body):
        url, accounts = rpc
        accounts[SETTLEMENT] = body
        assert exporter.read_account(url, SETTLEMENT) is None

    def test_connection_refused_is_a_failed_read(self):
        assert exporter.read_account("http://127.0.0.1:9", SETTLEMENT, timeout=1.0) is None


class TestRender:
    def test_failed_read_has_no_balance_or_nonce_and_says_so(self):
        text = exporter.render(
            [("escrow_settlement", SETTLEMENT, (123, 4)), ("bridge_release", BRIDGE, None)], now=1_700_000_000.9
        )
        samples = _metrics(text)
        assert samples[f'aitbc_authority_balance_units{{role="escrow_settlement",address="{SETTLEMENT}"}}'] == 123
        assert samples[f'aitbc_authority_nonce{{role="escrow_settlement",address="{SETTLEMENT}"}}'] == 4
        assert samples[f'aitbc_authority_scrape_success{{role="escrow_settlement",address="{SETTLEMENT}"}}'] == 1
        assert samples[f'aitbc_authority_scrape_success{{role="bridge_release",address="{BRIDGE}"}}'] == 0
        # a stale value must not read as current
        assert not [k for k in samples if "bridge_release" in k and ("balance_units" in k or "nonce" in k)]
        assert samples["aitbc_authority_scrape_timestamp_seconds"] == 1_700_000_000
        assert text.endswith("\n")


class TestWriteAtomic:
    def test_writes_world_readable_file_and_leaves_no_temp_file(self, tmp_path):
        exporter.write_atomic(str(tmp_path), "first\n")
        exporter.write_atomic(str(tmp_path), "second\n")
        target = tmp_path / exporter.OUTPUT_NAME
        assert target.read_text() == "second\n"
        assert stat.S_IMODE(target.stat().st_mode) == 0o644  # node_exporter runs as another user
        assert [p.name for p in tmp_path.iterdir()] == [exporter.OUTPUT_NAME]

    def test_failed_write_keeps_the_previous_file(self, tmp_path, monkeypatch):
        exporter.write_atomic(str(tmp_path), "good\n")

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(exporter.os, "replace", boom)
        with pytest.raises(OSError):
            exporter.write_atomic(str(tmp_path), "bad\n")
        assert (tmp_path / exporter.OUTPUT_NAME).read_text() == "good\n"
        assert [p.name for p in tmp_path.iterdir()] == [exporter.OUTPUT_NAME]


class TestMain:
    def _env(self, monkeypatch, tmp_path, url, accounts):
        monkeypatch.setenv("AITBC_WATCH_ACCOUNTS", accounts)
        monkeypatch.setenv("AITBC_RPC_URL", url)
        monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path))

    def test_all_reads_succeed(self, rpc, tmp_path, monkeypatch, capsys):
        url, accounts = rpc
        accounts[SETTLEMENT] = {"balance": 8_000_000, "nonce": 2}
        accounts[BRIDGE] = {"balance": 1_800_000, "nonce": 0}
        self._env(monkeypatch, tmp_path, url, f"escrow_settlement:{SETTLEMENT},bridge_release:{BRIDGE}")
        assert exporter.main() == 0
        samples = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert samples[f'aitbc_authority_balance_units{{role="escrow_settlement",address="{SETTLEMENT}"}}'] == 8_000_000
        assert samples[f'aitbc_authority_balance_units{{role="bridge_release",address="{BRIDGE}"}}'] == 1_800_000
        assert capsys.readouterr().err == ""

    def test_one_failed_read_exits_1_but_still_writes_the_file(self, rpc, tmp_path, monkeypatch, capsys):
        url, accounts = rpc
        accounts[SETTLEMENT] = {"balance": 8_000_000, "nonce": 2}
        self._env(monkeypatch, tmp_path, url, f"escrow_settlement:{SETTLEMENT},bridge_release:{BRIDGE}")
        assert exporter.main() == 1
        samples = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert samples[f'aitbc_authority_scrape_success{{role="bridge_release",address="{BRIDGE}"}}'] == 0
        assert samples[f'aitbc_authority_scrape_success{{role="escrow_settlement",address="{SETTLEMENT}"}}'] == 1
        assert "bridge_release" in capsys.readouterr().err

    def test_bad_config_exits_2_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        self._env(monkeypatch, tmp_path, "http://127.0.0.1:9", "not-a-pair")
        assert exporter.main() == 2
        assert list(tmp_path.iterdir()) == []
        assert "expected role:0x" in capsys.readouterr().err

    def test_missing_config_exits_2(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AITBC_WATCH_ACCOUNTS", raising=False)
        monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path))
        assert exporter.main() == 2


class TestFilesAgree:
    """The rules, the script and the unit file have to name the same things."""

    def test_every_metric_the_rules_use_is_emitted(self):
        rules = (MONITORING / "aitbc_rules.yml").read_text()
        used = set(re.findall(r"\baitbc_authority_[a-z_]+", rules))
        assert used, "the rules no longer read the authority series"
        emitted = set(re.findall(r"\baitbc_authority_[a-z_]+", exporter.render([("r", SETTLEMENT, (1, 1))], now=1)))
        assert used <= emitted, used - emitted

    def test_unit_file_roles_match_the_rule_labels(self):
        unit = (MONITORING / "aitbc-authority-balances.service").read_text()
        raw = re.search(r"^Environment=AITBC_WATCH_ACCOUNTS=(\S+)$", unit, re.M)
        assert raw, "the unit does not set AITBC_WATCH_ACCOUNTS"
        roles = {role for role, _ in exporter.parse_accounts(raw.group(1))}
        rules = (MONITORING / "aitbc_rules.yml").read_text()
        labelled = set(re.findall(r'aitbc_authority_[a-z_]+\{role="([a-z_]+)"', rules))
        assert labelled and labelled <= roles, (labelled, roles)

    def test_unit_runs_the_script_from_the_repo_and_may_write_the_textfile_dir(self):
        unit = (MONITORING / "aitbc-authority-balances.service").read_text()
        assert "/opt/aitbc/scripts/monitoring/authority-balances-textfile.py" in unit
        assert os.access(MONITORING / "authority-balances-textfile.py", os.X_OK)
        directory = re.search(r"^Environment=AITBC_TEXTFILE_DIR=(\S+)$", unit, re.M).group(1)
        assert f"ReadWritePaths={directory}" in unit
