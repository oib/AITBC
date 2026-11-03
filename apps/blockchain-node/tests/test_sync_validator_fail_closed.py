"""#842: multi-validator consensus fails closed, not silently open.

Three slip-shaped gaps are pinned refuse-now:
- a proposer outside the configured validator set no longer skips the check;
- a VALIDATOR_SET that doesn't parse logs and reads as empty (never 'everyone');
- an empty validator set counts nobody toward quorum instead of skipping the
  membership filter.
"""

import json
from unittest.mock import patch

import pytest

from aitbc_chain.sync_validator import ProposerSignatureValidator

PROPOSER = "0x" + "aa" * 20
OUTSIDER = "0x" + "bb" * 20
VALIDATOR = "0x" + "cc" * 20

SET = json.dumps([{"address": VALIDATOR}, {"address": PROPOSER}])
BLOCK = {
    "height": 5,
    "hash": "0x" + "ab" * 32,
    "parent_hash": "0x" + "00" * 32,
    "timestamp": "2026-01-01T00:00:00Z",
    "proposer": PROPOSER,
    "signature": "0xsig",
}


@pytest.fixture(autouse=True)
def _good_sig():
    with patch("aitbc.crypto.consensus_signing.verify_block_signature", return_value=True):
        yield


def _on(monkeypatch, validator_set=SET, min_att=1):
    monkeypatch.setattr("aitbc_chain.config.settings.multi_validator_consensus_enabled", True)
    monkeypatch.setattr("aitbc_chain.config.settings.validator_set", validator_set)
    monkeypatch.setattr("aitbc_chain.config.settings.multi_validator_min_attestations", min_att)
    monkeypatch.setattr("aitbc_chain.config.settings.bridge_block_signature_required", True)


def test_proposer_outside_the_set_is_refused(monkeypatch):
    _on(monkeypatch)
    v = ProposerSignatureValidator([])
    ok, reason = v.validate_block_signature({**BLOCK, "proposer": OUTSIDER})
    assert not ok and "validator set" in reason


def test_member_proposer_with_short_certificate_is_refused(monkeypatch):
    _on(monkeypatch)
    v = ProposerSignatureValidator([])
    ok, reason = v.validate_block_signature(dict(BLOCK))  # no block_metadata at all
    assert not ok and "metadata" in reason


def test_unparseable_validator_set_refuses_everyone(monkeypatch):
    _on(monkeypatch, validator_set="{not json")
    v = ProposerSignatureValidator([])
    # member proposer passes the trusted-signature gate but the set is empty,
    # so no attestation can count — the check cannot vanish.
    ok, reason = v.validate_block_signature(dict(BLOCK))
    assert not ok


def test_empty_validator_set_counts_nobody(monkeypatch):
    _on(monkeypatch, validator_set="[]")
    v = ProposerSignatureValidator([])
    ok, reason = v.validate_block_signature(dict(BLOCK))
    assert not ok
