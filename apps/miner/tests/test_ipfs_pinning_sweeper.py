"""Unit tests for the provider-side IPFS hosting sweeper."""

import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch

import base58
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


def _resp(json_data=None, status=200, text=None):
    r = Mock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else {}
    r.text = text if text is not None else (json.dumps(json_data) if json_data is not None else "")
    r.iter_content = lambda *a, **k: iter([b""])
    r.close = Mock()
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
        lambda address, route, binding=None: {
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
        if url.endswith("/api/v0/dag/stat"):
            return _resp({}, text='{"TotalSize": 1000}')
        if url.endswith("/api/v0/cat"):
            return _resp({})
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
    """Offset-aware market stub: honours ``offset``/``limit`` on the list route
    and serves ``GET /v1/market/jobs/{id}`` for the per-job unpin check."""
    by_id = {str(j.get("job_id") or j.get("id")): j for j in jobs}

    def fake_get(url, **kwargs):
        if "/v1/market/jobs/" in url:
            job_id = url.rsplit("/", 1)[-1]
            job = by_id.get(job_id)
            if job is None:
                return _resp({}, status=404)
            return _resp(job)
        params = kwargs.get("params", {})
        try:
            offset = int(params.get("offset", 0) or 0)
            limit = int(params.get("limit", 500) or 500)
        except (TypeError, ValueError):
            offset, limit = 0, 500
        return _resp(jobs[offset : offset + limit])

    return fake_get


@pytest.mark.unit
def test_sweep_disabled_by_env(monkeypatch, state_path, sweeper):
    monkeypatch.setenv("IPFS_HOSTING_ENABLED", "0")
    result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result == {
        "pinned": 0,
        "confirmed": 0,
        "unpinned": 0,
        "skipped_quota": 0,
        "errors": 0,
        "truncated": 0,
        "deferred": 0,
        "reclaimed": 0,
    }
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
    monkeypatch.setattr(ipfs_pinning_sweeper, "_signed_request_params", lambda address, route, binding=None: None)
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
            if url.endswith("/api/v0/dag/stat"):
                return _resp(text=f'{{"TotalSize": {big}}}')
            return _resp({})

        post_mock.side_effect = fake_post
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["skipped_quota"] == 1
    # job-1 is already provider_confirmed -> exempt from the quota gate; the
    # pin is state-recovery, not new spend.
    assert result["pinned"] == 1


@pytest.mark.unit
def test_sweep_paginates_job_listing(state_path, sweeper, monkeypatch):
    """#1489: the sweeper must page past the first 500 jobs, not truncate."""
    monkeypatch.setattr(ipfs_pinning_sweeper, "_JOB_PAGE_SIZE", 2)
    jobs = [_job(f"job-{i}", state="RUNNING") for i in range(3)]
    seen_offsets = []

    def fake_get(url, **kwargs):
        if "/v1/market/jobs/" in url:
            return _resp({}, status=404)
        params = kwargs.get("params", {})
        offset = int(params.get("offset", 0))
        seen_offsets.append(offset)
        return _resp(jobs[offset : offset + 2])

    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=fake_get):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert seen_offsets == [0, 2, 3]  # pages until an empty page
    assert result["pinned"] == 3
    assert result["truncated"] == 0


@pytest.mark.unit
def test_sweep_truncated_listing_skips_unpin(state_path, sweeper, monkeypatch):
    """#1489: when the page cap is hit the inspected set may be incomplete —
    reclamation is deferred rather than unpinning live rentals."""
    monkeypatch.setattr(ipfs_pinning_sweeper, "_JOB_PAGE_SIZE", 1)
    monkeypatch.setattr(ipfs_pinning_sweeper, "_JOB_MAX_PAGES", 2)
    jobs = [_job(f"job-{i}", state="RUNNING") for i in range(5)]
    ipfs_pinning_sweeper._save_state(state_path, {"orphan-1": {"cid": "Qmorphan", "size": 1, "pinned_at": "t"}})

    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response(jobs)):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["truncated"] == 1
    assert result["unpinned"] == 0
    # The tracked pin survives for a later, complete sweep.
    assert "orphan-1" in ipfs_pinning_sweeper._load_state(state_path)


