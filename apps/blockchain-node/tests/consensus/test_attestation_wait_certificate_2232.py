"""#2232 (c-light): bounded attestation wait when the PBFT certificate covers the minimum."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from aitbc_chain.consensus import vote_fetch
from aitbc_chain.consensus.poa_attest import _AttestMixin
from aitbc_chain.config import settings


class _Log:
    def __init__(self) -> None:
        self.infos: list[str] = []

    def info(self, msg, *args, **_kw) -> None:
        self.infos.append(msg % args)


def _stub():
    ns = SimpleNamespace(_logger=_Log())
    ns._cap = lambda *a: _AttestMixin._cap_wait_when_certified(ns, *a)
    return ns


@pytest.fixture
def bound(monkeypatch):
    def _set(value):
        monkeypatch.setattr(settings, "attestation_wait_when_certificate_covers_seconds", value, raising=False)

    return _set


def test_bound_applies_when_certificate_covers_minimum(bound):
    bound(1.0)
    ns = _stub()
    assert ns._cap(16.0, 2, 3, 100) == 1.0
    assert len(ns._logger.infos) == 1 and "2232" in ns._logger.infos[0]


def test_flag_off_keeps_full_wait(bound):
    bound(None)
    ns = _stub()
    assert ns._cap(16.0, 2, 4, 100) == 16.0
    assert ns._logger.infos == []


def test_short_certificate_keeps_full_wait(bound):
    bound(1.0)
    assert _stub()._cap(16.0, 3, 2, 100) == 16.0


def test_zero_effective_min_untouched(bound):
    bound(1.0)
    assert _stub()._cap(16.0, 0, 4, 100) == 16.0


def test_bound_never_lengthens_the_wait(bound):
    bound(30.0)
    assert _stub()._cap(16.0, 2, 3, 100) == 16.0


def _commits(*senders):
    return [{"message_type": "commit", "sender": s, "block_hash": "0xh"} for s in senders]


def _blk(meta):
    return {"hash": "0xh", "block_metadata": json.dumps(meta)}


def test_rival_sealed_by_certificate_only(monkeypatch):
    monkeypatch.setattr(settings, "multi_validator_min_attestations", 2, raising=False)
    assert vote_fetch._rival_sealed(_blk({"pbft_certificate": _commits("0xa", "0xb", "0xc")}))


def test_rival_certificate_short_or_duplicate_not_sealed(monkeypatch):
    monkeypatch.setattr(settings, "multi_validator_min_attestations", 2, raising=False)
    assert not vote_fetch._rival_sealed(_blk({"pbft_certificate": _commits("0xa")}))
    assert not vote_fetch._rival_sealed(_blk({"pbft_certificate": _commits("0xa", "0xa")}))
    assert not vote_fetch._rival_sealed(_blk({"pbft_certificate": [{"message_type": "prepare", "sender": "0xa"}] * 3}))


def test_rival_attestations_still_seal(monkeypatch):
    monkeypatch.setattr(settings, "multi_validator_min_attestations", 2, raising=False)
    assert vote_fetch._rival_sealed(_blk({"attestations": [{"validator": "0xa"}, {"validator": "0xb"}]}))
    assert not vote_fetch._rival_sealed(_blk({"attestations": [{"validator": "0xa"}]}))
