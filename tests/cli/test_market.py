"""Safe local integration tests for market and escrow commands."""

import json
import os
from types import SimpleNamespace

import pytest
import requests
from click.testing import CliRunner

from aitbc.exceptions import NetworkError

os.environ["AITBC_SKIP_ENV_FILES"] = "1"

from aitbc_cli.core.main import cli


@pytest.fixture
def mock_market_config(monkeypatch):
    """Patch get_config for local endpoints and a known hub proposer."""
    config = SimpleNamespace(
        market_service_url="http://127.0.0.1:8102",
        coordinator_api_url="http://127.0.0.1:8203",
        blockchain_rpc_url="http://127.0.0.1:8202",
        exchange_service_url="http://127.0.0.1:8106",
        hub_discovery_url="",
        hub_proposer_id="0x1111111111111111111111111111111111111111",
        blockchain_rpc_api_key=None,
    )
    monkeypatch.setattr("aitbc_cli.commands.market.escrow.get_config", lambda: config)
    return config


@pytest.fixture
def mock_http_client(monkeypatch):
    """Replace AITBCHTTPClient with a fake that records calls."""
    calls = {"get": [], "post": []}

    class FakeClient:
        def __init__(self, base_url=None, timeout=10, headers=None, **kwargs):
            self.base_url = base_url or "http://127.0.0.1:8202"

        def get(self, path, **kwargs):
            calls["get"].append((self.base_url, path, kwargs))
            if path == "/health" or path.endswith("/health"):
                return {
                    "supported_chains": ["ait-testchain.local"],
                    "proposer_id": "0x1111111111111111111111111111111111111111",
                }
            if "/rpc/account/" in path:
                return {"balance": 1000000000, "nonce": 0}
            return {"supported_chains": ["ait-testchain.local"]}

        def post(self, path, **kwargs):
            calls["post"].append((self.base_url, path, kwargs))
            if path == "/rpc/escrow/create":
                return {"contract_id": "escrow-abc"}
            if path == "/v1/transactions":
                return {"transaction_id": "tx-123"}
            if path == "/rpc/transaction":
                return {"transaction_hash": "0xabc123"}
            return {}

    # ``market escrow``, the escrow helpers and the chain-id probe each import
    # the client into their own namespaces, so patch every copy.
    monkeypatch.setattr("aitbc_cli.commands.market.escrow.AITBCHTTPClient", FakeClient)
    monkeypatch.setattr("aitbc_cli.utils.escrow.AITBCHTTPClient", FakeClient)
    monkeypatch.setattr("aitbc_cli.utils.http_client.AITBCHTTPClient", FakeClient)
    monkeypatch.setattr("aitbc_cli.utils.chain_id.AITBCHTTPClient", FakeClient)
    # ``_escrow_create`` re-imports this at call time, so patching the source
    # module covers it — the signing and nonce round-trips are skipped.
    monkeypatch.setattr(
        "aitbc_cli.utils.escrow.create_signed_escrow_lock",
        lambda *args, **kwargs: ({"type": "ESCROW_LOCK"}, "0x" + "ab" * 64),
    )
    return calls


def test_market_escrow_create_posts_to_local_blockchain(mock_market_config, mock_http_client):
    """``market escrow create`` posts the signed lock to the local blockchain RPC."""
    calls = mock_http_client
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "market",
            "escrow",
            "create",
            "--job-id",
            "job-1",
            "--buyer",
            "0x11a01cb7F3C01AE8E8a992FE72fbDF3B530ccdD7",
            "--provider",
            "0xEd34ECBd91d29f7E13213ba321F5E7Fc8830a450",
            "--amount",
            "2.5",
        ],
    )
    assert result.exit_code == 0, result.output
    assert any(path == "/rpc/escrow/create" for _, path, _ in calls["post"])
    _, path, kwargs = next((b, p, k) for b, p, k in calls["post"] if p == "/rpc/escrow/create")
    payload = kwargs["json"]
    assert payload["job_id"] == "job-1"
    assert payload["amount"] == "2.5"


def _refusing_client_cls(detail: str):
    """AITBCHTTPClient stand-in whose POSTs fail with a 503 carrying ``detail``.

    Mirrors the production chain: requests.HTTPError (with ``.response``)
    wrapped in NetworkError via ``raise ... from``.
    """

    class RefusingClient:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, path, **kwargs):
            # escrow create resolves the settlement custody address from the
            # node's own /health node_wallet before it ever POSTs.
            if path.rstrip("/").endswith("/health") or path == "/health":
                return {"node_wallet": "0xEd34ECBd91d29f7E13213ba321F5E7Fc8830a450", "supported_chains": ["ait-testchain.local"]}
            return {"supported_chains": ["ait-testchain.local"]}

        def post(self, path, **kwargs):
            response = requests.Response()
            response.status_code = 503
            response._content = json.dumps({"detail": detail}).encode()
            try:
                raise requests.HTTPError("503 Server Error", response=response)
            except requests.HTTPError as e:
                raise NetworkError(f"POST request failed: {e}") from e

    return RefusingClient


_REFUSAL_DETAIL = "this node cannot sign escrow settlement transactions; the settlement node is at http://hub.aitbc.invalid"


