"""Unit tests for the provider-side IPFS hosting sweeper."""

from pathlib import Path
from unittest.mock import Mock, patch

import ipfs_pinning_sweeper
import pytest

PROVIDER = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"
CID = "QmZdJ5Pjb6XC3oSHhJYUAnHT9PaNSbMqTSdozvj1WErNbh"


def _job(job_id: str, state: str = "RUNNING", cid: str | None = CID, **payload_extra):
    payload = {"cid": cid, "size": 1000}
    payload.update(payload_extra)
    return {
        "job_id": job_id,
        "state": state,
        "service_type": "ipfs",
        "buyer_address": "0xBuyer",
        "payload": payload,
        "constraints": {"disk_quota_mb": 100},
    }


def _resp(json_data=None, status=200):
    r = Mock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else {}
    r.raise_for_status = Mock()
    if status >= 400:
        import requests

        r.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
    return r


@pytest.fixture()
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "ipfs-pinning.json"


@pytest.fixture()
def sweeper(monkeypatch):
    """Patch the module's HTTP layer: ipfs POSTs and market GET/POST."""
    monkeypatch.setattr(ipfs_pinning_sweeper, "IPFS_API_URL", "http://127.0.0.1:5002")
    monkeypatch.delenv("IPFS_HOSTING_ENABLED", raising=False)
    # Signing is stubbed: market request auth is covered by its own tests.
    monkeypatch.setattr(
        ipfs_pinning_sweeper,
        "_signed_request_params",
        lambda address, route: {
            "signer_address": address,
            "chain_id": "test-chain",
            "issued_at": 1,
            "signature": "sig",
        },
    )
    calls = {"ipfs": [], "jobs_get": [], "confirm": []}

    def fake_post(url, **kwargs):
        if "/v1/market/jobs/" in url and url.endswith("/pin-confirm"):
            calls["confirm"].append((url, kwargs.get("json")))
            return _resp({})
        calls["ipfs"].append(url)
        if url.endswith("/api/v0/object/stat"):
            return _resp({"CumulativeSize": 1000})
        return _resp({})

    def fake_get(url, **kwargs):
        calls["jobs_get"].append(kwargs.get("params", {}))
        return _resp([])

    with (
        patch.object(ipfs_pinning_sweeper.requests, "post", side_effect=fake_post),
        patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=fake_get),
    ):
        yield calls


def _jobs_response(jobs):
    def fake_get(url, **kwargs):
        return _resp(jobs)

    return fake_get


@pytest.mark.unit
def test_sweep_disabled_by_env(monkeypatch, state_path, sweeper):
    monkeypatch.setenv("IPFS_HOSTING_ENABLED", "0")
    result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result == {"pinned": 0, "confirmed": 0, "unpinned": 0, "skipped_quota": 0, "errors": 0}
    assert sweeper["ipfs"] == []


@pytest.mark.unit
def test_sweep_empty_provider(state_path, sweeper):
    assert ipfs_pinning_sweeper.sweep_once("", state_path)["errors"] == 0
    assert sweeper["ipfs"] == []


@pytest.mark.unit
def test_sweep_daemon_down(state_path):
    import requests

    with patch.object(ipfs_pinning_sweeper.requests, "post", side_effect=requests.ConnectionError("down")):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["errors"] == 0  # daemon down is a quiet skip, not an error
    assert not state_path.exists()


@pytest.mark.unit
def test_sweep_pins_and_confirms(state_path, sweeper):
    job = _job("job-1", state="QUEUED")
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([job])):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["pinned"] == 1
    assert result["confirmed"] == 1
    assert any(u.endswith("/api/v0/pin/add") for u in sweeper["ipfs"])
    assert sweeper["confirm"][0][1]["provider_confirmed"] is True
    assert ipfs_pinning_sweeper._load_state(state_path)["job-1"]["cid"] == CID