@pytest.mark.unit
def test_unpin_verifies_job_before_removing_pin(state_path, sweeper):
    """#1489: a tracked job missing from the listing is unpinned only after a
    direct lookup confirms it terminal or gone — an active job keeps its pin."""
    ipfs_pinning_sweeper._save_state(state_path, {"job-live": {"cid": "Qmlive", "size": 1, "pinned_at": "t"}})
    # The list endpoint returns nothing, but the per-job lookup says RUNNING.
    live = _job("job-live", state="RUNNING", cid="Qmlive")

    def fake_get(url, **kwargs):
        if "/v1/market/jobs/" in url:
            return _resp(live)
        return _resp([])

    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=fake_get):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["unpinned"] == 0
    assert result["deferred"] == 1
    assert "job-live" in ipfs_pinning_sweeper._load_state(state_path)


@pytest.mark.unit
def test_unpin_proceeds_when_job_lookup_fails_closed(state_path, sweeper):
    """An unverifiable lookup (HTTP error) defers the unpin — fail closed."""
    ipfs_pinning_sweeper._save_state(state_path, {"job-x": {"cid": "Qmx", "size": 1, "pinned_at": "t"}})

    def fake_get(url, **kwargs):
        if "/v1/market/jobs/" in url:
            return _resp({}, status=500)
        return _resp([])

    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=fake_get):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert result["unpinned"] == 0
    assert result["deferred"] == 1
    assert "job-x" in ipfs_pinning_sweeper._load_state(state_path)


# --- IPFS-PIN-LEAK-1 (#1687): crash-window reconcile + atomic state ---------


def _age_untracked(path: Path, cid: str) -> None:
    import json

    state = json.loads(path.read_text())
    state["_untracked"][cid] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(state))


@pytest.mark.unit
def test_reconcile_records_then_reclaims_untracked_pin(state_path, sweeper, monkeypatch):
    """A daemon pin known to the market but absent from state is reclaimed
    only after the grace window — the pin/add→save crash window."""
    terminal = _job("job-old", state="RELEASED", cid=CID)
    monkeypatch.setattr(ipfs_pinning_sweeper, "_daemon_pins", lambda: {CID})
    get_patch = patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([terminal]))
    get_patch.start()
    try:
        first = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
        assert first["reclaimed"] == 0
        state = ipfs_pinning_sweeper._load_state(state_path)
        assert CID in state.get("_untracked", {})
        assert not any(u.endswith("/api/v0/pin/rm") for u in sweeper["ipfs"])

        _age_untracked(state_path, CID)
        second = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    finally:
        get_patch.stop()
    assert second["reclaimed"] == 1
    assert any(u.endswith("/api/v0/pin/rm") for u in sweeper["ipfs"])
    state = ipfs_pinning_sweeper._load_state(state_path)
    assert CID not in state.get("_untracked", {})


@pytest.mark.unit
def test_reconcile_leaves_unknown_and_active_pins_alone(state_path, sweeper, monkeypatch):
    """Pins the market never listed, and CIDs of active jobs, are never
    touched — manual pins on the provider daemon stay safe."""
    other = "Qm" + "a" * 44
    active = _job("job-live", state="RUNNING", cid=other)
    monkeypatch.setattr(ipfs_pinning_sweeper, "_daemon_pins", lambda: {CID, other})
    get_patch = patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([active]))
    get_patch.start()
    try:
        # CID is pinned on the daemon but unknown to the market listing;
        # `other` belongs to the active job and is tracked in state.
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    finally:
        get_patch.stop()
    assert result["reclaimed"] == 0
    assert not any(u.endswith("/api/v0/pin/rm") for u in sweeper["ipfs"])


@pytest.mark.unit
def test_save_state_is_atomic(state_path):
    import json

    ipfs_pinning_sweeper._save_state(state_path, {"job-1": {"cid": CID}})
    assert json.loads(state_path.read_text()) == {"job-1": {"cid": CID}}
    assert not state_path.with_name(state_path.name + ".tmp").exists()


@pytest.mark.unit
def test_pin_cid_rejects_ipfs_path_args(sweeper):
    """Buyer-influenced payload.cid must not become a Kubo path arg (#1582)."""
    assert ipfs_pinning_sweeper._pin_cid("ipfs/" + CID) is False
    assert ipfs_pinning_sweeper._unpin_cid("/ipfs/" + CID) is False
    assert ipfs_pinning_sweeper._object_size("a/b") is None
    assert not any(u.endswith(("/pin/add", "/pin/rm", "/dag/stat")) for u in sweeper["ipfs"])


def _uvarint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _cidv0_for_block(data: bytes) -> tuple[str, bytes]:
    multihash = b"\x12\x20" + hashlib.sha256(data).digest()
    return base58.b58encode(multihash).decode(), multihash


