"""Provider-key masking in ``evm_rpc`` error paths (TOOL-2).

Infura/Alchemy keys travel inside the RPC URL path or query, so an error
that echoes the URL — ours or httpx's — would write the key into journals
and pasted reports. Every abort raised by ``rpc_call``/``broadcast_raw``
must show only scheme+host+port and must scrub key-bearing URL parts out
of any echoed exception or RPC error body.
"""

import os
import tempfile

os.environ.setdefault(
    "API_KEY_STORAGE_PATH",
    os.path.join(tempfile.mkdtemp(prefix="aitbc-apikeys-"), "api_keys.json"),
)

import httpx
import pytest

from aitbc_cli.utils.evm_rpc import broadcast_raw, display_rpc_url, mask_rpc_url, rpc_call
from aitbc_cli.utils.error_handling import CLIError

PATH_KEY_URL = "https://mainnet.infura.io/v3/a9f8e7d6c5b4a39281706f5e4d3c2b1a"
QUERY_KEY_URL = "https://rpc.example.net/eth?apikey=Qk3yS3cr3tQu3ry"
PLAIN_URL = "http://127.0.0.1:8545"


def _fail_post(url, **kwargs):
    """httpx.post replacement whose exception echoes the full URL, the way
    httpx's own InvalidURL/ConnectError text can."""
    raise httpx.ConnectError(f"dial tcp: lookup failed for {url}")


def _abort_text(excinfo) -> str:
    exc = excinfo.value
    return str(exc) + str(exc.__cause__ or "")


class TestDisplayUrl:
    def test_path_key_dropped(self):
        assert display_rpc_url(PATH_KEY_URL) == "https://mainnet.infura.io"

    def test_query_key_dropped(self):
        assert display_rpc_url(QUERY_KEY_URL) == "https://rpc.example.net"

    def test_port_kept(self):
        assert display_rpc_url(PLAIN_URL) == "http://127.0.0.1:8545"

    def test_unparseable(self):
        assert display_rpc_url("not a url") == "<unparseable RPC URL>"


class TestMaskRpcUrl:
    def test_full_url_and_path_key(self):
        text = f"POST {PATH_KEY_URL} failed; also bare path /v3/a9f8e7d6c5b4a39281706f5e4d3c2b1a"
        masked = mask_rpc_url(text, PATH_KEY_URL)
        assert "a9f8e7d6c5b4a39281706f5e4d3c2b1a" not in masked
        assert "https://mainnet.infura.io" in masked

    def test_query_key(self):
        masked = mask_rpc_url(f"GET {QUERY_KEY_URL} refused", QUERY_KEY_URL)
        assert "Qk3yS3cr3tQu3ry" not in masked
        assert "https://rpc.example.net" in masked

    def test_embedded_credentials(self):
        url = "https://user:p4ssw0rd@rpc.example.net/"
        masked = mask_rpc_url(f"auth against {url} failed for user:p4ssw0rd", url)
        assert "p4ssw0rd" not in masked
        assert "user" not in masked.split("***")[0]


class TestRpcCallMasking:
    def test_httpx_exception_text_scrubbed_path_key(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", _fail_post)
        with pytest.raises(CLIError) as excinfo:
            rpc_call(None, PATH_KEY_URL, "eth_chainId", [])
        text = _abort_text(excinfo)
        assert "a9f8e7d6c5b4a39281706f5e4d3c2b1a" not in text
        assert "https://mainnet.infura.io" in text

    def test_httpx_exception_text_scrubbed_query_key(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", _fail_post)
        with pytest.raises(CLIError) as excinfo:
            rpc_call(None, QUERY_KEY_URL, "eth_chainId", [])
        text = _abort_text(excinfo)
        assert "Qk3yS3cr3tQu3ry" not in text
        assert "https://rpc.example.net" in text

    def test_rpc_error_body_scrubbed(self, monkeypatch):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"error": {"message": f"rejected key in {PATH_KEY_URL}"}}

        monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())
        with pytest.raises(CLIError) as excinfo:
            rpc_call(None, PATH_KEY_URL, "eth_chainId", [])
        assert "a9f8e7d6c5b4a39281706f5e4d3c2b1a" not in _abort_text(excinfo)


class TestBroadcastMasking:
    def test_async_post_failure_scrubbed(self, monkeypatch):
        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kwargs):
                raise httpx.ConnectError(f"unreachable: {url}")

        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        with pytest.raises(CLIError) as excinfo:
            broadcast_raw(None, PATH_KEY_URL, "0xdeadbeef")
        text = _abort_text(excinfo)
        assert "a9f8e7d6c5b4a39281706f5e4d3c2b1a" not in text
        assert "https://mainnet.infura.io" in text
