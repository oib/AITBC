"""Tests for ``scripts/ops/governance_parameter_change.py``.

The tool is the offline-executor path for authority-parameter changes: the
node-side execute route signs with the node key, so the operator signs the
``GOVERNANCE_EXECUTE`` envelope with the workstation-held executor key and
submits it to ``/rpc/transaction`` directly. These tests run against a faked
RPC layer — no live chain, and the executor key is a throwaway generated in
the test.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import sys
import urllib.error
from pathlib import Path

import pytest
from eth_account import Account

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "governance_parameter_change.py"

_spec = importlib.util.spec_from_file_location("governance_parameter_change", SCRIPT)
assert _spec is not None and _spec.loader is not None
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)

CHAIN_ID = "ait-test"
EXECUTOR = "0x04fE87ac0E6a9bcbe7554eb29ea86312BF817cCC"
TARGET = "0x1111111111111111111111111111111111111111"
OLD_VALUE = "0x2222222222222222222222222222222222222222"


def _http_error(code: int, body: dict | None = None) -> urllib.error.HTTPError:
    payload = json.dumps(body or {"detail": "err"}).encode()
    return urllib.error.HTTPError("http://fake", code, "err", {}, io.BytesIO(payload))


class FakeRPC:
    """Answers the handful of endpoints the tool touches."""

    FUNDED = 10_000_000  # comfortably above fee + headroom

    def __init__(
        self,
        params: dict[str, str] | None = None,
        nonces: dict[str, int] | None = None,
        seal_after: int = 1,
        landed: dict[str, str] | None = None,
        balances: dict[str, int] | None = None,
    ) -> None:
        self.params = dict(params or {})
        self.nonces = dict(nonces or {})
        self.posted: list[tuple[str, dict]] = []
        self.tx_polls = 0
        self.seal_after = seal_after
        # param -> value the snapshot reports once a tx has been posted
        self.landed = dict(landed or {})
        # account rows exist iff the address is in nonces; balance defaults funded
        self.balances = dict(balances or {})

    def get(self, base: str, path: str) -> dict:
        if path == "/rpc/info":
            return {"chain_id": CHAIN_ID}
        if path.startswith("/rpc/state/snapshot"):
            params = dict(self.params)
            if self.posted:
                params.update(self.landed)
            return {"chain_parameters": [{"parameter": k, "value": v} for k, v in params.items()]}
        if path.startswith("/rpc/account/"):
            address = path.split("/rpc/account/")[1].split("?")[0]
            if address not in self.nonces:
                raise _http_error(404)
            return {
                "address": address,
                "balance": self.balances.get(address, self.FUNDED),
                "nonce": self.nonces[address],
                "chain_id": CHAIN_ID,
            }
        if path.startswith("/rpc/transaction/"):
            self.tx_polls += 1
            if self.tx_polls < self.seal_after:
                raise _http_error(404)
            return {"status": "confirmed", "block_height": 4242, "tx_hash": "0xdeadbeef"}
        raise _http_error(404)

    def post(self, base: str, path: str, body: dict) -> tuple[int, dict]:
        assert path == "/rpc/transaction"
        self.posted.append((path, body))
        return 200, {"success": True, "transaction_hash": "0xdeadbeef"}


def _params(**overrides: str) -> dict[str, str]:
    base = {
        "governance_executors": EXECUTOR,
        "escrow_fee_recipient": OLD_VALUE,
        "escrow_settlement_authority": OLD_VALUE,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeRPC:
    rpc = FakeRPC(params=_params())
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    return rpc


def _write_key(path: Path, account: Account) -> str:
    """Write a key file with the mode the tool demands (0600, not the umask default)."""
    path.write_text(account.key.hex())
    os.chmod(path, 0o600)
    return str(path)


@pytest.fixture()
def key_file(tmp_path: Path) -> tuple[str, str]:
    """Throwaway executor key: returns (path, address). The file holds raw hex."""
    account = Account.create()
    return _write_key(tmp_path / "executor.key", account), account.address


def _argv(*args: str) -> list[str]:
    return ["tool", "--rpc-url", "http://fake", *args]


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", argv)
    rc = tool.main()
    assert rc == 0


# --- plan -----------------------------------------------------------------


def test_plan_prints_change_and_digest(
    fake: FakeRPC, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(
        monkeypatch,
        _argv("plan", "--parameter", "escrow_fee_recipient", "--value", TARGET),
    )
    out = capsys.readouterr().out
    assert "escrow_fee_recipient" in out
    assert OLD_VALUE in out
    assert TARGET in out
    assert EXECUTOR in out  # sole on-chain executor picked up as the default
    assert "GOVERNANCE_EXECUTE" in out
    assert "signing digest" in out
    assert "0x" in out.split("signing digest")[1]


def test_plan_marks_noop(fake: FakeRPC, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _run(monkeypatch, _argv("plan", "--parameter", "escrow_fee_recipient", "--value", OLD_VALUE))
    assert "already equals the target" in capsys.readouterr().out


def test_plan_unknown_parameter(fake: FakeRPC, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        _run(monkeypatch, _argv("plan", "--parameter", "some_random_param", "--value", TARGET))


@pytest.mark.parametrize(
    "bad",
    [
        "0x123",  # too short
        "0x" + "g" * 40,  # non-hex
        "0x" + "0" * 40,  # zero address
        "ait1abcdef",  # legacy prefix
        f"{TARGET},0x123",  # one bad element in a list
    ],
)
def test_refuses_bad_targets(fake: FakeRPC, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    with pytest.raises(SystemExit):
        _run(monkeypatch, _argv("plan", "--parameter", "escrow_fee_recipient", "--value", bad))


def test_executor_list_value_validates() -> None:
    assert tool._validate_target(f"{TARGET}, {OLD_VALUE}") == [TARGET, OLD_VALUE]


# --- sign-submit refusals ---------------------------------------------------


def test_refuses_without_confirm(fake: FakeRPC, key_file: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    path, _ = key_file
    with pytest.raises(SystemExit):
        _run(
            monkeypatch,
            _argv("sign-submit", "--parameter", "escrow_fee_recipient", "--value", TARGET, "--key-file", path),
        )
    assert fake.posted == []


def test_refuses_noop_change(fake: FakeRPC, key_file: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    path, _ = key_file
    with pytest.raises(SystemExit):
        _run(
            monkeypatch,
            _argv(
                "sign-submit",
                "--parameter",
                "escrow_fee_recipient",
                "--value",
                OLD_VALUE,
                "--key-file",
                path,
                "--confirm",
            ),
        )
    assert fake.posted == []


def test_refuses_key_not_in_executor_set(fake: FakeRPC, key_file: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """A throwaway key derives to an address that is not the on-chain executor."""
    path, _ = key_file
    with pytest.raises(SystemExit):
        _run(
            monkeypatch,
            _argv(
                "sign-submit",
                "--parameter",
                "escrow_fee_recipient",
                "--value",
                TARGET,
                "--key-file",
                path,
                "--confirm",
            ),
        )
    assert fake.posted == []


def test_refuses_missing_key_file(fake: FakeRPC, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit):
        _run(
            monkeypatch,
            _argv(
                "sign-submit",
                "--parameter",
                "escrow_fee_recipient",
                "--value",
                TARGET,
                "--key-file",
                "/nonexistent/executor.key",
                "--confirm",
            ),
        )
    assert fake.posted == []


# --- sign-submit happy path -------------------------------------------------


def _executor_key_file(tmp_path: Path) -> tuple[str, Account]:
    """A throwaway key whose derived address the caller registers as the
    on-chain executor (the fake's governance_executors is set to match)."""
    account = Account.create()
    return _write_key(tmp_path / "executor.key", account), account


def test_sign_submit_submits_signed_tx_and_reads_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, account = _executor_key_file(tmp_path)
    rpc = FakeRPC(
        params=_params(governance_executors=account.address),
        nonces={account.address: 7},
        seal_after=2,
        landed={"escrow_fee_recipient": TARGET},
    )
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)

    _run(
        monkeypatch,
        _argv(
            "sign-submit",
            "--parameter",
            "escrow_fee_recipient",
            "--value",
            TARGET,
            "--key-file",
            key_path,
            "--confirm",
            "--timeout",
            "30",
        ),
    )

    assert len(rpc.posted) == 1
    _, body = rpc.posted[0]
    tx = body["signed_tx"]
    assert tx["type"] == "GOVERNANCE_EXECUTE"
    assert tx["from"] == account.address == tx["to"]
    assert tx["nonce"] == 7
    assert tx["fee"] == tool.DEFAULT_TX_FEE_UNITS
    payload = tx["payload"]
    assert payload["executor"] == account.address
    assert payload["execution_payload"] == {
        "action": "parameter_change",
        "parameter": "escrow_fee_recipient",
        "value": TARGET,
    }
    # The node's intake recovers the sender from the signature — verify it here
    # the same way the chain would.
    assert tool.verify_transaction_signature(tx, tx["signature"], account.address)

    out = capsys.readouterr().out
    assert "sealed at block 4242" in out
    assert f"{OLD_VALUE} -> {TARGET}" in out


