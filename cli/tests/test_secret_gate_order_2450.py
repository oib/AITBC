"""#2450: one gate order for every secret-bearing leaf — wallet first, then
the password source.

Before this change ``transactions send``/``batch``, ``ipfs island
subscribe``/``swarm-key``, ``auth login`` and ``bond`` resolved the
``--password-file``/``--password-stdin`` source *before* checking the
wallet exists, so the same bad input produced a password-file refusal on
some leaves and a wallet refusal on others. All leaves now check the
wallet first; the password source is only consulted once the wallet
resolves. Top-level ``stake``/``unstake``/``liquidity-stake`` also gained
the shared ``--password``/``--password-file``/``--password-stdin`` trio
the ``aitbc wallet`` leaves already had.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def wallet_env(tmp_path, monkeypatch):
    """Isolated HOME with one file wallet ``w1`` and no password material."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHAIN_ID", "test")
    wallet_dir = tmp_path / ".aitbc" / "wallets"
    wallet_dir.mkdir(parents=True)
    (wallet_dir / "w1.json").write_text(
        json.dumps(
            {
                "address": "0x" + "11" * 20,
                "private_key": "0x" + "22" * 32,
            }
        )
    )
    return tmp_path


def _run(monkeypatch, capsys, argv):
    from aitbc_cli.core.main import main

    code = main(["--output", "json", *argv])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


MISSING_WALLET = "nosuch2450"
BAD_PW_FILE = "/tmp/definitely-nosuch-pw-2450.txt"


def test_send_missing_wallet_beats_bad_password_file(wallet_env, monkeypatch, capsys):
    """The sampled pair from the issue: same input must give the wallet
    refusal on both leaves — wallet gate first."""
    code, out = _run(
        monkeypatch,
        capsys,
        [
            "transactions",
            "send",
            "--from",
            MISSING_WALLET,
            "--to",
            "0x" + "11" * 20,
            "--amount",
            "1",
            "--password-file",
            BAD_PW_FILE,
        ],
    )
    assert code != 0
    assert f"Wallet '{MISSING_WALLET}' not found" in out
    assert "Cannot read password file" not in out


def test_send_existing_wallet_reaches_password_gate(wallet_env, monkeypatch, capsys):
    """Wallet resolves -> the password source is the next gate."""
    code, out = _run(
        monkeypatch,
        capsys,
        [
            "transactions",
            "send",
            "--from",
            "w1",
            "--to",
            "0x" + "11" * 20,
            "--amount",
            "1",
            "--password-file",
            BAD_PW_FILE,
        ],
    )
    assert code != 0
    assert "Cannot read password file" in out


def test_ipfs_subscribe_missing_wallet_beats_bad_password_file(wallet_env, monkeypatch, capsys):
    code, out = _run(
        monkeypatch,
        capsys,
        [
            "ipfs",
            "island",
            "subscribe",
            "--wallet",
            MISSING_WALLET,
            "--to",
            "0x" + "11" * 20,
            "--island-id",
            "i1",
            "--amount",
            "1",
            "--password-file",
            BAD_PW_FILE,
        ],
    )
    assert code != 0
    assert f"Wallet '{MISSING_WALLET}' not found" in out
    assert "Cannot read password file" not in out


def test_ipfs_swarm_key_missing_wallet_beats_bad_password_file(wallet_env, monkeypatch, capsys):
    code, out = _run(
        monkeypatch,
        capsys,
        [
            "ipfs",
            "island",
            "swarm-key",
            "--wallet",
            MISSING_WALLET,
            "--island-id",
            "i1",
            "--password-file",
            BAD_PW_FILE,
        ],
    )
    assert code != 0
    assert f"Wallet '{MISSING_WALLET}' not found" in out
    assert "Cannot read password file" not in out


def test_stake_accepts_password_trio_and_wallet_gate_first(wallet_env, monkeypatch, capsys):
    """#2450 item 2: top-level stake exposes the secret trio; the wallet
    gate still fires before the password source."""
    code, out = _run(
        monkeypatch,
        capsys,
        [
            "stake",
            "--amount",
            "1",
            "--duration",
            "1",
            "--wallet-name",
            MISSING_WALLET,
            "--password-file",
            BAD_PW_FILE,
        ],
    )
    assert code == 2
    assert f"Wallet '{MISSING_WALLET}' not found" in out
    assert "Cannot read password file" not in out
    assert "No such option '--password-file'" not in out


def test_stake_existing_wallet_reaches_password_gate(wallet_env, monkeypatch, capsys):
    code, out = _run(
        monkeypatch,
        capsys,
        [
            "stake",
            "--amount",
            "1",
            "--duration",
            "1",
            "--wallet-name",
            "w1",
            "--password-file",
            BAD_PW_FILE,
        ],
    )
    assert code != 0
    assert "Cannot read password file" in out


def test_unstake_and_liquidity_stake_accept_password_trio(wallet_env, monkeypatch, capsys):
    for argv in (
        ["unstake", "--stake-id", "1", "--wallet-name", MISSING_WALLET, "--password-file", BAD_PW_FILE],
        ["liquidity-stake", "--amount", "1", "--wallet-name", MISSING_WALLET, "--password-file", BAD_PW_FILE],
    ):
        code, out = _run(monkeypatch, capsys, argv)
        # liquidity-stake's exit class is normalised to NotFoundError/2 by
        # #2448 (verify-2448); until that lands it still exits 1 — the gate
        # order and the accepted option are what this test pins.
        assert code != 0, (argv, out)
        assert f"Wallet '{MISSING_WALLET}' not found" in out
        assert "No such option '--password-file'" not in out


def test_batch_missing_first_wallet_beats_bad_password_file(wallet_env, monkeypatch, capsys):
    code, out = _run(
        monkeypatch,
        capsys,
        [
            "transactions",
            "batch",
            "--transactions",
            json.dumps(
                [
                    {
                        "from_wallet": MISSING_WALLET,
                        "to_address": "0x" + "11" * 20,
                        "amount": "1",
                    }
                ]
            ),
            "--password-file",
            BAD_PW_FILE,
        ],
    )
    assert code != 0
    assert f"Wallet '{MISSING_WALLET}' not found" in out
    assert "Cannot read password file" not in out
