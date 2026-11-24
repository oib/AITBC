"""`aitbc market rate` and `aitbc market ratings` against a service that does not exist.

`AITBCHTTPClient` calls `raise_for_status` and re-raises everything -- including a 4xx --
as `NetworkError`, and both commands caught that and printed "Market service not
reachable ... Ensure market-service is reachable at <url>". That is a wrong diagnosis of a service
that answered, and it is the message a user would get the moment V23-81 made those two routes
return 404 for an unknown service. These pin the branch that tells the two apart.

Here rather than in `cli/tests/`, which is where the other command tests live: `cli/` has its
own `pytest.ini` and is not in the root `testpaths`, so nothing there is collected by the main
run. Those files also shell out to the installed binary and need live services. These stay
in-process and stub the client, so they check the error handling and nothing else.
"""

import pytest
from click.testing import CliRunner
from eth_account import Account

from aitbc.exceptions import NetworkError
from aitbc_cli.commands.market import market
from aitbc_cli.commands.market import ratings as ratings_module

_SIGNER = Account.create()


class _Client:
    """Stands in for `AITBCHTTPClient`, raising what the real one raises."""

    def __init__(self, error: Exception):
        self._error = error

    def __call__(self, *args, **kwargs):
        return self

    def get(self, *args, **kwargs):
        raise self._error

    def post(self, *args, **kwargs):
        raise self._error


@pytest.fixture
def runner():
    return CliRunner()


def _stub(monkeypatch, error: Exception):
    monkeypatch.setattr(ratings_module, "AITBCHTTPClient", _Client(error))


def _stub_signing(monkeypatch):
    """#2508: ``rate`` signs the request with the resolved market wallet —
    there is no self-declared ``--reviewer-id`` anymore."""
    monkeypatch.setattr(
        ratings_module, "get_market_wallet", lambda *a, **kw: (_SIGNER.address, _SIGNER.key.hex(), "test-wallet")
    )
    monkeypatch.setattr(ratings_module, "get_chain_id", lambda *a, **kw: "test-chain")


def _http_error(status_code: int) -> NetworkError:
    """NetworkError shaped like the real client's wrap of a requests.HTTPError.

    The status classifier walks the cause chain for ``.response.status_code``;
    a bare message string carries no response and must NOT classify (#2478).
    """
    err = NetworkError(f"GET request failed: {status_code} Client Error")
    cause = Exception(f"{status_code} Error")
    cause.response = type("R", (), {"status_code": status_code})()
    err.__cause__ = cause
    return err


NOT_FOUND = _http_error(404)
UNREACHABLE = NetworkError("GET request failed: HTTPConnectionPool(host='localhost', port=8102): refused")
# #2478 regression: transport failure text containing status digits but no
# response object must not be classified as a 404.
UNREACHABLE_WITH_DIGITS = NetworkError(
    "GET request failed: HTTPConnectionPool(host='localhost', port=8404): refused (tx 0x404abc)"
)


def test_ratings_reports_a_missing_service_as_missing(runner, monkeypatch):
    _stub(monkeypatch, NOT_FOUND)
    result = runner.invoke(market, ["ratings", "--service-id", "no-such-service"], obj={})
    assert result.exit_code != 0
    assert "No such service: no-such-service" in result.output
    assert "is running" not in result.output


def test_ratings_still_reports_an_unreachable_service_as_unreachable(runner, monkeypatch):
    _stub(monkeypatch, UNREACHABLE)
    result = runner.invoke(market, ["ratings", "--service-id", "no-such-service"], obj={})
    assert result.exit_code != 0
    assert "Market service not reachable" in result.output
    assert "Ensure market-service is reachable" in result.output


def test_ratings_unreachable_with_status_digits_is_not_a_404(runner, monkeypatch):
    """#2478: ':8404'/'404' inside a connection error is not an HTTP 404."""
    _stub(monkeypatch, UNREACHABLE_WITH_DIGITS)
    result = runner.invoke(market, ["ratings", "--service-id", "no-such-service"], obj={})
    assert result.exit_code != 0
    assert "No such service" not in result.output
    assert "Market service not reachable" in result.output


