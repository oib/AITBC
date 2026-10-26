"""Tests for main app endpoints and lifecycle."""


def test_health_endpoint(client):
    """Test health endpoint returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_metrics_endpoint_json(client):
    """Test /metrics returns JSON metrics."""
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "api_requests" in data


def test_prometheus_endpoint(client):
    """Test /prometheus returns Prometheus format."""
    response = client.get("/prometheus")
    assert response.status_code == 200
    assert "python_gc" in response.text or "# HELP" in response.text


def test_prometheus_relay_labels_are_metadata_only(client):
    """ESCROW-RELAY-OBS-1 ruling condition 1: the relay counter may carry
    ONLY {relay,result} — no job_id, address or amount labels (the scrape
    endpoint is now unauthenticated, so its output must be metadata-only)."""
    from coordinator_api.contexts.payments.services.escrow_relay_metrics import (
        record_escrow_relay_result,
    )

    record_escrow_relay_result("release", "ok")
    record_escrow_relay_result("create", "replay")
    response = client.get("/prometheus")
    assert response.status_code == 200
    for line in response.text.splitlines():
        if not line.startswith("aitbc_escrow_relay_requests_total{"):
            continue
        labels = line.split("{", 1)[1].split("}", 1)[0]
        keys = sorted(kv.split("=", 1)[0] for kv in labels.split(","))
        assert keys == ["relay", "result"], f"unexpected label set: {labels}"
    # The series must actually exist after the two records above.
    assert 'aitbc_escrow_relay_requests_total{relay="release",result="ok"}' in response.text


def test_openapi_endpoint(client):
    """Test OpenAPI schema endpoint."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data
