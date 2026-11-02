"""Phase-0 pin for MARKET-AUTH-MISSING-1 (#813).

The market service's mutating routes answer without credentials. Only
``require_market_api_key`` is wired (job access + parameters/apply);
everything else — release/refund, book, cancel, match, offer/job creation,
rental-token upsert, /v1/transactions — is open, and the service holds
BLOCKCHAIN_RPC_API_KEY, so it is an unauthenticated proxy into the gated
escrow-settle endpoints.

Desired behaviour (pinned here): every mutating route answers 401/403 to a
request without credentials. All cases FAIL on current main — the routes
answer — that is the bug demonstration.
"""

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from market_service.main import app


@pytest.fixture(scope="module")
def client():
    # Arm the authenticator the way production runs it (MARKET_API_KEY set);
    # without a key configured the dependency refuses 501 rather than 401.
    from market_service.main import require_market_api_key

    require_market_api_key.auth_enabled = True
    require_market_api_key.expected_key = "test-market-key"
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


MUTATING_ROUTES = [
    ("POST", "/v1/market/jobs/job-x/release", {"tx_hash": "0xdeadbeef"}),
    ("POST", "/v1/market/jobs/job-x/refund", {}),
    ("POST", "/v1/market/jobs/job-x/cancel", {}),
    ("POST", "/v1/market/offers/offer-x/book", {}),
    ("POST", "/v1/market/offers/offer-x/cancel", {}),
    ("POST", "/v1/market/offers", {"provider": "0xabc", "price": "1"}),
    ("POST", "/v1/market/bids/bid-x/complete", {"tx_hash": "0xdead"}),
    ("POST", "/v1/market/match", {}),
    ("POST", "/v1/market/jobs", {"state": "FAILED"}),
    ("POST", "/v1/market/ipfs/rental-token", {"access_key": "k", "access_secret": "s"}),
    ("POST", "/v1/transactions", {}),
]


@pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
def test_mutating_route_requires_credentials(client, method, path, body):
    resp = client.request(method, path, json=body)
    assert resp.status_code in (401, 403), f"{method} {path} answered {resp.status_code} without credentials"