def test_output_never_contains_key_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, account = _executor_key_file(tmp_path)
    rpc = FakeRPC(
        params=_params(governance_executors=account.address),
        nonces={account.address: 0},
        landed={"escrow_fee_recipient": TARGET},
    )
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)

    _run(
        monkeypatch,
        _argv(
            "sign-submit",
            "--parameter",
            "escrow_fee_recipient",
            "--value",
            TARGET,
            "--key-file",
            key_path,
            "--confirm",
            "--timeout",
            "10",
        ),
    )
    captured = capsys.readouterr()
    key_hex = account.key.hex().removeprefix("0x")
    assert key_hex not in captured.out
    assert key_hex not in captured.err
    assert f"0x{key_hex}" not in captured.out
    # The key file path may appear; the 64-hex body must not.
    assert rpc.posted and rpc.posted[0][1]["signed_tx"]["signature"]  # sanity: the run actually signed


# --- executor lock-out guard, key-file mode, proposal-id --------------------

OTHER = "0x3333333333333333333333333333333333333333"


def _submit_argv(key_path: str, parameter: str = "escrow_fee_recipient", value: str = TARGET, *extra: str) -> list[str]:
    return _argv(
        "sign-submit",
        "--parameter",
        parameter,
        "--value",
        value,
        "--key-file",
        key_path,
        "--confirm",
        "--timeout",
        "10",
        *extra,
    )


