"""Fixture tests for scripts/ops/bridge_mainnet_preflight.py (BR-5)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import bridge_mainnet_preflight as preflight  # noqa: E402

MAINNET_ENV = {
    "ETH_NETWORK": "mainnet",
    "BRIDGE_CONFIRMATIONS": "12",
    "CHAINLINK_MAX_AGE_SECONDS": "5400",
    "BRIDGE_MAX_PAYOUT_AIT": "100",
}

# Today's testnet posture: sepolia feed, testnet confirmation depth, the
# fixed-price pin set, generous staleness, no absolute payout cap.
TESTNET_ENV = {
    "ETH_NETWORK": "sepolia",
    "BRIDGE_CONFIRMATIONS": "3",
    "AIT_USD_FIXED_PRICE": "0.28",
    "CHAINLINK_MAX_AGE_SECONDS": "259200",
}


def results(env):
    return {c.name: c for c in preflight.check_config(env)}


def _write_env(tmp_path: Path, env: dict) -> Path:
    path = tmp_path / "check.env"
    path.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    return path


def test_mainnet_config_all_pass():
    assert all(c.passed for c in preflight.check_config(MAINNET_ENV))


def test_testnet_config_fails():
    """The current testnet config must not pass preflight — the verify step.

    Six of seven knobs fail (network, feed, confirmations, USD pin,
    staleness, payout ceiling); only the correctly-unset EUR pin passes —
    unset pins are desired on mainnet too.
    """
    res = results(TESTNET_ENV)
    failed = [n for n, c in res.items() if not c.passed]
    assert failed == [
        "ETH_NETWORK",
        "chainlink feed",
        "BRIDGE_CONFIRMATIONS",
        "AIT_USD_FIXED_PRICE",
        "CHAINLINK_MAX_AGE_SECONDS",
        "BRIDGE_MAX_PAYOUT_AIT",
    ]


def test_main_rc_all_pass(tmp_path, capsys):
    rc = preflight.main(["--env-file", str(_write_env(tmp_path, MAINNET_ENV))])
    assert rc == 0
    assert "7/7" in capsys.readouterr().out


def test_main_rc_testnet_fails(tmp_path):
    assert preflight.main(["--env-file", str(_write_env(tmp_path, TESTNET_ENV))]) == 1


@pytest.mark.parametrize(
    "key,value,check",
    [
        ("ETH_NETWORK", "sepolia", "ETH_NETWORK"),
        ("BRIDGE_CONFIRMATIONS", "3", "BRIDGE_CONFIRMATIONS"),
        ("BRIDGE_CONFIRMATIONS", "11", "BRIDGE_CONFIRMATIONS"),
        ("CHAINLINK_MAX_AGE_SECONDS", "5401", "CHAINLINK_MAX_AGE_SECONDS"),
        ("BRIDGE_MAX_PAYOUT_AIT", "", "BRIDGE_MAX_PAYOUT_AIT"),
    ],
)
def test_each_knob_fails_alone(key, value, check):
    env = dict(MAINNET_ENV)
    env[key] = value
    res = results(env)
    assert not res[check].passed
    # ETH_NETWORK also drives the derived feed check — accept both failing.
    expected_extra = {"chainlink feed"} if key == "ETH_NETWORK" else set()
    assert all(c.passed for n, c in res.items() if n != check and n not in expected_extra)


def test_unset_confirmations_uses_default_3():
    env = dict(MAINNET_ENV)
    del env["BRIDGE_CONFIRMATIONS"]
    assert not results(env)["BRIDGE_CONFIRMATIONS"].passed


def test_usd_pin_fails():
    env = dict(MAINNET_ENV, AIT_USD_FIXED_PRICE="0.28")
    assert not results(env)["AIT_USD_FIXED_PRICE"].passed


def test_eur_pin_fails():
    env = dict(MAINNET_ENV, AIT_EUR_FIXED_PRICE="0.25")
    assert not results(env)["AIT_EUR_FIXED_PRICE"].passed


def test_feed_constants_match_oracle():
    """The literals must stay in sync with aitbc/oracles/price_oracle.py."""
    import re

    src = (Path(__file__).resolve().parents[2] / "aitbc" / "oracles" / "price_oracle.py").read_text()
    mainnet = re.search(r'CHAINLINK_FEEDS_MAINNET.*?"ETH/USD":\s*"(0x[0-9a-fA-F]+)"', src, re.S)
    sepolia = re.search(r'CHAINLINK_FEEDS_SEPOLIA.*?"ETH/USD":\s*"(0x[0-9a-fA-F]+)"', src, re.S)
    assert mainnet and sepolia
    assert preflight.MAINNET_ETH_USD_FEED == mainnet.group(1)
    assert preflight.SEPOLIA_ETH_USD_FEED == sepolia.group(1)


# --- stacked --env-file (BR-8): systemd EnvironmentFile order ---


def _env_path(tmp_path: Path, name: str, env: dict) -> Path:
    path = tmp_path / name
    path.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    return path


def test_stacked_env_files_later_overrides(tmp_path):
    """Two files like blockchain.env + aitbc-bridge-monitor.env: later wins."""
    first = _env_path(tmp_path, "blockchain.env", {"AIT_EUR_FIXED_PRICE": "0.25", "ETH_NETWORK": "mainnet"})
    second = _env_path(tmp_path, "aitbc-bridge-monitor.env", {"ETH_NETWORK": "sepolia"})
    env = preflight.load_env_files([str(first), str(second)])
    assert env["ETH_NETWORK"] == "sepolia"


def test_stacked_env_files_first_only_key_survives(tmp_path):
    """A key set only in the earlier file keeps its value — the EUR-pin miss."""
    first = _env_path(tmp_path, "blockchain.env", {"AIT_EUR_FIXED_PRICE": "0.25"})
    second = _env_path(tmp_path, "aitbc-bridge-monitor.env", dict(TESTNET_ENV))
    env = preflight.load_env_files([str(first), str(second)])
    assert env["AIT_EUR_FIXED_PRICE"] == "0.25"
    res = results(env)
    assert not res["AIT_EUR_FIXED_PRICE"].passed


def test_optional_env_file_missing_is_skipped(tmp_path):
    """A '-' prefixed path that does not exist is skipped, like EnvironmentFile=-."""
    base = _env_path(tmp_path, "blockchain.env", dict(TESTNET_ENV))
    env = preflight.load_env_files([str(base), "-" + str(tmp_path / "secrets.env")])
    assert env["ETH_NETWORK"] == "sepolia"


def test_mandatory_env_file_missing_errors(tmp_path, capsys):
    """A missing non-optional file exits non-zero instead of silently passing."""
    with pytest.raises(SystemExit):
        preflight.main(["--env-file", str(tmp_path / "gone.env")])
    assert "gone.env" in capsys.readouterr().err


def test_main_stacked_env_files(tmp_path):
    """End to end: --env-file twice reproduces the unit's effective env."""
    first = _env_path(tmp_path, "blockchain.env", {"AIT_EUR_FIXED_PRICE": "0.25"})
    second = _env_path(tmp_path, "aitbc-bridge-monitor.env", dict(TESTNET_ENV))
    rc = preflight.main(["--env-file", str(first), "--env-file", str(second)])
    assert rc == 1
