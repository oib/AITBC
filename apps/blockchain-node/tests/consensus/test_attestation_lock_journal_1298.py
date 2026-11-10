"""#1298 attestation-lock journal — durable restart reseed (design v2.5/v2.6).

The non-round-lock attestation path now persists every signing to
``attestation_round_locks.json`` (kind="attestation" records) BEFORE the
signature is released, prunes by wall age at 2x the lock-lapse window
(260s at defaults), and refuses to sign when persistence fails. On load the
records reseed ``_attested`` and ``_signed_once`` so a restart cannot forget
a lock it already took.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry

PARENT_TS = datetime(2026, 1, 1, tzinfo=UTC)
ROUND_SECONDS = 60
# lapse = round(60) + header_max_age(60) + future_skew(10) = 130s → prune 260s
LAPSE_SECONDS = 130.0
PRUNE_SECONDS = 2 * LAPSE_SECONDS


@pytest.fixture(autouse=True)
def _journal_settings(monkeypatch):
    monkeypatch.setattr(settings, "attestation_round_lock_enabled", False)
    monkeypatch.setattr(settings, "consensus_proposer_round_seconds", ROUND_SECONDS)
    monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 60.0)
    monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 10.0)
    monkeypatch.setattr(settings, "attestation_lock_enabled", True)
    monkeypatch.setattr(settings, "consensus_require_signed_attest_request", False)
    monkeypatch.setattr(settings, "consensus_enforce_proposer_schedule", False)
    monkeypatch.setattr(settings, "consensus_domain_separation_height", None)
    monkeypatch.setattr(settings, "chain_id", "test-chain")
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _keys() -> tuple[str, str, str, str]:
    from eth_keys import keys

    our_key = "0x" + "11" * 32
    proposer_key = "0x" + "22" * 32
    our_addr = keys.PrivateKey(bytes.fromhex(our_key[2:])).public_key.to_checksum_address()
    proposer_addr = keys.PrivateKey(bytes.fromhex(proposer_key[2:])).public_key.to_checksum_address()
    return our_addr, our_key, proposer_addr, proposer_key


def _header(height: int, block_hash: str, proposer: str, chain_id: str = "test-chain") -> dict:
    return {
        "header": {
            "chain_id": chain_id,
            "height": height,
            "hash": block_hash,
            "parent_hash": "0xparent",
            "proposer": proposer,
            "state_root": "0xroot",
            "bridge_state_root": "",
        },
        "timestamp": time.time(),
    }


class _StubBroker:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, message: dict):
        self.published.append((topic, message))


def _service(
    monkeypatch, our_addr: str, our_key: str, proposer_addr: str, tmp_path, chain_id: str = "test-chain"
) -> tuple[RemoteAttestationService, _StubBroker]:
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": our_addr}, {"address": proposer_addr}]),
    )
    broker = _StubBroker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    svc = RemoteAttestationService(chain_id, {our_addr: our_key})
    svc._round_locks_path = tmp_path / "locks.json"
    return svc, broker


def _attestation_records(svc: RemoteAttestationService) -> list[dict]:
    data = json.loads(svc._round_locks_path.read_text())
    return [r for r in data["records"] if r.get("kind") == "attestation"]


class TestJournalWrite:
    @pytest.mark.asyncio
    async def test_signing_persists_attestation_record(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))

        assert len(broker.published) == 1
        records = _attestation_records(svc)
        assert len(records) == 1
        rec = records[0]
        assert rec["h"] == 100
        assert rec["hash"] == "0xaaaa"
        assert rec["proposer"] == proposer_addr
        assert abs(time.time() - float(rec["signed_wall"])) < 30
        # No parent timestamp stubbed → derived round underivable → null,
        # and the domain tag stays null below the (unset) activation height.
        assert rec["derived_round"] is None
        assert rec["signature_domain"] is None
        assert "r" not in rec  # old builds must skip this record, not misread it

    @pytest.mark.asyncio
    async def test_domain_tag_recorded_at_activation(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        monkeypatch.setattr(settings, "consensus_domain_separation_height", 1)
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        # #1298 T7a/T14: at/above the activation height the request must
        # declare the derived round and carry the signed block timestamp it
        # derives from — round authentication is unconditional post-H.
        monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
        monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 3600.0)
        svc._parent_timestamp = lambda p: PARENT_TS if p == "0xparent" else None  # type: ignore[method-assign]
        req = _header(100, "0xaaaa", proposer_addr)
        req["header"]["timestamp"] = (PARENT_TS + timedelta(seconds=61)).isoformat()
        req["header"]["round"] = 1

        await svc._handle_request(req)

        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION

        rec = _attestation_records(svc)[0]
        assert rec["signature_domain"] == DOMAIN_BLOCK_ATTESTATION

    @pytest.mark.asyncio
    async def test_derived_round_persisted(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        # The fixed historical timestamps would trip the #1245 freshness
        # bound — this test covers round derivation, not freshness.
        monkeypatch.setattr(settings, "attestation_header_max_age_seconds", 0.0)
        monkeypatch.setattr(settings, "attestation_header_future_skew_seconds", 3600.0)
        # Parent resolves; block ts = parent + 130s → round 2 at 60s rounds.
        svc._parent_timestamp = lambda p: PARENT_TS if p == "0xparent" else None  # type: ignore[method-assign]
        req = _header(100, "0xaaaa", proposer_addr)
        req["header"]["timestamp"] = (PARENT_TS + timedelta(seconds=130)).isoformat()

        await svc._handle_request(req)

        assert _attestation_records(svc)[0]["derived_round"] == 2

    @pytest.mark.asyncio
    async def test_duplicate_request_does_not_rewrite_journal(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        first_mtime = svc._round_locks_path.stat().st_mtime_ns
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))

        assert len(broker.published) == 2  # idempotent re-publish still works
        assert len(_attestation_records(svc)) == 1
        assert svc._round_locks_path.stat().st_mtime_ns == first_mtime


class TestRestartReseed:
    @pytest.mark.asyncio
    async def test_lock_and_signed_once_survive_restart(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))

        # Fresh service on the same journal = restart.
        svc2, broker2 = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        lock = svc2.attestation_lock(100, float(ROUND_SECONDS))
        assert lock is not None and lock[0] == "0xaaaa"
        assert svc2._signed_once_contains(100, "0xaaaa", None)

        # A rival at the locked height is still refused after restart.
        await svc2._handle_request(_header(100, "0xbbbb", proposer_addr))
        assert not broker2.published
        # The same hash re-publishes idempotently.
        await svc2._handle_request(_header(100, "0xaaaa", proposer_addr))
        assert len(broker2.published) == 1

    @pytest.mark.asyncio
    async def test_resign_after_lapse_still_refused_after_restart(self, monkeypatch, tmp_path):
        """#1245 anti-replay survives restart: a (height, hash) signed before
        the lock lapsed must not be re-armable by rebooting."""
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))

        # Age the journal record past the 60s lock window but inside the
        # 260s prune horizon, then "restart".
        path = svc._round_locks_path
        data = json.loads(path.read_text())
        for rec in data["records"]:
            if rec.get("kind") == "attestation":
                rec["signed_wall"] = time.time() - 120.0
        path.write_text(json.dumps(data))

        svc2, broker2 = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        assert svc2.attestation_lock(100, float(ROUND_SECONDS)) is None  # lapsed
        await svc2._handle_request(_header(100, "0xaaaa", proposer_addr))
        assert not broker2.published
        assert metrics_registry._counters.get("attestation_refused_resign_after_expiry_total", 0.0) == 1.0

    @pytest.mark.asyncio
    async def test_latest_signing_wins_per_height(self, monkeypatch, tmp_path):
        """Two hashes at one height (post-lapse rival): the newest journal
        record reseeds ``_attested``; both hashes reseed ``_signed_once``."""
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        # Lapse the in-memory lock, then sign a rival (post-lapse is legal).
        svc._attested[100] = {None: ("0xaaaa", proposer_addr, time.monotonic() - 3600)}
        await svc._handle_request(_header(100, "0xbbbb", proposer_addr))

        svc2, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)
        svc2._ensure_round_locks_loaded()  # lazy journal load
        assert svc2._attested[100][None][0] == "0xbbbb"
        assert svc2._signed_once[100] == {None: {"0xaaaa", "0xbbbb"}}


class TestWallAgePrune:
    def _write_journal(self, path, records):
        path.write_text(json.dumps({"version": 1, "chain_id": "test-chain", "records": records}))

    def test_boundary_259s_kept_261s_dropped(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        now = time.time()
        self._write_journal(
            tmp_path / "locks.json",
            [
                {
                    "kind": "attestation",
                    "h": 100,
                    "hash": "0xfresh",
                    "proposer": proposer_addr,
                    "signed_wall": now - (PRUNE_SECONDS - 1),
                },
                {
                    "kind": "attestation",
                    "h": 101,
                    "hash": "0xstale",
                    "proposer": proposer_addr,
                    "signed_wall": now - (PRUNE_SECONDS + 1),
                },
            ],
        )
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        svc._ensure_round_locks_loaded()

        assert (100, "0xfresh", None) in svc._attested_lock_records
        assert (101, "0xstale", None) not in svc._attested_lock_records
        assert 100 in svc._attested and 101 not in svc._attested
        assert svc._signed_once_contains(100, "0xfresh", None)
        assert not svc._signed_once_contains(101, "0xstale", None)

    def test_legacy_record_without_round_or_domain_reseeds(self, monkeypatch, tmp_path):
        """T21: minimal attestation record (no derived_round/signature_domain)
        still reseeds conservative-full-coverage."""
        our_addr, our_key, proposer_addr, _ = _keys()
        self._write_journal(
            tmp_path / "locks.json",
            [
                {
                    "kind": "attestation",
                    "h": 100,
                    "hash": "0xaaaa",
                    "proposer": proposer_addr,
                    "signed_wall": time.time(),
                }
            ],
        )
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        lock = svc.attestation_lock(100, float(ROUND_SECONDS))
        assert lock is not None and lock[0] == "0xaaaa"
        assert svc._signed_once_contains(100, "0xaaaa", None)

    def test_round_lock_records_still_load_alongside(self, monkeypatch, tmp_path):
        """Mixed file: kind-less records stay round locks; kind=attestation
        records reseed the legacy lock — neither pollutes the other."""
        our_addr, our_key, proposer_addr, _ = _keys()
        now = time.time()
        self._write_journal(
            tmp_path / "locks.json",
            [
                {"h": 100, "r": 0, "hash": "0xrl", "proposer": proposer_addr, "signed_wall": now, "request_seen_wall": None},
                {"kind": "attestation", "h": 100, "hash": "0xal", "proposer": proposer_addr, "signed_wall": now},
            ],
        )
        svc, _ = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        svc._ensure_round_locks_loaded()

        assert (100, 0, None) in svc._round_locks
        assert svc._round_locks[(100, 0, None)].block_hash == "0xrl"
        assert svc._attested[100][None][0] == "0xal"


class TestRefuseToSign:
    @pytest.mark.asyncio
    async def test_persist_failure_refuses_signature(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        def _boom(self):
            raise OSError("disk full")

        monkeypatch.setattr(RemoteAttestationService, "_persist_round_locks", _boom)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))

        assert not broker.published  # fail-closed: no signature released
        assert metrics_registry._counters.get("attestation_lock_persist_failure_total", 0.0) == 1.0
        # The in-memory record exists but nothing was signed — a later
        # request retries the persist rather than treating it as signed.
        assert svc.attestation_lock(100, float(ROUND_SECONDS)) is None

    @pytest.mark.asyncio
    async def test_persist_failure_recovers_on_next_request(self, monkeypatch, tmp_path):
        our_addr, our_key, proposer_addr, _ = _keys()
        svc, broker = _service(monkeypatch, our_addr, our_key, proposer_addr, tmp_path)

        calls = {"n": 0}
        real_persist = RemoteAttestationService._persist_round_locks

        def _flaky(self):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("transient")
            return real_persist(self)

        monkeypatch.setattr(RemoteAttestationService, "_persist_round_locks", _flaky)

        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        assert not broker.published
        await svc._handle_request(_header(100, "0xaaaa", proposer_addr))
        assert len(broker.published) == 1
