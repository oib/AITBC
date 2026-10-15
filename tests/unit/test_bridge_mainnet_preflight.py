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


# --- ETH-5: --profile sepolia ---

# A fully acceptable testnet configuration: sepolia feed map, the code's own
# 3-confirmation default depth, the fixed-price pin testnet runs on, the
# oracle's generous staleness bound, and an absolute payout ceiling.
SEPOLIA_ENV = {
    "ETH_NETWORK": "sepolia",
    "BRIDGE_CONFIRMATIONS": "3",
    "AIT_USD_FIXED_PRICE": "0.28",
    "AIT_EUR_FIXED_PRICE": "0.25",
    "CHAINLINK_MAX_AGE_SECONDS": "259200",
    "BRIDGE_MAX_PAYOUT_AIT": "100",
}


def sepolia_results(env):
    return {c.name: c for c in preflight.check_config(env, "sepolia")}


def test_sepolia_profile_full_pass():
    res = sepolia_results(SEPOLIA_ENV)
    assert all(c.passed for c in res.values())


def test_sepolia_rc_all_pass(tmp_path, capsys):
    rc = preflight.main(["--profile", "sepolia", "--env-file", str(_write_env(tmp_path, SEPOLIA_ENV))])
    assert rc == 0
    out = capsys.readouterr().out
    assert "7/7" in out and "sepolia" in out.lower()


def test_sepolia_header_names_profile(tmp_path, capsys):
    """A sepolia PASS can never be mistaken for mainnet readiness."""
    preflight.main(["--profile", "sepolia", "--env-file", str(_write_env(tmp_path, SEPOLIA_ENV))])
    out = capsys.readouterr().out
    assert "SEPOLIA" in out
    assert "NOT mainnet readiness" in out


@pytest.mark.parametrize("pin", ["AIT_USD_FIXED_PRICE", "AIT_EUR_FIXED_PRICE"])
def test_sepolia_pin_set_passes_with_info(pin):
    env = dict(SEPOLIA_ENV)
    res = sepolia_results(env)
    assert res[pin].passed
    assert "INFO" in res[pin].detail and env[pin] in res[pin].detail


@pytest.mark.parametrize("pin", ["AIT_USD_FIXED_PRICE", "AIT_EUR_FIXED_PRICE"])
def test_sepolia_pin_unset_also_passes(pin):
    env = dict(SEPOLIA_ENV)
    del env[pin]
    res = sepolia_results(env)
    assert res[pin].passed
    assert "unset" in res[pin].detail


@pytest.mark.parametrize(
    "key,value,check",
    [
        ("ETH_NETWORK", "mainnet", "ETH_NETWORK"),
        ("ETH_NETWORK", "", "ETH_NETWORK"),  # unset maps to the mainnet feed map
        ("BRIDGE_CONFIRMATIONS", "2", "BRIDGE_CONFIRMATIONS"),
        ("CHAINLINK_MAX_AGE_SECONDS", "", "CHAINLINK_MAX_AGE_SECONDS"),  # must be set
        ("CHAINLINK_MAX_AGE_SECONDS", "259201", "CHAINLINK_MAX_AGE_SECONDS"),  # looser than the code default
        ("CHAINLINK_MAX_AGE_SECONDS", "0", "CHAINLINK_MAX_AGE_SECONDS"),
        ("BRIDGE_MAX_PAYOUT_AIT", "", "BRIDGE_MAX_PAYOUT_AIT"),
    ],
)
def test_sepolia_each_knob_fails_alone(key, value, check):
    env = dict(SEPOLIA_ENV)
    if value == "":
        del env[key]
    else:
        env[key] = value
    res = sepolia_results(env)
    assert not res[check].passed
    # ETH_NETWORK also drives the derived feed check — accept both failing.
    expected_extra = {"chainlink feed"} if key == "ETH_NETWORK" else set()
    assert all(c.passed for n, c in res.items() if n != check and n not in expected_extra)


def test_sepolia_unset_confirmations_passes_at_code_default():
    """Unset BRIDGE_CONFIRMATIONS resolves to the code default 3 — still >= 3."""
    env = dict(SEPOLIA_ENV)
    del env["BRIDGE_CONFIRMATIONS"]
    res = sepolia_results(env)
    # unset env var -> int("") fails -> default 3 — passes at the code floor.
    assert res["BRIDGE_CONFIRMATIONS"].passed


def test_mainnet_profile_still_fails_sepolia_config(tmp_path):
    """The same sepolia env must still FAIL under the default/mainnet profile."""
    path = _write_env(tmp_path, SEPOLIA_ENV)
    assert preflight.main(["--env-file", str(path)]) == 1
    assert preflight.main(["--profile", "mainnet", "--env-file", str(path)]) == 1


def test_default_profile_equals_explicit_mainnet(tmp_path, capsys):
    path = _write_env(tmp_path, SEPOLIA_ENV)
    rc_default = preflight.main(["--env-file", str(path)])
    out_default = capsys.readouterr().out
    rc_explicit = preflight.main(["--profile", "mainnet", "--env-file", str(path)])
    out_explicit = capsys.readouterr().out
    assert rc_default == rc_explicit == 1
    assert out_default == out_explicit


# --- ETH-5 Part B: mainnet-style staging env stacked in the real unit order ---

# The four set knobs on a mainnet-style config; the two pins stay absent.
STAGING_MAINNET = {
    "ETH_NETWORK": "mainnet",
    "BRIDGE_CONFIRMATIONS": "12",
    "CHAINLINK_MAX_AGE_SECONDS": "3600",
    "BRIDGE_MAX_PAYOUT_AIT": "100",
}


def _staging_env_paths(tmp_path: Path, knobs: dict) -> list[str]:
    """Stand-in files in the live unit's EnvironmentFile order — synthetic
    content only, no real addresses or secrets."""
    _env_path(tmp_path, "blockchain.env", {"AITBC_DATA_DIR": "/var/lib/aitbc"})
    _env_path(tmp_path, "node.env", {"NODE_ID": "staging"})
    _env_path(tmp_path, "aitbc-bridge-monitor.env", knobs)
    return [
        str(tmp_path / "blockchain.env"),
        "-" + str(tmp_path / "blockchain-secrets.env"),  # optional, absent
        str(tmp_path / "node.env"),
        str(tmp_path / "aitbc-bridge-monitor.env"),
    ]


def test_staging_mainnet_stack_passes_7_of_7(tmp_path, capsys):
    """Part B proof: the mainnet profile is green on a mainnet-style env
    layered exactly like the real EnvironmentFile list."""
    files = _staging_env_paths(tmp_path, dict(STAGING_MAINNET))
    rc = preflight.main(["--env-file", *files])
    out = capsys.readouterr().out
    assert rc == 0
    assert "7/7" in out
    assert "MAINNET" in out


@pytest.mark.parametrize("knob", list(STAGING_MAINNET))
def test_staging_mainnet_stack_knob_removed_fails(tmp_path, capsys, knob):
    """Removing any one staging knob fails exactly that knob."""
    env = dict(STAGING_MAINNET)
    del env[knob]
    files = _staging_env_paths(tmp_path, env)
    rc = preflight.main(["--env-file", *files])
    out = capsys.readouterr().out
    assert rc == 1
    assert f"FAIL  {knob}" in out
    # the removal must fail exactly that one knob (feed rides on ETH_NETWORK)
    extra = {"chainlink feed"} if knob == "ETH_NETWORK" else set()
    fails = [line for line in out.splitlines() if line.lstrip().startswith("FAIL")]
    assert all(knob in line or any(x in line for x in extra) for line in fails)
