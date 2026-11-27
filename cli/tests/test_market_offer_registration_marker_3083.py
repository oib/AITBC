"""SHOP-OFFER-REGISTER-AUTH-1 (#3083): a refused ``POST /v1/market/offer``
must surface a stable ``market-registration: FAILED`` marker on the CLI's
status stream.

``_register_software_offer`` is best-effort by design (#2954 — the on-chain
listing already landed, so the command still exits 0), which is exactly why
the miner used to log "Published default offer" while the registry row was
missing: the 401 from the user-tier authz hardening was invisible. The
marker gives supervising callers (``publish_default_offers``) a greppable
signal; it rides the status-label stream — stdout in table mode, stderr
under ``--output json`` — so machine-readable stdout stays clean.
"""

from decimal import Decimal

import pytest

import aitbc_cli.commands.market.offers as offers_mod
from aitbc.exceptions import NetworkError


class _Client:
    def __init__(self, outcome):
        self._outcome = outcome
        self.posts: list[tuple[str, dict]] = []

    def post(self, path, json=None, **kwargs):
        self.posts.append((path, json or {}))
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


_GPU = {
    "gpu_name": "RTX 4090",
    "gpu_model": "RTX 4090",
    "gpu_device": "0",
    "gpu_uuid": "GPU-UUID-1",
    "gpu_memory_gb": 24,
    "compute_capability": "8.9",
}


def _register(client, monkeypatch):
    monkeypatch.setattr(offers_mod, "_market_service_client", lambda hub_url: client)
    monkeypatch.setattr(offers_mod, "sign_transaction_data", lambda *a, **kw: "deadbeef")
    return offers_mod._register_software_offer(
        "http://hub",
        wallet_address="0xprovider",
        private_key="0xpriv",
        provider_node_id="node-1",
        chain_id="ait-test",
        service_type="whisper",
        model_or_variant="base",
        offer_id="sw_offer_test",
        price=Decimal("0.5"),
        unit="per_audio_min",
        description=None,
        deployment_type="local",
        gpu=dict(_GPU),
        gpu_offer_id=None,
        disk_quota_mb=None,
        public_endpoint="https://node.example/whisper",
        local_endpoint="http://localhost:8110",
        ipfs_port=0,
    )


@pytest.mark.unit
def test_refused_registration_emits_failed_marker(monkeypatch, capsys):
    """401/NetworkError → returns False and prints the stable marker."""
    client = _Client(NetworkError("POST request failed: 401 Unauthorized"))

    assert _register(client, monkeypatch) is False

    out = capsys.readouterr()
    status = f"{out.out}{out.err}"
    assert "market-registration: FAILED" in status
    assert client.posts and client.posts[0][0] == "/v1/market/offer"


@pytest.mark.unit
def test_successful_registration_has_no_marker(monkeypatch, capsys):
    """Accepted POST → True, 'registered in market' info, no FAILED marker."""
    client = _Client({"plugin_id": "whisper-base"})

    assert _register(client, monkeypatch) is True

    out = capsys.readouterr()
    status = f"{out.out}{out.err}"
    assert "market-registration: FAILED" not in status
    assert "registered in market" in status