def test_refuses_group_readable_key_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = Account.create()
    path = tmp_path / "executor.key"
    path.write_text(account.key.hex())
    os.chmod(path, 0o644)
    rpc = FakeRPC(params=_params(governance_executors=account.address), nonces={account.address: 0})
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    with pytest.raises(SystemExit):
        _run(monkeypatch, _submit_argv(str(path)))
    assert "chmod 600" in capsys.readouterr().err
    assert rpc.posted == []


def test_executor_list_dropping_signer_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_path, account = _executor_key_file(tmp_path)
    rpc = FakeRPC(params=_params(governance_executors=account.address), nonces={account.address: 0})
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    new_list = f"{OTHER},{OLD_VALUE}"  # signer absent — would lock out every executor
    with pytest.raises(SystemExit):
        _run(monkeypatch, _submit_argv(key_path, "governance_executors", new_list))
    assert rpc.posted == []


def test_executor_list_keeping_signer_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, account = _executor_key_file(tmp_path)
    new_list = f"{account.address},{OTHER}"
    rpc = FakeRPC(
        params=_params(governance_executors=account.address),
        nonces={account.address: 0},
        landed={"governance_executors": new_list},
    )
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    _run(monkeypatch, _submit_argv(key_path, "governance_executors", new_list))
    assert len(rpc.posted) == 1


