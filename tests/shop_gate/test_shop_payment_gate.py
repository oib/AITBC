"""Phase-0 pin for SHOP-ENDPOINTS-NO-PAYMENT-GATE-1 (#803).

Ruling 6A: the gate is a per-job access token, buyer-scoped, same shape as
the market access path. Today the shop's public ffmpeg/whisper endpoints
run for anyone — payment is a convention of the CLI, not a check on the
endpoint.

Desired: a POST to a paid shop endpoint without a buyer access token is
refused 401/403 before the handler runs. FAILS on current main: the
handlers are reached (they answer 422 on an empty body — field validation,
not a gate).
"""

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


def _app(path: str, module: str):
    import importlib.util

    svc_dir = Path(__file__).parents[2] / path
    sys.path.insert(0, str(svc_dir))
    spec = importlib.util.spec_from_file_location(f"shop_{module}", svc_dir / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


@pytest.mark.parametrize(
    "svc_path,module,route",
    [
        ("apps/ffmpeg", "main", "/process"),
        ("apps/whisper", "main", "/transcribe"),
    ],
)
def test_paid_endpoint_requires_access_token(svc_path, module, route):
    app = _app(svc_path, module)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(route)
    assert resp.status_code in (401, 403), f"{module}{route} answered {resp.status_code} with no access token"
