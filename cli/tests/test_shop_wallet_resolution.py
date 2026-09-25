"""SHOP_WALLET_ADDRESS resolves a local wallet file so offer listings can sign.

The unsigned-offer exemption (V23-90) is closed: ``aitbc market offer`` must
carry a signature. The unattended miner path sets only ``SHOP_WALLET_ADDRESS``
— an address, not a wallet name — so ``get_market_wallet`` resolves the env
address to a file wallet in the search dirs and loads its key.
"""

import json

import click
import pytest

from aitbc_cli.commands.market import get_market_wallet
from aitbc_cli.utils.error_handling import CLIError
from aitbc_cli.utils.wallet_loader import find_wallet_by_address

ADDR = "0x1234567890aBcdef1234567890aBcDef12345678"
KEY = "0x" + "33" * 32


def _ctx() -> click.Context:
    ctx = click.Context(click.Command("market"))
    ctx.obj = {}
    return ctx


@pytest.fixture
def wallet_dir(tmp_path, monkeypatch):
    d = tmp_path / "wallets"
    d.mkdir()
    monkeypatch.setenv("AITBC_WALLET_DIR", str(d))
    return d


def _write_wallet(directory, name, address, key=KEY):
    path = directory / f"{name}.json"
    path.write_text(json.dumps({"wallet_id": name, "type": "simple", "address": address, "private_key": key}))
    return path


def test_find_wallet_by_address_matches(wallet_dir):
    """Canonical compare: checksummed env value vs lowercase file must hit."""
    _write_wallet(wallet_dir, "miner", ADDR.lower())
    assert find_wallet_by_address(ADDR) == wallet_dir / "miner.json"


def test_find_wallet_by_address_metadata_shape(wallet_dir):
    """Service-wallet shape: the address may live under ``metadata``."""
    path = wallet_dir / "svc.json"
    path.write_text(json.dumps({"wallet_id": "svc", "metadata": {"address": ADDR}}))
    assert find_wallet_by_address(ADDR) == path


def test_find_wallet_by_address_no_match(wallet_dir):
    _write_wallet(wallet_dir, "other", "0x" + "ab" * 20)
    assert find_wallet_by_address(ADDR) is None


def test_get_market_wallet_resolves_shop_key(wallet_dir, monkeypatch):
    monkeypatch.setenv("SHOP_WALLET_ADDRESS", ADDR)
    _write_wallet(wallet_dir, "miner", ADDR)
    address, key, name = get_market_wallet(_ctx())
    assert address.lower() == ADDR.lower()
    assert key == KEY
    assert name == "miner"


def test_get_market_wallet_shop_without_file_is_address_only(wallet_dir, monkeypatch):
    """No matching file: the env shortcut degrades to address-only as before."""
    monkeypatch.setenv("SHOP_WALLET_ADDRESS", ADDR)
    address, key, name = get_market_wallet(_ctx())
    assert address == ADDR
    assert key is None
    assert name == "shop"


def test_get_market_wallet_signing_loads_shop_key(wallet_dir, monkeypatch):
    """require_private_key=True still prefers the shop address file."""
    monkeypatch.setenv("SHOP_WALLET_ADDRESS", ADDR)
    _write_wallet(wallet_dir, "miner", ADDR)
    # A default wallet that also exists must not win over the shop address.
    _write_wallet(wallet_dir, "default", "0x" + "cd" * 20)
    address, key, name = get_market_wallet(_ctx(), require_private_key=True)
    assert address.lower() == ADDR.lower()
    assert key == KEY
    assert name == "miner"


def test_get_market_wallet_signing_fails_when_shop_file_missing(wallet_dir, monkeypatch):
    """A signing caller must not silently sign as a different wallet."""
    monkeypatch.setenv("SHOP_WALLET_ADDRESS", ADDR)
    _write_wallet(wallet_dir, "default", "0x" + "cd" * 20)
    with pytest.raises(CLIError, match="SHOP_WALLET_ADDRESS"):
        get_market_wallet(_ctx(), require_private_key=True)


def test_get_market_wallet_explicit_wallet_beats_env(wallet_dir, monkeypatch):
    """--wallet always wins over the SHOP_WALLET_ADDRESS shortcut."""
    monkeypatch.setenv("SHOP_WALLET_ADDRESS", ADDR)
    other_addr = "0x" + "cd" * 20
    _write_wallet(wallet_dir, "named", other_addr)
    ctx = _ctx()
    ctx.obj["market_wallet"] = "named"
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet_dir))
    address, key, name = get_market_wallet(ctx)
    assert address.lower() == other_addr.lower()
    assert name == "named"