@pytest.mark.unit
def test_fetch_jobs_sends_provider_signature(state_path, sweeper):
    """The jobs fetch must carry the signed proof or the market returns the
    redacted public view (or a 403) and the sweeper cannot pin."""
    job = _job("job-1", state="QUEUED")
    seen: list[dict] = []

    def fake_get(url, **kwargs):
        seen.append(kwargs.get("params", {}))
        return _resp([job])

    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=fake_get):
        ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    params = seen[0]
    assert params["signer_address"] == PROVIDER
    assert params["signature"] == "sig"
    assert params["chain_id"]


@pytest.mark.unit
def test_pin_confirm_sends_provider_signature(state_path, sweeper):
    job = _job("job-1", state="QUEUED")
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([job])):
        ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    body = sweeper["confirm"][0][1]
    assert body["provider_confirmed"] is True
    assert body["signer_address"] == PROVIDER
    assert body["signature"]


@pytest.mark.unit
def test_sweep_unsigned_fetch_is_unknown_not_empty(state_path, sweeper, monkeypatch):
    """No signing material -> fetch returns None (unknown): error counted,
    no pins, and crucially no unpin of tracked entries."""
    monkeypatch.setattr(ipfs_pinning_sweeper, "_signed_request_params", lambda address, route: None)
    ipfs_pinning_sweeper._save_state(state_path, {"job-1": {"cid": CID, "size": 1000, "pinned_at": "t"}})
    result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["errors"] == 1
    assert result["unpinned"] == 0
    assert result["pinned"] == 0
    assert "job-1" in ipfs_pinning_sweeper._load_state(state_path)


@pytest.mark.unit
def test_sweep_auth_rejected_fetch_is_unknown_not_empty(state_path, sweeper):
    """A 401/403 from the market is a failed fetch -> None, never an empty
    list, so tracked pins are not unpinned on a rejection."""
    ipfs_pinning_sweeper._save_state(state_path, {"job-1": {"cid": CID, "size": 1000, "pinned_at": "t"}})
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=lambda url, **kw: _resp({}, status=403)):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["errors"] == 1
    assert result["unpinned"] == 0
    assert "job-1" in ipfs_pinning_sweeper._load_state(state_path)


@pytest.mark.unit
def test_provider_key_reads_wallet_dir(tmp_path, monkeypatch):
    key = "0x" + "33" * 32
    from aitbc.crypto.crypto import derive_ethereum_address

    wallet = tmp_path / "wallets"
    wallet.mkdir()
    import json as _json

    (wallet / "default.json").write_text(_json.dumps({"address": derive_ethereum_address(key), "private_key": key}))
    (wallet / "other.json").write_text(_json.dumps({"address": "0x" + "ab" * 20, "private_key": "0x" + "77" * 32}))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet))

    address = derive_ethereum_address(key)
    assert ipfs_pinning_sweeper._provider_key(address) == key
    assert ipfs_pinning_sweeper._provider_key("0x" + "cd" * 20) is None


@pytest.mark.unit
def test_signed_params_shape(tmp_path, monkeypatch):
    """Signed params carry the proof fields; the signed message is the
    canonical jobs-request message the market verifies."""
    key = "0x" + "33" * 32
    from aitbc.crypto.crypto import derive_ethereum_address
    from aitbc.crypto.crypto import recover_signer
    from aitbc.market.job_request_signature import jobs_request_message

    wallet = tmp_path / "wallets"
    wallet.mkdir()
    import json as _json

    address = derive_ethereum_address(key)
    (wallet / "default.json").write_text(_json.dumps({"address": address, "private_key": key}))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(wallet))
    monkeypatch.setenv("AITBC_CHAIN_ID", "chain-test")

    params = ipfs_pinning_sweeper._signed_request_params(address, "/v1/market/jobs")
    assert params is not None
    assert params["signer_address"] == address
    assert params["chain_id"] == "chain-test"
    assert params["issued_at"] > 0
    recovered = recover_signer(
        jobs_request_message(address, "chain-test", params["issued_at"], "/v1/market/jobs"),
        params["signature"],
    )
    assert recovered == address


