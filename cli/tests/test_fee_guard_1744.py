"""#1744: the #1714 ``--fee`` sanity guard covers every CLI signing path.

``validate_tx_fee`` (cli/aitbc_cli/utils/fee_guard.py) rejects negative fees
and fees above ``MAX_TX_FEE_AIT`` unless ``--allow-high-fee`` is passed. Each
case invokes a command far enough to reach the guard — every guarded path
aborts before wallet resolution, RPC or signing, so no mocks are needed for
the rejection cases. ``fee_args`` is appended to the base argv.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from aitbc_cli.commands import ipfs as ipfs_cmd
from aitbc_cli.commands import liquidity as liq_cmd
from aitbc_cli.commands import transactions as tx_cmd
from aitbc_cli.commands.exchange import hub_orders
from aitbc_cli.commands.messaging import messaging
from aitbc_cli.commands.wallet import staking as wallet_staking
from aitbc_cli.commands.wallet.basic import send as wallet_send

TO = "0x40c7181b639A2642294A802b1CD60C7a0d531a07"
TX64 = "ab" * 32
GRANTEE = "0x" + "22" * 20


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def wallet_env(tmp_path):
    (tmp_path / "w.json").write_text(
        json.dumps({"address": "0xCf1719140054AB3fD52ce8aa3128dec9317426E3", "private_key": "0x" + "11" * 32})
    )
    return {"AITBC_WALLET_DIR": str(tmp_path)}


def _msg(args):
    def fn(runner, fee_args, **kw):
        return runner.invoke(messaging, args + fee_args, obj={"output_format": "json"}, **kw)

    return fn


def _cmd(command, args):
    def fn(runner, fee_args, **kw):
        return runner.invoke(command, args + fee_args, **kw)

    return fn


# Every ``--fee``-taking command path. ``wallet_send`` and the ``wallet``
# group staking commands need the wallet-group callback, so they take
# ``env=wallet_env`` via the **kw passthrough in the tests below.
GUARDED = [
    pytest.param(_cmd(tx_cmd.send, ["--from", "w", "--to", TO, "--amount", "1"]), id="transactions-send"),
    pytest.param(
        _cmd(ipfs_cmd.subscribe, ["--wallet", "w", "--to", TO, "--island-id", "isl", "--amount", "1"]),
        id="ipfs-island-subscribe",
    ),
    pytest.param(_cmd(liq_cmd.build_deposit, ["--address", TO, "--amount", "1"]), id="liquidity-build-deposit"),
    pytest.param(_cmd(liq_cmd.build_claim, ["--address", TO, "--stake-id", "s1"]), id="liquidity-build-claim"),
    pytest.param(_cmd(liq_cmd.build_withdraw, ["--address", TO, "--stake-id", "s1"]), id="liquidity-build-withdraw"),
    pytest.param(_cmd(hub_orders.order_fund, ["1"]), id="exchange-order-fund"),
    pytest.param(_msg(["send", "--wallet", "w", "--message", "hi"]), id="messaging-send"),
    pytest.param(_msg(["dm", "keygen", "--wallet", "w"]), id="messaging-dm-keygen"),
    pytest.param(_msg(["dm", "send", GRANTEE, "--wallet", "w", "--message", "hi"]), id="messaging-dm-send"),
    pytest.param(_msg(["vote", TX64, "up", "--wallet", "w"]), id="messaging-vote"),
    pytest.param(_msg(["hide", TX64, "--wallet", "w"]), id="messaging-hide"),
    pytest.param(_msg(["pin", TX64, "--wallet", "w"]), id="messaging-pin"),
    pytest.param(_msg(["unhide", TX64, "--wallet", "w"]), id="messaging-unhide"),
    pytest.param(_msg(["unpin", TX64, "--wallet", "w"]), id="messaging-unpin"),
    pytest.param(_msg(["lock", "--topic", "dev", "--wallet", "w"]), id="messaging-lock"),
    pytest.param(_msg(["unlock", "--topic", "dev", "--wallet", "w"]), id="messaging-unlock"),
    pytest.param(_msg(["mod-grant", GRANTEE, "--topic", "dev", "--wallet", "w"]), id="messaging-mod-grant"),
    pytest.param(_msg(["mod-revoke", GRANTEE, "--topic", "dev", "--wallet", "w"]), id="messaging-mod-revoke"),
    # wallet-group staking commands: invoked standalone, the fee guard fires
    # before ctx.obj wallet lookups.
    pytest.param(_cmd(wallet_staking.liquidity_stake, ["--amount", "1"]), id="wallet-liquidity-stake"),
    pytest.param(_cmd(wallet_staking.liquidity_claim, ["--stake-id", "s1"]), id="wallet-liquidity-claim"),
    pytest.param(_cmd(wallet_staking.liquidity_unstake, ["--stake-id", "s1"]), id="wallet-liquidity-unstake"),
]


@pytest.mark.parametrize("invoke", GUARDED)
def test_fee_above_ceiling_rejected(runner, invoke, wallet_env):
    result = invoke(runner, ["--fee", "50"], env=wallet_env)
    assert result.exit_code != 0, result.output
    assert "sanity ceiling" in result.output


@pytest.mark.parametrize("invoke", GUARDED)
def test_negative_fee_rejected(runner, invoke, wallet_env):
    result = invoke(runner, ["--fee=-1"], env=wallet_env)
    assert result.exit_code != 0, result.output
    assert "must be >= 0" in result.output


def test_transactions_send_allow_high_fee_overrides(runner, wallet_env):
    """--allow-high-fee passes the guard; the command then fails later on
    wallet resolution (no wallet dir contents), which is fine — the point is
    the guard no longer fires."""
    result = runner.invoke(
        tx_cmd.send,
        ["--from", "w", "--to", TO, "--amount", "1", "--fee", "50", "--allow-high-fee"],
        env=wallet_env,
    )
    assert "sanity ceiling" not in result.output


def test_wallet_send_still_guarded(runner, tmp_path, wallet_env):
    """The original #1714 path keeps working through the shared helper."""
    tmp_path / "w.json"
    result = runner.invoke(
        wallet_send,
        [
            "--to-address",
            TO,
            "--amount",
            "1",
            "--fee",
            "50",
        ],
        obj={},
        env=wallet_env,
    )
    # wallet_send is a subcommand of the wallet group — ctx.obj lacks
    # wallet_name, but the fee guard fires before that lookup.
    assert result.exit_code != 0
    assert "sanity ceiling" in result.output


def test_liquidity_stake_rejects_nonpositive_amount(runner):
    """#1744: wallet liquidity-stake must refuse amount <= 0 before signing."""
    for bad in ("0", "-1"):
        result = runner.invoke(wallet_staking.liquidity_stake, ["--amount", bad], obj={})
        assert result.exit_code != 0
        assert "must be > 0" in result.output