def _car_for_block(data: bytes) -> tuple[str, bytes]:
    """Small but structurally valid single-block CARv1 for sweeper tests."""
    cid_text, cid_bytes = _cidv0_for_block(data)
    # DAG-CBOR: {"roots": [<cid bytes>], "version": 1}. The sweeper verifies
    # block hashes and root presence itself; this header keeps the fixture
    # realistic for a real Kubo import shape.
    header = b"\x82" + b"\x65roots" + b"\x81" + bytes([0x58, len(cid_bytes)]) + cid_bytes + b"\x67version" + b"\x01"
    section = cid_bytes + data
    car = _uvarint(len(header)) + header + _uvarint(len(section)) + section
    return cid_text, car


def _cidv1_raw_for_block(data: bytes) -> tuple[str, bytes]:
    multihash = b"\x12\x20" + hashlib.sha256(data).digest()
    cid_bytes = b"\x01\x55" + multihash  # CIDv1, raw codec
    encoded = base64.b32encode(cid_bytes).decode().lower().rstrip("=")
    return "b" + encoded, cid_bytes


# --- #2968: hub CAR fallback + persistent delivery-error surfacing ---------


@pytest.mark.unit
def test_direct_pin_failure_imports_market_car_and_confirms(state_path, sweeper):
    """When the direct swarm leg cannot pin, the sweeper downloads the signed
    market CAR proxy stream, imports it into the local daemon, pins the CID,
    and confirms delivery."""
    payload_block = b"rental payload bytes"
    car_cid, car_bytes = _car_for_block(payload_block)
    job = _job("job-car", state="QUEUED", cid=car_cid)
    calls = {"pin_add": 0, "car_get": [], "dag_import": 0}

    def fake_post(url, **kwargs):
        if url.endswith("/api/v0/pin/add"):
            calls["pin_add"] += 1
            if calls["pin_add"] == 1:
                import requests

                raise requests.ReadTimeout("direct bitswap timeout")
            return _resp({})
        if url.endswith("/api/v0/dag/import"):
            calls["dag_import"] += 1
            assert kwargs.get("files")
            assert kwargs.get("params") == {"pin-roots": "false"}
            return _resp({})
        if url.endswith("/api/v0/dag/stat"):
            return _resp({}, text='{"TotalSize": 1000}')
        if "/v1/market/jobs/" in url and url.endswith("/pin-confirm"):
            return _resp({})
        return _resp({})

    car = _resp({})
    car.iter_content = lambda *a, **k: iter([car_bytes])

    def fake_get(url, **kwargs):
        if url.endswith("/content-car"):
            calls["car_get"].append((url, kwargs.get("params", {})))
            return car
        return _jobs_response([job])(url, **kwargs)

    with (
        patch.object(ipfs_pinning_sweeper.requests, "post", side_effect=fake_post),
        patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=fake_get),
    ):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)

    assert result["pinned"] == 1
    assert result["confirmed"] == 1
    assert calls["dag_import"] == 1
    assert calls["pin_add"] == 2
    assert calls["car_get"]
    assert calls["car_get"][0][1]["signer_address"] == PROVIDER


@pytest.mark.unit
def test_tampered_market_car_never_reaches_dag_import(state_path, sweeper):
    """The market proxy is transport, not authority: a hash-mismatched CAR is
    rejected locally before any byte is offered to the provider blockstore."""
    payload_block = b"rental payload bytes"
    car_cid, car_bytes = _car_for_block(payload_block)
    tampered = bytearray(car_bytes)
    tampered[-1] ^= 0x01
    job = _job("job-tampered-car", state="QUEUED", cid=car_cid)
    calls = {"dag_import": 0}

    import requests

    def fake_post(url, **kwargs):
        if url.endswith("/api/v0/pin/add"):
            raise requests.ReadTimeout("direct bitswap timeout")
        if url.endswith("/api/v0/dag/import"):
            calls["dag_import"] += 1
            return _resp({})
        if url.endswith("/api/v0/dag/stat"):
            return _resp({}, text='{"TotalSize": 1000}')
        return _resp({})

    car = _resp({})
    car.iter_content = lambda *a, **k: iter([bytes(tampered)])

    def fake_get(url, **kwargs):
        if url.endswith("/content-car"):
            return car
        return _jobs_response([job])(url, **kwargs)

    with (
        patch.object(ipfs_pinning_sweeper.requests, "post", side_effect=fake_post),
        patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=fake_get),
    ):
        result = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)

    assert result["errors"] == 1
    assert result["pinned"] == 0
    assert calls["dag_import"] == 0


