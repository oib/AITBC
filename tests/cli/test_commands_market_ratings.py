"""`aitbc market rate` and `aitbc market ratings` against a service that does not exist.

`AITBCHTTPClient` calls `raise_for_status` and re-raises everything -- including a 4xx --
as `NetworkError`, and both commands caught that and printed "Marketplace service not
reachable ... Ensure marketplace-service is reachable at <url>". That is a wrong diagnosis of a service
that answered, and it is the message a user would get the moment V23-81 made those two routes
return 404 for an unknown service. These pin the branch that tells the two apart.

Here rather than in `cli/tests/`, which is where the other command tests live: `cli/` has its
own `pytest.ini` and is not in the root `testpaths`, so nothing there is collected by the main
run. Those files also shell out to the installed binary and need live services. These stay
in-process and stub the client, so they check the error handling and nothing else.
"""

import pytest
from click.testing import CliRunner

from aitbc.exceptions import NetworkError
from aitbc_cli.commands.market import market
from aitbc_cli.commands.market import ratings as ratings_module


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


NOT_FOUND = NetworkError("GET request failed: 404 Client Error: Not Found for url: http://localhost:8102/x")
UNREACHABLE = NetworkError("GET request failed: HTTPConnectionPool(host='localhost', port=8102): refused")


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
    assert "Marketplace service not reachable" in result.output
    assert "Ensure marketplace-service is reachable" in result.output


def test_rate_reports_a_missing_service_as_missing(runner, monkeypatch):
    _stub(monkeypatch, NOT_FOUND)
    result = runner.invoke(
        market,
        [
            "rate",
            "--service-id",
            "no-such-service",
            "--rating",
            "5.0",
            "--reviewer-id",
            "0x9bceE7FF5de39627FB60A4cE03eD3959357ec91e",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "No such service: no-such-service" in result.output
    assert "is running" not in result.output


def test_rate_still_reports_an_unreachable_service_as_unreachable(runner, monkeypatch):
    _stub(monkeypatch, UNREACHABLE)
    result = runner.invoke(
        market,
        [
            "rate",
            "--service-id",
            "no-such-service",
            "--rating",
            "5.0",
            "--reviewer-id",
            "0x9bceE7FF5de39627FB60A4cE03eD3959357ec91e",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "Marketplace service not reachable" in result.output
    assert "Ensure marketplace-service is reachable" in result.output


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
            "--reviewer-id",
            "0x9bceE7FF5de39627FB60A4cE03eD3959357ec91e",
        ],
        obj={},
    )
    assert result.exit_code != 0
    assert "Rating must be between 1.0 and 5.0" in result.output


class _CaptureClient:
    """Records the base_url passed to AITBCHTTPClient and returns a fixed response."""

    def __init__(self, base_url: str, timeout: int = 10, headers: dict | None = None):
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers

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


def test_rate_uses_marketplace_url_override(runner, monkeypatch):
    """--marketplace-url is passed through to the HTTP client base URL."""
    captured: list[str] = []

    def _client_factory(base_url: str, **kwargs):
        captured.append(base_url)
        return _CaptureClient(base_url, **kwargs)

    monkeypatch.setattr(ratings_module, "AITBCHTTPClient", _client_factory)
    result = runner.invoke(
        market,
        [
            "rate",
            "--service-id",
            "svc-1",
            "--rating",
            "5.0",
            "--reviewer-id",
            "0x9bceE7FF5de39627FB60A4cE03eD3959357ec91e",
            "--marketplace-url",
            "https://market.example.com/v1/",
        ],
        obj={},
    )
    assert result.exit_code == 0
    assert captured == ["https://market.example.com"]


def test_ratings_uses_marketplace_url_override(runner, monkeypatch):
    """--marketplace-url is passed through to the HTTP client base URL for ratings too."""
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
            "--marketplace-url",
            "https://market.example.com/v1/",
        ],
        obj={},
    )
    assert result.exit_code == 0
    assert captured == ["https://market.example.com"]
