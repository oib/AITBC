"""CLI-LOOPBACK-1: loopback service URLs get a hint naming the fix.

On customer nodes the GPU service is not local and the hub gateway has no
/v1/gpu/ mount — a refused connection on localhost:8101 should say so.
Market reads already try the hub first via _candidate_bases, and
agent-msg peers' explicit --coordinator-url already wins.
"""

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.gpu_market as gm
from aitbc_cli.commands.gpu_market import gpu
from aitbc_cli.utils.http_client import NetworkError, loopback_service_hint


@pytest.mark.parametrize(
    "url,expect_hint",
    [
        ("http://localhost:8101", True),
        ("http://127.0.0.1:8102", True),
        ("http://[::1]:8101", True),
        ("", True),
        ("https://hub.example.net/v1/gpu", False),
        ("http://10.0.0.5:8101", False),
    ],
)
def test_loopback_service_hint_shape(url, expect_hint):
    hint = loopback_service_hint(url, "GPU")
    if expect_hint:
        assert "loopback" in hint
        assert "GPU" in hint
    else:
        assert hint == ""


def test_gpu_discover_loopback_names_fix(monkeypatch):
    class _Cfg:
        gpu_service_url = "http://localhost:8101"
        gpu_api_key = None

    class _Refused:
        def __init__(self, **kw):
            pass

        def get(self, *a, **k):
            raise NetworkError("GET request failed: connection refused")

        def close(self):
            pass

    monkeypatch.setattr(gm, "get_config", lambda: _Cfg())
    monkeypatch.setattr(gm, "AITBCHTTPClient", _Refused)
    result = CliRunner().invoke(gpu, obj={"output_format": "table"}, args=["discover"])
    assert result.exit_code != 0
    assert "loopback" in result.output
    assert "localhost:8101" in result.output
