"""Pin for SHOP-ENDPOINTS-NO-PAYMENT-GATE-1 (#803), post-fix contract.

Ruling 6A + 8222: paid shop endpoints require a per-job access token
(X-Access-Key + X-Access-Secret) strictly bound to the job (X-Job-Id).
Green on the fix; FAILS on pre-fix main (handlers answered anonymous
requests).
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _app(path: str, module: str):
    svc_dir = Path(__file__).parents[2] / path
    sys.path.insert(0, str(svc_dir))
    spec = importlib.util.spec_from_file_location(f"shop_{module}", svc_dir / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


PAID_ROUTES = [
    ("apps/ffmpeg", "ffmpeg_main", "/process"),
    ("apps/whisper", "whisper_main", "/transcribe"),
    ("apps/hermes_agent", "hermes_main", "/run"),
    ("apps/ollama_gate", "ollama_gate_main", "/api/generate"),
]


@pytest.mark.parametrize("svc_path, module, route", PAID_ROUTES)
def test_paid_endpoint_requires_access_token(svc_path, module, route):
    client = TestClient(_app(svc_path, module), raise_server_exceptions=False)
    resp = client.post(route)
    assert resp.status_code in (401, 403), f"{module}{route} answered {resp.status_code} with no access token"


@pytest.mark.parametrize("svc_path, module, route", PAID_ROUTES)
def test_token_must_match_the_request_job(svc_path, module, route):
    """Strict binding: a valid token for job-A does not open job-B's route."""
    app = _app(svc_path, module)
    client = TestClient(app, raise_server_exceptions=False)
    with patch("aitbc.shop_gate._verify", return_value={"job_id": "job-A"}):
        resp = client.post(
            route,
            headers={
                "X-Access-Key": "k0123456789abcdef",
                "X-Access-Secret": "s",
                "X-Job-Id": "job-B",
            },
        )
    assert resp.status_code == 403


@pytest.mark.parametrize("svc_path, module, route", PAID_ROUTES)
def test_access_key_must_be_a_single_safe_path_segment(svc_path, module, route):
    """Traversal keys (SHOPGATE-ACCESS-KEY-PATH-TRAVERSAL-1, #1087): a key
    that is not a single safe URL path segment is refused before the
    market verify call is even attempted."""
    app = _app(svc_path, module)
    client = TestClient(app, raise_server_exceptions=False)
    with patch("aitbc.shop_gate._verify", side_effect=AssertionError("_verify must not be called")):
        resp = client.post(
            route,
            headers={
                "X-Access-Key": "../jobs/job-1",
                "X-Access-Secret": "s",
                "X-Job-Id": "job-1",
            },
        )
    assert resp.status_code == 401
