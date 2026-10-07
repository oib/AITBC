"""The authority balance exporter: ``scripts/monitoring/authority-balances-textfile.py``.

Hub's Prometheus had no balance series, so nothing warned that the escrow settlement
authority was running out of fee float. The exporter derives its watch addresses from the
live chain parameters (``/rpc/state/snapshot``) so a rotation needs no unit edit, reads the
accounts from the local RPC and writes a node_exporter textfile; the alert rules in
``aitbc_hub_rules.yml`` read it. ``AITBC_WATCH_ACCOUNTS`` is the fallback when the parameter
read fails and an extras list for unmanaged roles.

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

SETTLEMENT = "0x" + "11" * 20
BRIDGE = "0x" + "2b" * 20
EXECUTOR_1 = "0x" + "fa" * 20
EXECUTOR_2 = "0x" + "d9" * 20
SETTLEMENT_OLD = "0x" + "03" * 20
BRIDGE_OLD = "0x" + "04" * 20
SLASH = "0x" + "9a" * 20
UNKNOWN = "0x" + "ee" * 20


class _Handler(http.server.BaseHTTPRequestHandler):
    accounts: dict[str, object] = {}
    parameters: dict[str, object] = {}

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path.startswith("/rpc/state/snapshot"):
            if self.parameters is None:
                self.send_response(500)
                self.end_headers()
                return
            body = json.dumps(
                {"chain_parameters": [{"parameter": k, "value": v} for k, v in self.parameters.items()]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
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
    handler = type(
        "Handler",
        (_Handler,),
        {
            "accounts": {},
            "parameters": {
                "escrow_settlement_authority": SETTLEMENT,
                "bridge_release_authority": BRIDGE,
                "bond_slash_authority": SLASH,
                "governance_executors": f"{EXECUTOR_1},{EXECUTOR_2}",
            },
        },
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", handler.accounts, handler.parameters
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

    def test_empty_is_allowed_as_extras_list(self):
        assert exporter.parse_accounts("", allow_empty=True) == []
        assert exporter.parse_accounts(" , ", allow_empty=True) == []

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


class TestFetchParameters:
    def test_reads_the_snapshot(self, rpc):
        url, _, _ = rpc
        assert exporter.fetch_parameters(url) == {
            "escrow_settlement_authority": SETTLEMENT,
            "bridge_release_authority": BRIDGE,
            "bond_slash_authority": SLASH,
            "governance_executors": f"{EXECUTOR_1},{EXECUTOR_2}",
        }

    def test_connection_refused_is_none(self):
        assert exporter.fetch_parameters("http://127.0.0.1:9", timeout=1.0) is None


class TestReadAccount:
    def test_reads_balance_and_nonce(self, rpc):
        url, accounts, _ = rpc
        accounts[SETTLEMENT] = {"address": SETTLEMENT, "balance": 39_728_900, "nonce": 2}
        assert exporter.read_account(url, SETTLEMENT) == (39_728_900, 2)

    def test_missing_account_row_is_a_zero_account(self, rpc):
        url, _accounts, _ = rpc
        assert exporter.read_account(url, UNKNOWN) == (0, 0)

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
        url, accounts, _ = rpc
        accounts[SETTLEMENT] = body
        assert exporter.read_account(url, SETTLEMENT) is None

    def test_connection_refused_is_a_failed_read(self):
        assert exporter.read_account("http://127.0.0.1:9", SETTLEMENT, timeout=1.0) is None


class TestResolveAccounts:
    _PARAMS = {
        "escrow_settlement_authority": SETTLEMENT,
        "bridge_release_authority": BRIDGE,
        "bond_slash_authority": SLASH,
        "governance_executors": f"{EXECUTOR_1},{EXECUTOR_2}",
    }

    def test_parameter_addresses_win(self):
        resolved, stale = exporter.resolve_accounts(dict(self._PARAMS), [("escrow_settlement", SETTLEMENT_OLD)])
        assert resolved == [
            ("escrow_settlement", SETTLEMENT),
            ("bridge_release", BRIDGE),
            ("bond_slash", SLASH),
            ("governance_executor", EXECUTOR_1),
            ("governance_executor", EXECUTOR_2),
        ]
        assert stale == set()

    def test_missing_parameter_falls_back_to_env_and_marks_stale(self):
        params = dict(self._PARAMS)
        del params["bridge_release_authority"]
        resolved, stale = exporter.resolve_accounts(
            params, [("escrow_settlement", SETTLEMENT_OLD), ("bridge_release", BRIDGE_OLD)]
        )
        assert ("bridge_release", BRIDGE_OLD) in resolved
        assert ("escrow_settlement", SETTLEMENT) in resolved
        assert stale == {"bridge_release"}

    def test_failed_parameter_read_falls_back_and_marks_every_managed_role_stale(self):
        resolved, stale = exporter.resolve_accounts(
            None, [("escrow_settlement", SETTLEMENT_OLD), ("bridge_release", BRIDGE_OLD)]
        )
        assert ("bridge_release", BRIDGE_OLD) in resolved
        assert ("escrow_settlement", SETTLEMENT_OLD) in resolved
        assert ("bond_slash", "") in resolved
        assert ("governance_executor", "") in resolved
        assert stale == {"escrow_settlement", "bridge_release", "bond_slash", "governance_executor"}

    def test_no_fallback_leaves_the_role_blind(self):
        resolved, stale = exporter.resolve_accounts(None, [])
        assert ("escrow_settlement", "") in resolved
        assert ("bridge_release", "") in resolved
        assert ("bond_slash", "") in resolved
        assert ("governance_executor", "") in resolved
        assert stale == {"escrow_settlement", "bridge_release", "bond_slash", "governance_executor"}

    def test_malformed_parameter_value_is_a_failed_read(self):
        params = dict(self._PARAMS)
        params["escrow_settlement_authority"] = "0x1234"
        resolved, stale = exporter.resolve_accounts(params, [])
        assert ("escrow_settlement", "") in resolved
        assert stale == {"escrow_settlement"}

    def test_unmanaged_roles_are_always_extras(self):
        resolved, stale = exporter.resolve_accounts(dict(self._PARAMS), [("treasury", SETTLEMENT_OLD)])
        assert ("treasury", SETTLEMENT_OLD) in resolved
        assert stale == set()

    def test_executor_list_parameter_yields_one_entry_per_member(self):
        resolved, stale = exporter.resolve_accounts(dict(self._PARAMS), [])
        assert ("governance_executor", EXECUTOR_1) in resolved
        assert ("governance_executor", EXECUTOR_2) in resolved
        assert stale == set()

    def test_executor_list_with_a_bad_member_watches_the_valid_and_marks_stale(self):
        params = dict(self._PARAMS)
        params["governance_executors"] = f"{EXECUTOR_1},not-an-address,{EXECUTOR_2}"
        resolved, stale = exporter.resolve_accounts(params, [])
        assert ("governance_executor", EXECUTOR_1) in resolved
        assert ("governance_executor", EXECUTOR_2) in resolved
        assert "governance_executor" in stale

    def test_executor_list_missing_falls_back_per_entry(self):
        params = dict(self._PARAMS)
        params["governance_executors"] = ""
        resolved, stale = exporter.resolve_accounts(
            params, [("governance_executor", EXECUTOR_1), ("governance_executor", EXECUTOR_2)]
        )
        assert ("governance_executor", EXECUTOR_1) in resolved
        assert ("governance_executor", EXECUTOR_2) in resolved
        assert "governance_executor" in stale


class TestRender:
    def test_failed_read_has_no_balance_or_nonce_and_says_so(self):
        text = exporter.render(
            [("escrow_settlement", SETTLEMENT, (123, 4)), ("bridge_release", BRIDGE, None)],
            stale_roles=set(),
            now=1_700_000_000.9,
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

    def test_fallback_role_reports_scrape_failure_even_when_the_read_worked(self):
        text = exporter.render(
            [("escrow_settlement", SETTLEMENT_OLD, (123, 4)), ("bridge_release", BRIDGE, (9, 0))],
            stale_roles={"escrow_settlement"},
            now=1_700_000_000,
        )
        samples = _metrics(text)
        # the fallback address's real balance is exported, but scrape_success says the
        # parameter-derived read failed — a stale address must not look clean
        assert samples[f'aitbc_authority_balance_units{{role="escrow_settlement",address="{SETTLEMENT_OLD}"}}'] == 123
        assert samples[f'aitbc_authority_scrape_success{{role="escrow_settlement",address="{SETTLEMENT_OLD}"}}'] == 0
        assert samples[f'aitbc_authority_scrape_success{{role="bridge_release",address="{BRIDGE}"}}'] == 1

    def test_blind_role_reports_empty_address(self):
        text = exporter.render([("escrow_settlement", "", None)], stale_roles={"escrow_settlement"}, now=1_700_000_000)
        samples = _metrics(text)
        assert samples['aitbc_authority_scrape_success{role="escrow_settlement",address=""}'] == 0


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
    def _env(self, monkeypatch, tmp_path, url, accounts=""):
        monkeypatch.setenv("AITBC_WATCH_ACCOUNTS", accounts)
        monkeypatch.setenv("AITBC_RPC_URL", url)
        monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path))

    def test_parameter_derived_reads_succeed(self, rpc, tmp_path, monkeypatch, capsys):
        url, accounts, _ = rpc
        accounts[SETTLEMENT] = {"balance": 32_975_761, "nonce": 0}
        accounts[BRIDGE] = {"balance": 1_800_000, "nonce": 0}
        self._env(monkeypatch, tmp_path, url)
        assert exporter.main() == 0
        samples = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert samples[f'aitbc_authority_balance_units{{role="escrow_settlement",address="{SETTLEMENT}"}}'] == 32_975_761
        assert samples[f'aitbc_authority_balance_units{{role="bridge_release",address="{BRIDGE}"}}'] == 1_800_000
        assert capsys.readouterr().err == ""

    def test_unfunded_authority_is_a_zero_account_not_a_failed_read(self, rpc, tmp_path, monkeypatch, capsys):
        url, accounts, _ = rpc
        accounts[SETTLEMENT] = {"balance": 32_975_761, "nonce": 0}
        # BRIDGE has no account row: the stub answers 404
        self._env(monkeypatch, tmp_path, url)
        assert exporter.main() == 0
        samples = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert samples[f'aitbc_authority_balance_units{{role="bridge_release",address="{BRIDGE}"}}'] == 0
        assert samples[f'aitbc_authority_nonce{{role="bridge_release",address="{BRIDGE}"}}'] == 0
        assert samples[f'aitbc_authority_scrape_success{{role="bridge_release",address="{BRIDGE}"}}'] == 1
        assert capsys.readouterr().err == ""

    def test_failed_parameter_read_falls_back_and_reports_stale(self, tmp_path, monkeypatch, capsys):
        self._env(
            monkeypatch,
            tmp_path,
            "http://127.0.0.1:9",  # nothing listens: snapshot AND accounts both fail
            f"escrow_settlement:{SETTLEMENT_OLD},bridge_release:{BRIDGE_OLD}",
        )
        assert exporter.main() == 1
        samples = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert samples[f'aitbc_authority_scrape_success{{role="escrow_settlement",address="{SETTLEMENT_OLD}"}}'] == 0
        assert "fallback" in capsys.readouterr().err

    def test_rotation_replaces_the_series(self, rpc, tmp_path, monkeypatch):
        url, accounts, parameters = rpc
        accounts[SETTLEMENT_OLD] = {"balance": 33_335_761, "nonce": 48}
        parameters["escrow_settlement_authority"] = SETTLEMENT_OLD
        self._env(monkeypatch, tmp_path, url)
        assert exporter.main() == 0
        first = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert f'aitbc_authority_balance_units{{role="escrow_settlement",address="{SETTLEMENT_OLD}"}}' in first
        # the parameter rotates: the next run watches the new address and the old
        # series disappears from the file entirely, so its alerts resolve
        del accounts[SETTLEMENT_OLD]
        parameters["escrow_settlement_authority"] = SETTLEMENT
        accounts[SETTLEMENT] = {"balance": 32_975_761, "nonce": 0}
        assert exporter.main() == 0
        samples = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert samples[f'aitbc_authority_balance_units{{role="escrow_settlement",address="{SETTLEMENT}"}}'] == 32_975_761
        assert not [k for k in samples if SETTLEMENT_OLD in k]

    def test_executors_are_watched_from_the_parameter_list(self, rpc, tmp_path, monkeypatch, capsys):
        url, accounts, _ = rpc
        accounts[SETTLEMENT] = {"balance": 32_975_761, "nonce": 0}
        accounts[BRIDGE] = {"balance": 0, "nonce": 0}
        accounts[EXECUTOR_1] = {"balance": 9_640_000, "nonce": 1}
        accounts[EXECUTOR_2] = {"balance": 36_000_000, "nonce": 0}
        self._env(monkeypatch, tmp_path, url)
        assert exporter.main() == 0
        samples = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert samples[f'aitbc_authority_balance_units{{role="governance_executor",address="{EXECUTOR_1}"}}'] == 9_640_000
        assert samples[f'aitbc_authority_balance_units{{role="governance_executor",address="{EXECUTOR_2}"}}'] == 36_000_000
        assert capsys.readouterr().err == ""

    def test_extras_run_alongside_derived_roles(self, rpc, tmp_path, monkeypatch):
        url, accounts, _ = rpc
        accounts[SETTLEMENT] = {"balance": 32_975_761, "nonce": 0}
        accounts[BRIDGE] = {"balance": 1_800_000, "nonce": 0}
        accounts[SETTLEMENT_OLD] = {"balance": 0, "nonce": 49}
        self._env(monkeypatch, tmp_path, url, f"settlement_retired:{SETTLEMENT_OLD}")
        assert exporter.main() == 0
        samples = _metrics((tmp_path / exporter.OUTPUT_NAME).read_text())
        assert samples[f'aitbc_authority_balance_units{{role="settlement_retired",address="{SETTLEMENT_OLD}"}}'] == 0

    def test_bad_config_exits_2_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        self._env(monkeypatch, tmp_path, "http://127.0.0.1:9", "not-a-pair")
        assert exporter.main() == 2
        assert list(tmp_path.iterdir()) == []
        assert "expected role:0x" in capsys.readouterr().err


class TestFilesAgree:
    """The rules, the script and the unit file have to name the same things.

    Since the T35 split the authority rules live in ``aitbc_hub_rules.yml``
    (loaded on the exporter host only); the shared ``aitbc_rules.yml`` must
    carry none of them.
    """

    def test_every_metric_the_rules_use_is_emitted(self):
        # T35 scoped the authority alerts to the hub-only file; the shared
        # rules file no longer references the aitbc_authority_* series.
        rules = (MONITORING / "aitbc_hub_rules.yml").read_text()
        used = set(re.findall(r"\baitbc_authority_[a-z_]+", rules))
        assert used, "the hub rules no longer read the authority series"
        emitted = set(re.findall(r"\baitbc_authority_[a-z_]+", exporter.render([("r", SETTLEMENT, (1, 1))], set(), now=1)))
        assert used <= emitted, used - emitted

    def test_roles_the_rules_use_are_covered(self):
        """Rule-labelled roles must be produced by the unit env list or the parameters."""
        unit = (MONITORING / "aitbc-authority-balances.service").read_text()
        raw = re.search(r"^Environment=AITBC_WATCH_ACCOUNTS=(\S+)$", unit, re.M)
        unit_roles = {role for role, _ in exporter.parse_accounts(raw.group(1), allow_empty=True)} if raw else set()
        covered = unit_roles | set(exporter.PARAMETER_ROLES) | set(exporter.LIST_PARAMETER_ROLES)
        rules = (MONITORING / "aitbc_hub_rules.yml").read_text()
        labelled = set(re.findall(r'aitbc_authority_[a-z_]+\{role="([a-z_]+)"', rules))
        assert labelled and labelled <= covered, (labelled, covered)

    def test_shared_rules_file_has_no_authority_rules(self):
        rules = (MONITORING / "aitbc_rules.yml").read_text()
        assert not re.findall(r"\baitbc_authority_[a-z_]+", rules), (
            "authority rules belong in aitbc_hub_rules.yml; the shared file is loaded on hosts without the exporter"
        )

    def test_unit_runs_the_script_from_the_repo_and_may_write_the_textfile_dir(self):
        unit = (MONITORING / "aitbc-authority-balances.service").read_text()
        assert "/opt/aitbc/scripts/monitoring/authority-balances-textfile.py" in unit
        assert os.access(MONITORING / "authority-balances-textfile.py", os.X_OK)
        directory = re.search(r"^Environment=AITBC_TEXTFILE_DIR=(\S+)$", unit, re.M).group(1)
        assert f"ReadWritePaths={directory}" in unit
