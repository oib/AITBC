"""Regression coverage for wallet file auto-import exclusions."""

import json
import logging
import os
import tempfile
from pathlib import Path

import httpx
import pytest

_API_KEY_DIR = tempfile.TemporaryDirectory(prefix="wallet-import-api-keys-")
os.environ.setdefault("API_KEY_STORAGE_PATH", str(Path(_API_KEY_DIR.name) / "api_keys.json"))

from wallet_app import main as wallet_main  # noqa: E402


class _Response:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _DaemonClient:
    def __init__(self, calls: dict[str, list]):
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False

    async def get(self, url: str):
        self._calls["get"].append(url)
        return _Response(payload={"items": []})

    async def post(self, url: str, json: dict):
        self._calls["post"].append((url, json))
        return _Response(status_code=201)


@pytest.mark.asyncio
async def test_sell_escrow_slot_skipped_by_file_wallet_import(tmp_path: Path, monkeypatch, caplog):
    escrow_file = tmp_path / "ait-sell-escrow.json"
    escrow_file.write_text(
        json.dumps(
            {
                "address": "0x" + "33" * 20,
                "private_key": {"ciphertext": "credential-slot"},
            }
        )
    )
    shop_file = tmp_path / "shop.json"
    shop_file.write_text(
        json.dumps(
            {
                "wallet_id": "shop",
                "address": "0x" + "44" * 20,
                "private_key": "11" * 32,
                "chain_id": "ait-testnet",
            }
        )
    )

    calls: dict[str, list] = {"get": [], "post": []}
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: _DaemonClient(calls))
    monkeypatch.setenv("WALLET_DIR", str(tmp_path))
    monkeypatch.setenv("WALLET_IMPORT_PASSWORD", "test-import-password")
    monkeypatch.setenv("SELL_ESCROW_WALLET_PATH", str(escrow_file))

    with caplog.at_level(logging.WARNING):
        await wallet_main._import_file_wallets()

    assert calls["get"] == ["http://localhost:8108/v1/wallets"]
    assert len(calls["post"]) == 1
    url, payload = calls["post"][0]
    assert url == "http://localhost:8108/v1/wallets"
    assert payload["wallet_id"] == "shop"
    assert "ait-sell-escrow.json" not in caplog.text
    assert "failed to decrypt private_key dict" not in caplog.text