@pytest.mark.unit
def test_sweep_skips_already_confirmed(state_path, sweeper):
    job = _job("job-1", provider_confirmed=True)
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([job])):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    # Confirmed jobs still get pinned (idempotent no-op) so the state file is
    # rebuilt after a wipe and the CID can be unpinned at end of rental.
    assert result["pinned"] == 1
    assert result["confirmed"] == 0
    assert "job-1" in ipfs_pinning_sweeper._load_state(state_path)


@pytest.mark.unit
def test_sweep_reconfirms_when_state_but_unconfirmed(state_path, sweeper):
    ipfs_pinning_sweeper._save_state(state_path, {"job-1": {"cid": CID, "size": 1000, "pinned_at": "t"}})
    job = _job("job-1", state="RUNNING")
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([job])):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["pinned"] == 0  # already in state -> no re-pin
    assert result["confirmed"] == 1
    assert not any(u.endswith("/api/v0/pin/add") for u in sweeper["ipfs"])


@pytest.mark.unit
def test_sweep_unpins_terminal_job(state_path, sweeper):
    ipfs_pinning_sweeper._save_state(state_path, {"job-1": {"cid": CID, "size": 1000, "pinned_at": "t"}})
    job = _job("job-1", state="RELEASED")
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([job])):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["unpinned"] == 1
    assert any(u.endswith("/api/v0/pin/rm") for u in sweeper["ipfs"])
    assert ipfs_pinning_sweeper._load_state(state_path) == {}


@pytest.mark.unit
def test_sweep_keeps_shared_cid_while_active(state_path, sweeper):
    ipfs_pinning_sweeper._save_state(
        state_path,
        {
            "job-1": {"cid": CID, "size": 1000, "pinned_at": "t"},
            "job-2": {"cid": CID, "size": 1000, "pinned_at": "t"},
        },
    )
    jobs = [
        _job("job-1", state="RELEASED"),
        _job("job-2", state="RUNNING", provider_confirmed=True),
    ]
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response(jobs)):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["unpinned"] == 0  # CID still referenced by the active job
    assert "job-1" not in ipfs_pinning_sweeper._load_state(state_path)


@pytest.mark.unit
def test_fetch_failure_keeps_state(state_path, sweeper):
    import requests

    ipfs_pinning_sweeper._save_state(state_path, {"job-1": {"cid": CID, "size": 1000, "pinned_at": "t"}})
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=requests.ConnectionError("hub down")):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["errors"] == 1
    assert result["unpinned"] == 0
    assert "job-1" in ipfs_pinning_sweeper._load_state(state_path)


@pytest.mark.unit
def test_sweep_skips_job_without_cid(state_path, sweeper):
    job = _job("job-1", state="QUEUED", cid=None)
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([job])):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["pinned"] == 0
    assert not any(u.endswith("/api/v0/pin/add") for u in sweeper["ipfs"])


@pytest.mark.unit
def test_sweep_quota_skip(state_path, sweeper):
    # 100 MB quota; buyer already uses ~all of it and the declared sizes overflow.
    big = 200 * 1024 * 1024
    jobs = [
        _job("job-1", state="RUNNING", provider_confirmed=True, size=big),
        _job("job-2", state="QUEUED", size=big),
    ]
    with (
        patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response(jobs)),
        patch.object(ipfs_pinning_sweeper.requests, "post") as post_mock,
    ):

        def fake_post(url, **kwargs):
            if "/api/v0/id" in url:
                return _resp({"ID": "peer"})
            if url.endswith("/api/v0/object/stat"):
                return _resp({"CumulativeSize": big})
            return _resp({})

        post_mock.side_effect = fake_post
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["skipped_quota"] == 1
    # job-1 is already provider_confirmed -> exempt from the quota gate; the
    # pin is state-recovery, not new spend.
    assert result["pinned"] == 1
