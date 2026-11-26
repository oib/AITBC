"""Regression pins for the 22 Nov audit-leftover cluster (#2578, #2552, #2553, #2556, #2566).

- #2578: the synthetic ``local-rpc`` multichain node must follow
  ``blockchain_rpc_url`` on every load and must never be persisted.
- #2552: dashboard sections that fail must be named, and an all-failed
  dashboard must exit non-zero instead of printing "loaded".
- #2553: the shop dashboard asks the market for ``provider=<shop>`` so the
  shop's own offers cannot be pushed out by the server-side page.
- #2556: ``account list`` exposes limit/offset/cursor/--all and a
  truncation notice.
- #2566: ``developer register`` requires a wallet signature over the
  registration claim.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
import yaml
from click.testing import CliRunner
from eth_account import Account

import aitbc_cli.commands.account as account_mod
import aitbc_cli.commands.dashboard as dashboard_mod
import aitbc_cli.commands.developer as developer_mod
from aitbc.crypto.developer_registry import (
    developer_register_claim,
    verify_developer_register,
)
from aitbc_cli.commands.account import account
from aitbc_cli.commands.dashboard import dashboard  # noqa: F401 — register commands
from aitbc_cli.commands.developer import developer
from aitbc_cli.core.config import NodeConfig, load_multichain_config, save_multichain_config


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# #2578 — local-rpc synthetic node
# ---------------------------------------------------------------------------


def _patch_rpc_url(monkeypatch, url: str) -> None:
    monkeypatch.setattr(
        "aitbc_cli.config.get_config",
        lambda: SimpleNamespace(blockchain_rpc_url=url),
    )


def test_local_rpc_refreshes_stale_persisted_endpoint(monkeypatch, tmp_path):
    """A local-rpc row saved by an older config must follow blockchain_rpc_url."""
    cfg_path = tmp_path / "multichain_config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "nodes": {
                    "local-rpc": {"id": "local-rpc", "endpoint": "http://127.0.0.1:9999"},
                    "peer": {"id": "peer", "endpoint": "http://peer:8202"},
                }
            }
        )
    )
    _patch_rpc_url(monkeypatch, "http://127.0.0.1:8202")
    config = load_multichain_config(str(cfg_path))
    assert config.nodes["local-rpc"].endpoint == "http://127.0.0.1:8202"
    assert config.nodes["peer"].endpoint == "http://peer:8202"


def test_first_load_offers_local_rpc_but_does_not_persist_it(monkeypatch, tmp_path):
    """The missing-file path must offer local-rpc in memory yet write a clean file."""
    cfg_path = tmp_path / "multichain_config.yaml"
    _patch_rpc_url(monkeypatch, "http://10.0.0.9:8202")
    config = load_multichain_config(str(cfg_path))
    assert config.nodes["local-rpc"].endpoint == "http://10.0.0.9:8202"
    on_disk = yaml.safe_load(cfg_path.read_text())
    assert "local-rpc" not in (on_disk.get("nodes") or {})


def test_save_strips_synthetic_local_rpc(monkeypatch, tmp_path):
    """node add/remove must not freeze the synthetic entry into the YAML."""
    cfg_path = tmp_path / "multichain_config.yaml"
    _patch_rpc_url(monkeypatch, "http://127.0.0.1:8202")
    config = load_multichain_config(str(cfg_path))
    config.nodes["real-node"] = NodeConfig(id="real-node", endpoint="http://n:8202")
    save_multichain_config(config, str(cfg_path))
    on_disk = yaml.safe_load(cfg_path.read_text())
    assert "local-rpc" not in on_disk["nodes"]
    assert "real-node" in on_disk["nodes"]


# ---------------------------------------------------------------------------
# #2556 — account list paging
# ---------------------------------------------------------------------------


class _AccountsClient:
    """Fake /rpc/accounts peer: pages keyed off the cursor it is handed."""

    pages: dict[str | None, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []

    def __init__(self, *a, **kw):
        pass

    def get(self, path, params=None):
        type(self).calls.append({"path": path, "params": dict(params or {})})
        return type(self).pages[params.get("cursor") if params else None]

    def close(self):
        pass


def _accounts_page(accounts, next_cursor=None, total_accounts=None):
    return {
        "chain_id": "ait-devnet",
        "accounts": accounts,
        "total": len(accounts),
        "total_accounts": len(accounts) if total_accounts is None else total_accounts,
        "limit": 100,
        "offset": 0,
        "next_cursor": next_cursor,
    }


def test_account_list_passes_paging_params(runner, monkeypatch):
    _AccountsClient.pages = {"0xabc": _accounts_page([{"address": "0x1", "balance": 0, "nonce": 0}])}
    _AccountsClient.calls = []
    monkeypatch.setattr(account_mod, "AITBCHTTPClient", _AccountsClient)
    result = runner.invoke(
        account,
        ["list", "--rpc-url", "http://rpc.test", "--limit", "50", "--offset", "10", "--cursor", "0xabc"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    sent = _AccountsClient.calls[0]["params"]
    assert sent["limit"] == 50 and sent["offset"] == 10 and sent["cursor"] == "0xabc"


def test_account_list_all_pages_via_next_cursor(runner, monkeypatch):
    _AccountsClient.pages = {
        None: _accounts_page([{"address": "0x1", "balance": 0, "nonce": 0}], next_cursor="0x2", total_accounts=2),
        "0x2": _accounts_page([{"address": "0x2", "balance": 0, "nonce": 0}], total_accounts=2),
    }
    _AccountsClient.calls = []
    monkeypatch.setattr(account_mod, "AITBCHTTPClient", _AccountsClient)
    result = runner.invoke(account, ["list", "--rpc-url", "http://rpc.test", "--all"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [a["address"] for a in payload["accounts"]] == ["0x1", "0x2"]
    assert payload["pages"] == 2 and payload["next_cursor"] is None
    assert _AccountsClient.calls[1]["params"]["cursor"] == "0x2"


def test_account_list_truncation_notice(runner, monkeypatch):
    _AccountsClient.pages = {
        None: _accounts_page([{"address": "0x1", "balance": 0, "nonce": 0}], next_cursor="0x2", total_accounts=3)
    }
    _AccountsClient.calls = []
    monkeypatch.setattr(account_mod, "AITBCHTTPClient", _AccountsClient)
    result = runner.invoke(account, ["list", "--rpc-url", "http://rpc.test"], obj={"output_format": "table"})
    assert result.exit_code == 0, result.output
    assert "showing 1 of 3 accounts" in result.stderr


# ---------------------------------------------------------------------------
# #2552 — dashboard degrade-loaded
# ---------------------------------------------------------------------------


def _reset_failures():
    dashboard_mod._SECTION_FAILURES.clear()


def test_safe_get_records_section_failure(monkeypatch):
    class _Down:
        def get_json(self, *a, **kw):
            raise dashboard_mod.NetworkError("down")

    _reset_failures()
    assert dashboard_mod._safe_get(cast(Any, _Down()), "/v1/jobs", section="jobs") is None
    assert "jobs" in dashboard_mod._SECTION_FAILURES


def test_finish_dashboard_names_unavailable_sections():
    _reset_failures()
    dashboard_mod._SECTION_FAILURES.add("jobs")
    data: dict[str, Any] = {"summary": {}}
    ctx = cast(Any, SimpleNamespace(obj={"output_format": "json"}))
    dashboard_mod._finish_dashboard(ctx, data, "json", "T", "loaded", {"jobs", "wallets"})
    assert data["summary"]["unavailable_sections"] == ["jobs"]


def test_finish_dashboard_exits_nonzero_when_all_sections_fail():
    _reset_failures()
    dashboard_mod._SECTION_FAILURES.update({"jobs", "wallets"})
    ctx = cast(Any, SimpleNamespace(obj={"output_format": "json"}))
    with pytest.raises(SystemExit) as exc:
        dashboard_mod._finish_dashboard(ctx, {"summary": {}}, "json", "T", "loaded", {"jobs", "wallets"})
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# #2553 — shop market offers provider filter
# ---------------------------------------------------------------------------


class _OfferClient:
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, payload, *a, **kw):
        self._payload = payload

    def get_json(self, path, params=None):
        type(self).calls.append({"path": path, "params": dict(params or {})})
        return self._payload

    def close(self):
        pass


def test_shop_market_offers_sends_provider_filter(monkeypatch):
    _OfferClient.calls = []
    offers = {
        "offers": [
            {"plugin_id": "mine", "node_id": "shop-1", "provider_address": "0xmine"},
            {"plugin_id": "theirs", "node_id": "shop-2", "provider_address": "0xother"},
        ]
    }
    monkeypatch.setattr(dashboard_mod, "AITBCHTTPClient", lambda *a, **kw: _OfferClient(offers))
    monkeypatch.setattr(dashboard_mod, "_auth_headers", lambda ctx, role="client": None)
    config = SimpleNamespace(hub_discovery_url="http://market.test", node_id="fallback-node")
    ctx = cast(Any, SimpleNamespace(obj={}))
    rows = dashboard_mod._shop_market_offers(ctx, config, "shop-1", 10)
    call = _OfferClient.calls[-1]
    assert call["params"].get("provider") == "shop-1"
    # client-side filter kept for pre-provider market builds
    assert [r["Plugin ID"] for r in rows] == ["mine"]


# ---------------------------------------------------------------------------
# #2566 — developer register wallet signature (CLI side)
# ---------------------------------------------------------------------------

_KEY = Account.from_key("0x" + "11" * 32)
WALLET = _KEY.address
_OTHER_KEY = Account.from_key("0x" + "22" * 32)


class _PostClient:
    posts: list[dict[str, Any]] = []

    def __init__(self, *a, **kw):
        pass

    def post(self, path, json=None, **kw):
        type(self).posts.append({"path": path, "json": json})
        return {"id": "dev-1"}

    def close(self):
        pass


def _invoke_register(runner, monkeypatch, signing):
    monkeypatch.setattr(developer_mod, "load_signing_wallet", lambda *a, **kw: signing)
    monkeypatch.setattr(developer_mod, "_get_client", lambda ctx: _PostClient())
    _PostClient.posts = []
    return runner.invoke(
        developer,
        ["register", "--wallet-address", WALLET, "--name", "dev-one"],
        obj={"output_format": "json"},
    )


def test_register_requires_wallet_signature(runner, monkeypatch):
    result = _invoke_register(runner, monkeypatch, None)
    assert result.exit_code != 0
    assert "wallet signature" in result.output
    assert _PostClient.posts == []


def test_register_rejects_mismatched_signing_wallet(runner, monkeypatch):
    result = _invoke_register(runner, monkeypatch, (_OTHER_KEY.address, "0x" + "22" * 32))
    assert result.exit_code != 0
    assert "does not match" in result.output
    assert _PostClient.posts == []


def test_register_signs_claim_and_posts(runner, monkeypatch):
    result = _invoke_register(runner, monkeypatch, (WALLET, "0x" + "11" * 32))
    assert result.exit_code == 0, result.output
    # #3023: self-service register posts to the public /register path —
    # POST /v1/developers stays admin/client-gated.
    assert _PostClient.posts[0]["path"] == "/v1/developers/register"
    posted = _PostClient.posts[0]["json"]
    assert posted["wallet_address"] == WALLET
    assert posted["signature"].startswith("0x") and len(posted["signature"]) == 132
    claim = developer_register_claim(
        wallet_address=posted["wallet_address"],
        name=posted.get("name"),
        email=posted.get("email"),
        github_handle=posted.get("github_handle"),
        timestamp=posted["timestamp"],
    )
    assert verify_developer_register(claim, posted["signature"], WALLET)
    # timestamp is fresh — the server-side staleness window accepts it
    assert abs(time.time() - posted["timestamp"]) < 600
    # and the signature is not a reusable blank check: wrong wallet fails
    assert not verify_developer_register(claim, posted["signature"], _OTHER_KEY.address)
