"""Tests for #2461: dispute file store must not report success on a failed
save, and must preserve a corrupt state file before overwriting it.

Before the fix, ``_save_state`` caught ``OSError`` and only logged, so
every ``@_persisted`` mutation returned ``success: True`` while the state
existed only in that worker's memory. And ``_load_state`` on a corrupt
file logged-and-returned, so the next mutation's save overwrote the
corrupt file with no forensic copy.
"""

from __future__ import annotations

import os


from aitbc_chain.contracts.dispute_resolution import DisputeResolutionContract

PARTY_A = "0xF1C83cd90e4d33F35BE73Dd57CaBa21Ea52D4584"
PARTY_B = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"


def _file_dispute(contract: DisputeResolutionContract) -> dict:
    return contract.file_dispute(
        agreement_id=0,
        respondent=PARTY_B,
        dispute_type="Payment",
        reason="test",
        evidence_hash="0xabc",
        sender_address=PARTY_A,
    )


def test_persist_failure_reports_success_false(tmp_path, monkeypatch):
    """os.replace raising OSError must surface as success: False — the
    mutation lives only in memory and a fresh instance must not see it."""
    state_file = tmp_path / "disputes.json"
    contract = DisputeResolutionContract(state_path=state_file)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)

    result = _file_dispute(contract)

    assert result["success"] is False
    assert "could not be persisted" in result["error"]

    monkeypatch.undo()
    fresh = DisputeResolutionContract(state_path=state_file)
    assert fresh.get_dispute(1)["success"] is False


def test_corrupt_state_file_preserved_before_overwrite(tmp_path):
    """A truncated state file is renamed to *.corrupt-<ts>* on load so the
    next successful save cannot silently destroy the forensic copy."""
    state_file = tmp_path / "disputes.json"
    state_file.write_text('{"dispute_counter": 7, "disputes": {"1": {truncated')

    contract = DisputeResolutionContract(state_path=state_file)

    corrupt_copies = list(tmp_path.glob("disputes.json.corrupt-*"))
    assert len(corrupt_copies) == 1
    assert "truncated" in corrupt_copies[0].read_text()

    result = _file_dispute(contract)
    assert result["success"] is True

    # The live file is valid JSON again and the corrupt copy still exists.
    assert corrupt_copies[0].exists()
    fresh = DisputeResolutionContract(state_path=state_file)
    assert fresh.get_dispute(int(result["dispute_id"]))["success"] is True