def test_rate_reports_a_missing_service_as_missing(runner, monkeypatch):
    _stub(monkeypatch, NOT_FOUND)
    _stub_signing(monkeypatch)
    result = runner.invoke(
        market,
        [
            "rate",
            "--service-id",
            "no-such-service",
            "--rating",
            "5.0",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "No such service: no-such-service" in result.output
    assert "is running" not in result.output


def test_rate_still_reports_an_unreachable_service_as_unreachable(runner, monkeypatch):
    _stub(monkeypatch, UNREACHABLE)
    _stub_signing(monkeypatch)
    result = runner.invoke(
        market,
        [
            "rate",
            "--service-id",
            "no-such-service",
            "--rating",
            "5.0",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "Market service not reachable" in result.output
    assert "Ensure market-service is reachable" in result.output


def test_rate_rejects_an_out_of_range_rating_before_any_request(runner, monkeypatch):
    """The client is never constructed, so a bad rating cannot be blamed on the network.

    The command also prints a bare "Error rating service: " after this, because the
    `click.Abort` it raises for the range check is inside the `try` and its own
    `except Exception` catches it. Cosmetic, unrelated to V23-81, and not asserted here --
    asserting it would make the wart load-bearing.
    """

    def _explode(*args, **kwargs):
        raise AssertionError("the rating scale is checked before the request")

    monkeypatch.setattr(ratings_module, "AITBCHTTPClient", _explode)
    result = runner.invoke(
        market,
        [
            "rate",
            "--service-id",
            "some-service",
            "--rating",
            "9.0",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "Rating must be between 1.0 and 5.0" in result.output


class _CaptureClient:
    """Records the base_url passed to AITBCHTTPClient and returns a fixed response."""

    def __init__(self, base_url: str, timeout: int = 10, headers: dict | None = None, api_key: str | None = None):
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers
        self.api_key = api_key

    def get(self, *args, **kwargs):
        return {"service_info": {"avg_rating": 5.0, "rating_count": 1}, "ratings": []}

    def post(self, *args, **kwargs):
        return {
            "status": "success",
            "rating": {
                "service_id": kwargs.get("json", {}).get("service_id", "svc-1"),
                "rating": 5.0,
                "reviewer_id": "0x9bceE7FF5de39627FB60A4cE03eD3959357ec91e",
                "comment": "",
                "created_at": "2026-09-10T18:21:58.763625",
            },
        }


def test_rate_uses_market_url_override(runner, monkeypatch):
    """--market-url is passed through to the HTTP client base URL."""
    captured: list[str] = []

    def _client_factory(base_url: str, **kwargs):
        captured.append(base_url)
        return _CaptureClient(base_url, **kwargs)

    monkeypatch.setattr(ratings_module, "AITBCHTTPClient", _client_factory)
    _stub_signing(monkeypatch)
    result = runner.invoke(
        market,
        [
            "rate",
            "--service-id",
            "svc-1",
            "--rating",
            "5.0",
            "--market-url",
            "https://market.example.com/v1/",
        ],
        obj={},
    )
    assert result.exit_code == 0
    assert captured == ["https://market.example.com"]


def test_ratings_uses_market_url_override(runner, monkeypatch):
    """--market-url is passed through to the HTTP client base URL for ratings too."""
    captured: list[str] = []

    def _client_factory(base_url: str, **kwargs):
        captured.append(base_url)
        return _CaptureClient(base_url, **kwargs)

    monkeypatch.setattr(ratings_module, "AITBCHTTPClient", _client_factory)
    result = runner.invoke(
        market,
        [
            "ratings",
            "--service-id",
            "svc-1",
            "--market-url",
            "https://market.example.com/v1/",
        ],
        obj={},
    )
    assert result.exit_code == 0
    assert captured == ["https://market.example.com"]
