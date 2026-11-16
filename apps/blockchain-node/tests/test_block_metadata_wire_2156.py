"""#2156 — ``block_metadata`` is a JSON string on the wire; a dict must not crash importers.

The PBFT view-change re-seal gossiped ``block_metadata`` as a dict. Every importer's
``json.loads(block_metadata)`` raised ``TypeError`` ("must be str, bytes or bytearray, not
dict"), caught only as ``JSONDecodeError``, so followers dropped the block and stalled
(Phase-A soak: node0/hub1 stuck at 29548 while validators reached 29556+).
"""

import json
from types import SimpleNamespace

import pytest

from aitbc_chain.sync_block_import import BlockImportMixin
from aitbc_chain.sync_validator import ProposerSignatureValidator

PROPOSER = "0x" + "aa" * 20
SET = json.dumps([{"address": PROPOSER}, {"address": "0x" + "cc" * 20}])
BLOCK = {"height": 5, "hash": "0x" + "ab" * 32, "parent_hash": "0x" + "00" * 32, "proposer": PROPOSER}
META = {"attestations": [], "rejected_txs": [{"sender": "0xabc", "nonce": 1}]}


@pytest.fixture
def _armed(monkeypatch):
    monkeypatch.setattr("aitbc_chain.config.settings.multi_validator_consensus_enabled", True)
    monkeypatch.setattr("aitbc_chain.config.settings.validator_set", SET)
    monkeypatch.setattr("aitbc_chain.config.settings.multi_validator_min_attestations", 1)


def test_normalize_serialises_a_dict_and_never_mutates_the_caller():
    original = {**BLOCK, "block_metadata": dict(META)}
    out = BlockImportMixin._normalize_block_metadata(original)
    assert isinstance(out["block_metadata"], str)
    assert json.loads(out["block_metadata"]) == META
    assert isinstance(original["block_metadata"], dict)  # caller's message untouched


@pytest.mark.parametrize("raw", [None, "", json.dumps(META)])
def test_normalize_leaves_strings_and_absent_metadata_alone(raw):
    block = {**BLOCK, "block_metadata": raw}
    assert BlockImportMixin._normalize_block_metadata(block) is block


def test_the_raw_dict_is_what_crashed_the_legacy_validator(_armed):
    """Documents the soak failure: un-normalised dict metadata raised TypeError."""
    v = ProposerSignatureValidator([])
    with pytest.raises(TypeError):
        v._validate_attestations({**BLOCK, "block_metadata": dict(META)})


def test_normalised_dict_metadata_gets_a_clean_verdict(_armed):
    v = ProposerSignatureValidator([])
    block = BlockImportMixin._normalize_block_metadata({**BLOCK, "block_metadata": dict(META)})
    ok, reason = v._validate_attestations(block)
    assert ok is False and "Insufficient attestations" in reason  # a verdict, not a crash


def test_import_block_normalises_before_any_validator_sees_the_message():
    seen = {}

    def _capture(block_data):
        seen.update(block_data)
        return False, "stop here"

    stub = SimpleNamespace(
        _validate_signatures=True,
        _validator=SimpleNamespace(validate_block_signature=_capture),
        _normalize_block_metadata=BlockImportMixin._normalize_block_metadata,
    )
    try:
        BlockImportMixin.import_block(stub, {**BLOCK, "block_metadata": dict(META)})  # type: ignore[arg-type]
    except AttributeError:
        pass  # the stub has no rejection plumbing; only what the validator saw matters
    assert isinstance(seen["block_metadata"], str)
    assert json.loads(seen["block_metadata"]) == META