def test_market_escrow_create_503_shows_detail(mock_market_config, monkeypatch):
    """A settlement-gate 503 surfaces the node's detail and exits non-zero."""
    monkeypatch.setattr(
        "aitbc_cli.commands.market.escrow.AITBCHTTPClient",
        _refusing_client_cls(_REFUSAL_DETAIL),
    )
    monkeypatch.setattr(
        "aitbc_cli.utils.escrow.AITBCHTTPClient",
        _refusing_client_cls(_REFUSAL_DETAIL),
    )
    monkeypatch.setattr(
        "aitbc_cli.utils.http_client.AITBCHTTPClient",
        _refusing_client_cls(_REFUSAL_DETAIL),
    )
    monkeypatch.setattr(
        "aitbc_cli.utils.chain_id.AITBCHTTPClient",
        _refusing_client_cls(_REFUSAL_DETAIL),
    )
    monkeypatch.setattr(
        "aitbc_cli.utils.escrow.create_signed_escrow_lock",
        lambda *args, **kwargs: ({"type": "ESCROW_LOCK"}, "0x" + "ab" * 64),
    )

    result = CliRunner().invoke(
        cli,
        [
            "market",
            "escrow",
            "create",
            "--job-id",
            "job-1",
            "--buyer",
            "0x11a01cb7F3C01AE8E8a992FE72fbDF3B530ccdD7",
            "--provider",
            "0xEd34ECBd91d29f7E13213ba321F5E7Fc8830a450",
            "--amount",
            "2.5",
        ],
    )
    assert result.exit_code != 0
    # The refusal is now gated: the command extracts the settlement retry
    # target from the detail and refuses a non-hub/non-loopback address,
    # surfacing the target in its own message rather than echoing the detail.
    assert "hub.aitbc.invalid" in result.output
    assert "refused" in result.output


def test_market_escrow_refund_503_shows_detail(mock_market_config, monkeypatch):
    """The refund path prints the follower's 503 detail instead of failing silently."""
    refusing = _refusing_client_cls(_REFUSAL_DETAIL)
    monkeypatch.setattr("aitbc_cli.commands.market.escrow.AITBCHTTPClient", refusing)
    monkeypatch.setattr("aitbc_cli.utils.http_client.AITBCHTTPClient", refusing)

    result = CliRunner().invoke(
        cli,
        ["market", "escrow", "refund", "--job-id", "job-1"],
    )
    assert _REFUSAL_DETAIL in result.output


def _settlement_503() -> NetworkError:
    """NetworkError carrying a 503 whose detail names a loopback settlement node."""
    response = requests.Response()
    response.status_code = 503
    response._content = json.dumps(
        {"detail": "this node cannot sign escrow settlement transactions; the settlement node is at http://127.0.0.1:9999"}
    ).encode()
    try:
        raise requests.HTTPError("503 Server Error", response=response)
    except requests.HTTPError as e:
        exc = NetworkError(f"POST request failed: {e}")
        exc.__cause__ = e
        return exc


def _post_config() -> SimpleNamespace:
    return SimpleNamespace(
        blockchain_rpc_url="http://127.0.0.1:8202",
        hub_discovery_url="",
        hub_proposer_id="0x1111111111111111111111111111111111111111",
        blockchain_rpc_api_key=None,
        blockchain_rpc_settlement_api_key=None,
    )


def test_post_escrow_rpc_retries_named_settlement_node(monkeypatch):
    """#2348: a settlement-incapable node's 503 names the settlement RPC —
    release/refund must retry it instead of stopping after local+hub."""
    from aitbc_cli.commands.market import escrow as escrow_mod

    attempted: list[str] = []

    class LocalClient:
        def __init__(self, base_url=None, **kwargs):
            self.base_url = base_url

        def post(self, path, **kwargs):
            attempted.append(self.base_url)
            raise _settlement_503()

    class SettlementClient:
        def __init__(self, base_url=None, **kwargs):
            self.base_url = base_url

        def post(self, path, **kwargs):
            attempted.append(self.base_url)
            return {"success": True, "tx_hash": "0xrel"}

    def fake_client(config, base, timeout=10):
        if "9999" in base:
            return SettlementClient(base_url=base)
        return LocalClient(base_url=base)

    monkeypatch.setattr(escrow_mod, "_get_rpc_client", fake_client)
    monkeypatch.setattr(escrow_mod, "_hub_base_url", lambda config: "")

    result, failures = escrow_mod._post_escrow_rpc(_post_config(), "/rpc/escrow/job-1/release", {})
    assert result == {"success": True, "tx_hash": "0xrel"}
    assert "http://127.0.0.1:9999" in attempted


def test_post_escrow_rpc_refuses_foreign_settlement_url(monkeypatch):
    """#2348: a server-named settlement URL outside hub/loopback is never
    followed — an attacker-controlled detail must not redirect the POST."""
    from aitbc_cli.commands.market import escrow as escrow_mod

    attempted: list[str] = []

    class RefusingClient:
        def __init__(self, base_url=None, **kwargs):
            self.base_url = base_url

        def post(self, path, **kwargs):
            attempted.append(self.base_url)
            response = requests.Response()
            response.status_code = 503
            response._content = json.dumps(
                {"detail": "cannot sign; the settlement node is at http://evil.example:8202"}
            ).encode()
            try:
                raise requests.HTTPError("503", response=response)
            except requests.HTTPError as e:
                raise NetworkError(f"POST failed: {e}") from e

    monkeypatch.setattr(escrow_mod, "_get_rpc_client", lambda config, base, timeout=10: RefusingClient(base_url=base))
    monkeypatch.setattr(escrow_mod, "_hub_base_url", lambda config: "")

    result, failures = escrow_mod._post_escrow_rpc(_post_config(), "/rpc/escrow/job-1/release", {})
    assert result is None
    assert all("evil.example" not in b for b in attempted)
    assert failures