def test_executor_rotation_with_proof_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, signer = _executor_key_file(tmp_path)
    proof = Account.create()
    proof_path = _write_key(tmp_path / "new_executor.key", proof)
    new_list = f"{proof.address},{OTHER}"  # signer dropped; proof key survives
    rpc = FakeRPC(
        params=_params(governance_executors=signer.address),
        nonces={signer.address: 0, proof.address: 0},
        landed={"governance_executors": new_list},
    )
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    _run(
        monkeypatch,
        _submit_argv(key_path, "governance_executors", new_list, "--proof-key-file", proof_path),
    )
    assert len(rpc.posted) == 1
    assert proof.address in capsys.readouterr().out


def test_proof_key_not_in_new_list_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_path, signer = _executor_key_file(tmp_path)
    proof = Account.create()
    proof_path = _write_key(tmp_path / "unrelated.key", proof)
    rpc = FakeRPC(params=_params(governance_executors=signer.address), nonces={signer.address: 0})
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    with pytest.raises(SystemExit):
        _run(
            monkeypatch,
            _submit_argv(key_path, "governance_executors", f"{OTHER},{OLD_VALUE}", "--proof-key-file", proof_path),
        )
    assert rpc.posted == []


def test_plan_warns_when_executor_dropped(
    fake: FakeRPC, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(monkeypatch, _argv("plan", "--parameter", "governance_executors", "--value", f"{TARGET},{OTHER}"))
    assert "permanently locks" in capsys.readouterr().err


def test_refuses_underfunded_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, account = _executor_key_file(tmp_path)
    low = tool.DEFAULT_TX_FEE_UNITS  # covers the fee but not the headroom
    rpc = FakeRPC(
        params=_params(governance_executors=account.address),
        nonces={account.address: 0},
        balances={account.address: low},
    )
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    with pytest.raises(SystemExit):
        _run(monkeypatch, _submit_argv(key_path))
    err = capsys.readouterr().err
    assert account.address in err
    assert str(low) in err
    assert str(tool.REQUIRED_BALANCE_UNITS) in err
    assert rpc.posted == []


def test_refuses_unfunded_proof_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A surviving executor that cannot afford its own fee is not a survivor."""
    key_path, signer = _executor_key_file(tmp_path)
    proof = Account.create()
    proof_path = _write_key(tmp_path / "broke_executor.key", proof)
    new_list = f"{proof.address},{OTHER}"
    rpc = FakeRPC(
        params=_params(governance_executors=signer.address),
        nonces={signer.address: 0, proof.address: 0},
        balances={proof.address: 0},
    )
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    with pytest.raises(SystemExit):
        _run(monkeypatch, _submit_argv(key_path, "governance_executors", new_list, "--proof-key-file", proof_path))
    assert rpc.posted == []


def test_absent_executor_account_is_zero_balance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """404 from /rpc/account reads as nonce 0 / balance 0 — and balance 0 refuses."""
    key_path, account = _executor_key_file(tmp_path)
    rpc = FakeRPC(params=_params(governance_executors=account.address), nonces={})
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    monkeypatch.setattr(tool, "_rpc_post", rpc.post)
    with pytest.raises(SystemExit):
        _run(monkeypatch, _submit_argv(key_path))
    assert rpc.posted == []


def test_plan_warns_on_low_balance_without_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    account = Account.create()
    rpc = FakeRPC(
        params=_params(governance_executors=account.address),
        nonces={account.address: 0},
        balances={account.address: 0},
    )
    monkeypatch.setattr(tool, "_rpc_get", rpc.get)
    _run(monkeypatch, _argv("plan", "--parameter", "escrow_fee_recipient", "--value", TARGET))
    captured = capsys.readouterr()
    assert "balance 0" in captured.out
    assert "sign-submit would refuse" in captured.err


def test_default_proposal_id_carries_parameter_date_and_nonce(
    fake: FakeRPC, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unique default id: parameter + date + signer nonce, so a second same-day
    change to the same parameter gets a different label (the nonce moved)."""
    _run(monkeypatch, _argv("plan", "--parameter", "escrow_fee_recipient", "--value", TARGET))
    match = re.search(r"proposal_id: (manual-\S+)", capsys.readouterr().out)
    assert match is not None
    assert re.fullmatch(r"manual-escrow_fee_recipient-\d{4}-\d{2}-\d{2}-n\d+", match.group(1))
