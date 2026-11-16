"""#2143 — a 67 MB slashing_events_json must not stall the consensus RPC routes.

``/rpc/consensus/status`` and ``/validators`` called ``load_state()`` per request, which parsed
the whole slashing-history column (67 MB on hub, multi-second). They only need validators, view
and epoch: ``load_state(slashing=False)`` never reads the column. ``/slashing-history`` still
needs it, so the parsed history is cached by the row fingerprint and re-parsed only after a write.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA

from .test_validator_deactivation_1198 import _chain_db, _consensus

V1 = "0x" + "11" * 20


def _persisted_chain(n_events: int = 6):
    chain_id = f"blob-2143-{uuid.uuid4().hex[:8]}"
    _chain_db(chain_id)
    c = _consensus(chain_id, V1)
    mgr = c._slashing_manager
    for i in range(n_events):
        ev = mgr.detect_double_sign(V1, f"0x{i:064x}", f"0x{i + 10**6:064x}", 100 + i)
        assert ev is not None
        mgr.slashing_events.append(ev)
    assert c.save_state() is True
    return chain_id


@pytest.fixture
def parse_counter(monkeypatch):
    calls = []
    real = MultiValidatorPoA._parse_slashing_events

    def counting(records):
        calls.append(len(records))
        return real(records)

    monkeypatch.setattr(MultiValidatorPoA, "_parse_slashing_events", staticmethod(counting))
    return calls


def test_slashing_false_never_parses_the_history_blob(parse_counter):
    chain_id = _persisted_chain()
    fresh = MultiValidatorPoA(chain_id, load_state=False)
    parse_counter.clear()
    assert fresh.load_state(slashing=False) is True
    assert parse_counter == []  # the blob was neither read nor parsed
    assert fresh._slashing_manager.slashing_events == []  # in-memory history untouched
    assert V1 in set(fresh.validators)  # validators still restored


def test_unchanged_row_is_parsed_once(parse_counter):
    chain_id = _persisted_chain()
    fresh = MultiValidatorPoA(chain_id, load_state=False)
    parse_counter.clear()
    assert fresh.load_state() is True
    assert fresh.load_state() is True
    assert fresh.load_state() is True
    assert len(parse_counter) == 1
    assert len(fresh._slashing_manager.slashing_events) == 6


def test_a_write_invalidates_the_cache(parse_counter):
    chain_id = _persisted_chain()
    reader = MultiValidatorPoA(chain_id, load_state=False)
    reader.load_state()
    writer = MultiValidatorPoA(chain_id)
    ev = writer._slashing_manager.detect_double_sign(V1, "0x" + "ab" * 32, "0x" + "cd" * 32, 900)
    assert ev is not None
    writer._slashing_manager.slashing_events.append(ev)
    assert writer.save_state() is True
    parse_counter.clear()
    reader.load_state()
    assert len(parse_counter) == 1
    assert len(reader._slashing_manager.slashing_events) == 7


def test_cache_hit_hands_out_an_independent_list():
    chain_id = _persisted_chain()
    reader = MultiValidatorPoA(chain_id, load_state=False)
    reader.load_state()
    reader._slashing_manager.slashing_events.clear()  # a caller mutating its list
    reader.load_state()
    assert len(reader._slashing_manager.slashing_events) == 6


def test_status_and_validators_routes_skip_the_slashing_blob(monkeypatch):
    from unittest.mock import MagicMock, patch

    from aitbc_chain.config import settings
    from aitbc_chain.rpc.routers.consensus import consensus_status_route, consensus_validators_route

    validator = MagicMock()
    validator.is_active = True
    validator.role.value = "validator"
    validator.stake = Decimal(1)
    validators = {f"0x{i}": validator for i in range(4)}
    consensus = MagicMock()
    consensus.validators = validators
    consensus.get_consensus_participants.return_value = list(validators)
    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", True)
    monkeypatch.setattr(settings, "validator_set", ",".join(validators))
    monkeypatch.setattr(settings, "pbft_consensus_enabled", False)
    monkeypatch.setattr(settings, "chain_id", "ait-test")
    with patch("aitbc_chain.consensus.multi_validator_poa.get_consensus", return_value=consensus):
        consensus_status_route(request=None)
        consensus_validators_route(request=None)
    assert consensus.load_state.call_args_list == [((), {"slashing": False}), ((), {"slashing": False})]
