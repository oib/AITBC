"""SHOP-OFFER-REGISTER-AUTH-1 (#3083): the miner's `aitbc market offer`
subprocess must receive the market-service credential, and a refused
/v1/market/offer registration must be logged distinctly — not reported as
a clean "Published default offer".

Two halves:

1. ``subprocess_env(include_prefixes=("AITBC_", "SHOP_", "MINER_"))`` strips
   ``MARKET_API_KEY``/``MARKET_OPERATOR_API_KEY`` before the CLI child sees
   them, so ``_resolve_market_api_key`` finds nothing and the market service
   401s the registration POST. The env builder now passes both names via
   ``include``.

2. ``_register_software_offer`` failures still exit the CLI with rc=0 (the
   on-chain listing already landed — #2954 best-effort), so the miner used
   to log "Published" while the registry row was missing. The CLI emits a
   stable ``market-registration: FAILED`` marker; the miner greps both
   streams (stdout in table mode, stderr in --output json mode) and logs a
   distinct warning while still consuming the cycle's nonce slot.
"""

from unittest.mock import Mock, patch

import pytest

import production_miner


@pytest.fixture(autouse=True)
def _backends_up(monkeypatch):
    monkeypatch.setattr(production_miner, "_offer_backend_up", lambda service_type: True)


_ONE_OFFER = [
    {
        "service_type": "whisper",
        "model": "base",
        "price": "0.001",
        "unit": "per_minute",
        "description": "offer-a",
    },
]


def _publish_env(mock_run):
    return mock_run.call_args.kwargs["env"]


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_offer_subprocess_env_passes_market_api_keys(mock_run, monkeypatch):
    """MARKET_API_KEY / MARKET_OPERATOR_API_KEY reach the CLI child even
    though neither matches the AITBC_/SHOP_/MINER_ prefixes (#3083)."""
    monkeypatch.setattr(production_miner, "DEFAULT_SOFTWARE_OFFERS", _ONE_OFFER)
    monkeypatch.setenv("MARKET_API_KEY", "user-tier-key")
    monkeypatch.setenv("MARKET_OPERATOR_API_KEY", "operator-tier-key")
    monkeypatch.setenv("MINER_WALLET_ADDRESS", "0xminer")
    mock_run.return_value = Mock(returncode=0, stdout="offer published tx=0xabc", stderr="")

    production_miner.publish_default_offers([])

    env = _publish_env(mock_run)
    assert env["MARKET_API_KEY"] == "user-tier-key"
    assert env["MARKET_OPERATOR_API_KEY"] == "operator-tier-key"
    assert env["MINER_WALLET_ADDRESS"] == "0xminer" or env.get("SHOP_WALLET_ADDRESS") == "0xminer"


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_offer_subprocess_env_still_strips_unrelated_secrets(mock_run, monkeypatch):
    """The include list is exact-name only — the #1760 secrets.env filter
    must not widen: a non-prefixed service secret stays out of the child."""
    monkeypatch.setattr(production_miner, "DEFAULT_SOFTWARE_OFFERS", _ONE_OFFER)
    monkeypatch.setenv("MARKET_API_KEY", "user-tier-key")
    monkeypatch.setenv("EXCHANGE_API_KEY", "not-for-the-offer-child")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    mock_run.return_value = Mock(returncode=0, stdout="offer published tx=0xabc", stderr="")

    production_miner.publish_default_offers([])

    env = _publish_env(mock_run)
    assert "EXCHANGE_API_KEY" not in env
    assert "DATABASE_URL" not in env


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_registration_failure_marker_logged_distinctly(mock_run, monkeypatch, caplog):
    """rc=0 + 'market-registration: FAILED' marker → WARNING, not 'Published'.

    The chain listing landed (nonce consumed — the sibling still defers),
    but the registry row was refused; the log must say so."""
    monkeypatch.setattr(production_miner, "DEFAULT_SOFTWARE_OFFERS", list(_ONE_OFFER) * 2)
    mock_run.return_value = Mock(
        returncode=0,
        stdout="Software offer listed on market!\nmarket-registration: FAILED — whisper/base is listed on-chain only",
        stderr="",
    )

    with caplog.at_level("INFO", logger="production_miner"):
        production_miner.publish_default_offers([])

    assert "market-service registration FAILED" in caplog.text
    assert "Published default offer:" not in caplog.text
    # The tx landed, so the cycle's nonce slot is consumed — the sibling defers.
    assert mock_run.call_count == 1
    assert "Deferring default offer" in caplog.text


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_registration_failure_marker_on_stderr_also_caught(mock_run, monkeypatch, caplog):
    """--output json mode routes status labels to stderr — the marker must be
    found there too."""
    monkeypatch.setattr(production_miner, "DEFAULT_SOFTWARE_OFFERS", _ONE_OFFER)
    mock_run.return_value = Mock(
        returncode=0,
        stdout='{"tx_hash": "0xabc"}',
        stderr="market-registration: FAILED — whisper/base refused (401)",
    )

    with caplog.at_level("INFO", logger="production_miner"):
        production_miner.publish_default_offers([])

    assert "market-service registration FAILED" in caplog.text


@pytest.mark.unit
@patch("production_miner.subprocess.run")
def test_clean_publish_still_logs_published(mock_run, monkeypatch, caplog):
    """No marker → unchanged 'Published default offer' info line."""
    monkeypatch.setattr(production_miner, "DEFAULT_SOFTWARE_OFFERS", _ONE_OFFER)
    mock_run.return_value = Mock(returncode=0, stdout="offer published tx=0xabc", stderr="")

    with caplog.at_level("INFO", logger="production_miner"):
        production_miner.publish_default_offers([])

    assert "Published default offer: whisper/base" in caplog.text
    assert "registration FAILED" not in caplog.text
