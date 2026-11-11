"""#1760: subprocess_env() must strip service secrets from child environments."""

import os

from aitbc.utils.env import subprocess_env


def test_strips_non_allowlisted_vars(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("PROPOSER_KEY", "secret-key-material")
    monkeypatch.setenv("VALIDATOR_KEYS", "{}")
    monkeypatch.setenv("JWT_SECRET", "jwt")
    monkeypatch.setenv("COORDINATOR_API_KEY", "ck")
    env = subprocess_env()
    assert env["PATH"] == "/usr/bin:/bin"
    for leaked in ("PROPOSER_KEY", "VALIDATOR_KEYS", "JWT_SECRET", "COORDINATOR_API_KEY"):
        assert leaked not in env


def test_include_adds_named_vars(monkeypatch):
    monkeypatch.setenv("IPFS_PATH", "/data/ipfs")
    monkeypatch.setenv("UNRELATED_SECRET", "x")
    env = subprocess_env(include=("IPFS_PATH",))
    assert env["IPFS_PATH"] == "/data/ipfs"
    assert "UNRELATED_SECRET" not in env


def test_include_prefixes(monkeypatch):
    monkeypatch.setenv("AITBC_WALLET_DIR", "/w")
    monkeypatch.setenv("SHOP_WALLET_ADDRESS", "0xabc")
    monkeypatch.setenv("MINER_GPU", "0")
    monkeypatch.setenv("PROPOSER_KEY", "secret")
    env = subprocess_env(include_prefixes=("AITBC_", "SHOP_", "MINER_"))
    assert env["AITBC_WALLET_DIR"] == "/w"
    assert env["SHOP_WALLET_ADDRESS"] == "0xabc"
    assert env["MINER_GPU"] == "0"
    assert "PROPOSER_KEY" not in env


def test_result_is_a_copy(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    env = subprocess_env()
    env["PATH"] = "/tampered"
    assert os.environ["PATH"] != "/tampered"