@pytest.mark.unit
def test_persistent_pin_failure_reports_delivery_error_once(state_path, sweeper, monkeypatch):
    """Transient failure stays local; the configured consecutive-failure
    threshold writes a signed pin-error report once, and a later success
    clears the bookkeeping."""
    monkeypatch.setenv("IPFS_HOSTING_FAILURE_REPORT_THRESHOLD", "2")
    job = _job("job-fail", state="QUEUED")
    reports = []

    monkeypatch.setattr(ipfs_pinning_sweeper, "_pin_with_market_fallback", lambda *a, **k: (False, "both paths failed"))
    monkeypatch.setattr(
        ipfs_pinning_sweeper,
        "_report_pin_error",
        lambda market_url, job_id, cid, provider, error: reports.append((job_id, cid, provider, error)) or True,
    )
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([job])):
        first = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
        assert reports == []
        second = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
        assert reports == [("job-fail", CID, PROVIDER, "both paths failed")]
        third = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)

    assert first["errors"] == second["errors"] == third["errors"] == 1
    assert reports == [("job-fail", CID, PROVIDER, "both paths failed")]
    state = ipfs_pinning_sweeper._load_state(state_path)
    assert state["_delivery_failures"]["job-fail"]["reported"] is True

    monkeypatch.setattr(ipfs_pinning_sweeper, "_pin_with_market_fallback", lambda *a, **k: (True, None))
    with patch.object(ipfs_pinning_sweeper.requests, "get", side_effect=_jobs_response([job])):
        recovered = ipfs_pinning_sweeper.sweep_once(PROVIDER, state_path)
    assert recovered["pinned"] == 1
    assert "_delivery_failures" not in ipfs_pinning_sweeper._load_state(state_path)


@pytest.mark.unit
def test_car_integrity_validator_accepts_valid_car(tmp_path):
    _cid, car_bytes = _car_for_block(b"verified rental block")
    car_path = tmp_path / "valid.car"
    car_path.write_bytes(car_bytes)
    with car_path.open("rb") as car_file:
        ipfs_pinning_sweeper._validate_car_integrity(car_file, _cid, len(car_bytes) + 1024)


@pytest.mark.unit
def test_car_integrity_validator_rejects_tampered_block_before_import(tmp_path):
    cid, car_bytes = _car_for_block(b"verified rental block")
    tampered = bytearray(car_bytes)
    tampered[-1] ^= 0x01
    car_path = tmp_path / "tampered.car"
    car_path.write_bytes(bytes(tampered))
    with car_path.open("rb") as car_file, pytest.raises(ValueError, match="hash does not match"):
        ipfs_pinning_sweeper._validate_car_integrity(car_file, cid, len(car_bytes) + 1024)


@pytest.mark.unit
def test_car_integrity_validator_rejects_missing_job_root(tmp_path):
    cid, car_bytes = _car_for_block(b"verified rental block")
    other_cid, _other_car = _car_for_block(b"different block")
    car_path = tmp_path / "wrong-root.car"
    car_path.write_bytes(car_bytes)
    with car_path.open("rb") as car_file, pytest.raises(ValueError, match="does not contain the job CID root"):
        ipfs_pinning_sweeper._validate_car_integrity(car_file, other_cid, len(car_bytes) + 1024)


@pytest.mark.unit
def test_car_integrity_validator_accepts_base32_cidv1(tmp_path):
    data = b"cidv1 raw rental block"
    cid, cid_bytes = _cidv1_raw_for_block(data)
    header = b"header"
    section = cid_bytes + data
    car = _uvarint(len(header)) + header + _uvarint(len(section)) + section
    car_path = tmp_path / "cidv1.car"
    car_path.write_bytes(car)
    with car_path.open("rb") as car_file:
        ipfs_pinning_sweeper._validate_car_integrity(car_file, cid, len(car) + 1024)


@pytest.mark.unit
def test_fallback_error_report_redacts_signed_request_urls():
    import requests

    response = requests.Response()
    response.status_code = 403
    response.url = "http://market.internal/v1/market/jobs/job/content-car?signer_address=0xProvider&signature=secret-sig"
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        detail = ipfs_pinning_sweeper._safe_exception_detail(error)
    else:
        raise AssertionError("raise_for_status did not raise")
    assert "signature" not in detail
    assert "market.internal" not in detail
    assert "<url>" in detail
