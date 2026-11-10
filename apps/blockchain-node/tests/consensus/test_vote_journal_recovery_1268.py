"""Batch v3 item 16: vote-journal crash / partial-write / recovery edge cases (#1268).

The journal is the durable barrier against double votes, so what it does on a
bad disk matters as much as the happy path. Pinned here (some are
characterisations of today's fail-open behaviour, called out as such):

* a crash BEFORE the atomic rename leaves the previous file intact and a
  stale ``.tmp`` that the next write simply overwrites;
* a failed write rolls the in-memory vote back (no phantom vote) and the file
  on disk is still the previous good one;
* truncated JSON and non-dict payloads degrade to empty and are counted;
* a file with some bad records keeps the good ones;
* an UNREADABLE file fails CLOSED (operator ruling, 10 Nov): no vote is
  recorded, the file is never overwritten, recovery = move aside + restart;
* the valve boundary is inclusive and a non-positive window never opens;
* concurrent writers all land and survive a reload;
* the height hard-cap evicts the oldest heights;
* retract / prune persist failures keep the (safe) entries.
"""

from __future__ import annotations

import json
import os
import threading
from types import SimpleNamespace

import pytest
from aitbc_chain.consensus import vote_journal
from aitbc_chain.consensus.vote_journal import (
    KIND_ATTEST,
    VoteJournal,
    VoteJournalError,
    valve_open,
)
from aitbc_chain.metrics import metrics_registry

CHAIN = "test-chain"
T0 = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


def _rows(path) -> list[dict]:
    return json.loads(path.read_text())["votes"]


def test_crash_before_rename_keeps_previous_file_and_rolls_back_memory(tmp_path, monkeypatch):
    path = tmp_path / "vj.json"
    j = VoteJournal(CHAIN, path)
    j.record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0)
    good = path.read_text()

    real_replace = type(path).replace

    def crash(self, target):
        raise OSError("power cut before rename")

    monkeypatch.setattr(type(path), "replace", crash)
    with pytest.raises(VoteJournalError):
        j.record(2, "0xv", "0xbbbb", KIND_ATTEST, now=T0)
    monkeypatch.setattr(type(path), "replace", real_replace)

    assert path.read_text() == good  # the previous good file is untouched
    assert j.votes_at(2, "0xv") == []  # no phantom vote in memory
    assert (tmp_path / "vj.json.tmp").exists()  # the torn temp is left behind...
    # ...and a restart sees exactly the durable state
    assert [v.block_hash for v in VoteJournal(CHAIN, path).votes_at(1, "0xv")] == ["0xaaaa"]
    assert VoteJournal(CHAIN, path).votes_at(2, "0xv") == []


def test_stale_tmp_file_is_overwritten_by_the_next_write(tmp_path):
    path = tmp_path / "vj.json"
    (tmp_path / "vj.json.tmp").write_text("{garbage from a crashed writer")
    j = VoteJournal(CHAIN, path)
    assert j.record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0) is True
    assert not (tmp_path / "vj.json.tmp").exists()
    assert len(_rows(path)) == 1


def test_fsync_failure_refuses_the_vote(tmp_path, monkeypatch):
    j = VoteJournal(CHAIN, tmp_path / "vj.json")
    monkeypatch.setattr(vote_journal.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("EIO")))
    with pytest.raises(VoteJournalError):
        j.record(1, "0xv", "0xaaaa", KIND_ATTEST)
    assert j.height_count() == 0


@pytest.mark.parametrize(
    "content", ["", "{", '{"votes": [', "[]", "null", '"text"', '{"chain_id": ' + json.dumps(CHAIN) + ', "votes": 7}']
)
def test_unreadable_or_odd_shapes_degrade_to_empty(tmp_path, content):
    path = tmp_path / "vj.json"
    path.write_text(content)
    assert VoteJournal(CHAIN, path).votes_at(1, "0xv") == []


def test_truncated_file_is_counted(tmp_path):
    path = tmp_path / "vj.json"
    j = VoteJournal(CHAIN, path)
    for h in range(1, 6):
        j.record(h, "0xv", f"0x{h:04x}", KIND_ATTEST, now=T0)
    path.write_text(path.read_text()[:-40])  # torn tail
    assert VoteJournal(CHAIN, path).height_count() == 0
    assert _counter("vote_journal_load_failed_total") == 1


def test_bad_records_are_skipped_and_good_ones_kept(tmp_path):
    path = tmp_path / "vj.json"
    j = VoteJournal(CHAIN, path)
    j.record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0)
    j.record(2, "0xv", "0xbbbb", KIND_ATTEST, now=T0)
    data = json.loads(path.read_text())
    data["votes"].insert(1, {"height": "not-a-number"})
    data["votes"].insert(0, 42)
    data["votes"].append({"voter": "x"})
    path.write_text(json.dumps(data))
    reloaded = VoteJournal(CHAIN, path)
    assert [v.block_hash for v in reloaded.votes_at(1, "0xv")] == ["0xaaaa"]
    assert [v.block_hash for v in reloaded.votes_at(2, "0xv")] == ["0xbbbb"]


def test_unreadable_journal_fails_closed_and_keeps_the_file(tmp_path):
    """Operator ruling (10 Nov): an unreadable journal must not release votes. No vote is
    recorded (so no attestation/proposal is signed), the unreadable file is never overwritten,
    and recovery is an operator action (move the file aside, restart)."""
    path = tmp_path / "vj.json"
    VoteJournal(CHAIN, path).record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0)
    path.write_text("{corrupt")
    j = VoteJournal(CHAIN, path)
    with pytest.raises(VoteJournalError):
        j.record(1, "0xv", "0xrival", KIND_ATTEST, now=T0)
    with pytest.raises(VoteJournalError):
        j.record(2, "0xv", "0xother", KIND_ATTEST, now=T0)  # not just the conflicting height
    assert path.read_text() == "{corrupt"  # evidence preserved, never replaced
    assert _counter("vote_journal_fail_closed_total") == 2
    assert j.votes_at(1, "0xv") == []
    # operator moves the file aside and restarts: a fresh journal works again
    path.rename(tmp_path / "vj.json.corrupt")
    assert VoteJournal(CHAIN, path).record(1, "0xv", "0xrival", KIND_ATTEST, now=T0) is True


def test_absent_file_is_a_fresh_start_not_a_failure(tmp_path):
    j = VoteJournal(CHAIN, tmp_path / "nope" / "vj.json")
    assert j.record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0) is True
    assert _counter("vote_journal_fail_closed_total") == 0


def test_wrong_chain_file_is_not_a_failure(tmp_path):
    path = tmp_path / "vj.json"
    VoteJournal("other-chain", path).record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0)
    assert VoteJournal(CHAIN, path).record(1, "0xv", "0xbbbb", KIND_ATTEST, now=T0) is True


def test_skipped_rows_are_counted(tmp_path):
    path = tmp_path / "vj.json"
    VoteJournal(CHAIN, path).record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0)
    data = json.loads(path.read_text())
    data["votes"] += [42, {"height": "x"}]
    path.write_text(json.dumps(data))
    VoteJournal(CHAIN, path).votes_at(1, "0xv")
    assert _counter("vote_journal_rows_skipped_total") == 2


def test_valve_boundary_is_inclusive_and_nonpositive_window_never_opens():
    rec = SimpleNamespace(at=T0)
    assert valve_open(rec, 300.0, now=T0 + 300.0) is True
    assert valve_open(rec, 300.0, now=T0 + 299.999) is False
    assert valve_open(rec, 0.0, now=T0 + 10**9) is False
    assert valve_open(rec, -5.0, now=T0 + 10**9) is False


def test_concurrent_writers_all_land_and_survive_reload(tmp_path):
    path = tmp_path / "vj.json"
    j = VoteJournal(CHAIN, path)
    errors: list[BaseException] = []

    def writer(i: int) -> None:
        try:
            for n in range(25):
                j.record(1000 + i * 100 + n, f"0xv{i}", f"0x{i:02x}{n:02x}", KIND_ATTEST, now=T0)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,), daemon=True) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not any(t.is_alive() for t in threads) and not errors
    assert len(_rows(path)) == 100
    assert VoteJournal(CHAIN, path).height_count() == 100


def test_height_hard_cap_evicts_the_oldest_heights(tmp_path, monkeypatch):
    monkeypatch.setattr(vote_journal, "VOTE_JOURNAL_MAX_HEIGHTS", 5)
    j = VoteJournal(CHAIN, tmp_path / "vj.json")
    for h in range(1, 11):
        j.record(h, "0xv", f"0x{h:04x}", KIND_ATTEST, now=T0)
    assert j.prune_below(None) == 5
    assert sorted(j._votes) == [6, 7, 8, 9, 10]
    assert VoteJournal(CHAIN, tmp_path / "vj.json").height_count() == 5


def test_retract_and_prune_persist_failures_keep_the_safe_entries(tmp_path, monkeypatch):
    path = tmp_path / "vj.json"
    j = VoteJournal(CHAIN, path)
    j.record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0)
    j.record(2, "0xv", "0xbbbb", KIND_ATTEST, now=T0)
    monkeypatch.setattr(j, "_persist", lambda: (_ for _ in ()).throw(OSError("ro fs")))
    assert j.retract(2, "0xv", "0xbbbb") is True  # in memory only
    assert j.prune_below(2) == 1
    # the file on disk still has both votes: a restart is conservative (keeps the barrier)
    assert {v["height"] for v in _rows(path)} == {1, 2}


def test_record_after_restart_is_a_noop_for_an_existing_vote(tmp_path):
    path = tmp_path / "vj.json"
    VoteJournal(CHAIN, path).record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0)
    assert VoteJournal(CHAIN, path).record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0 + 5) is False


def test_justification_round_trips_through_a_restart(tmp_path):
    path = tmp_path / "vj.json"
    just = {"class": "evidence", "cert": {"k": 1}}
    VoteJournal(CHAIN, path).record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0, justification=just)
    (rec,) = VoteJournal(CHAIN, path).votes_at(1, "0xv")
    assert rec.justification == just


def test_file_is_written_with_fsync_before_rename(tmp_path, monkeypatch):
    order: list[str] = []
    real_fsync = os.fsync
    monkeypatch.setattr(vote_journal.os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    real_replace = type(tmp_path).replace
    monkeypatch.setattr(type(tmp_path), "replace", lambda self, t: (order.append("rename"), real_replace(self, t))[1])
    VoteJournal(CHAIN, tmp_path / "vj.json").record(1, "0xv", "0xaaaa", KIND_ATTEST, now=T0)
    assert order == ["fsync", "rename"]


@pytest.mark.asyncio
async def test_attester_gate_refuses_to_sign_when_the_journal_is_unreadable(tmp_path, monkeypatch):
    from aitbc_chain.config import settings
    from aitbc_chain.consensus import remote_attestation as ra_module
    from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
    from aitbc_chain.consensus.vote_journal import reset_vote_journals

    from eth_keys import keys

    key = "0x" + "11" * 32
    addr = keys.PrivateKey(bytes.fromhex(key[2:])).public_key.to_checksum_address()
    reset_vote_journals()
    monkeypatch.setattr(vote_journal, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ra_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "vote_journal_enabled", True)
    jpath = tmp_path / "data" / CHAIN / "vote_journal.json"
    jpath.parent.mkdir(parents=True)
    jpath.write_text("{corrupt")
    svc = RemoteAttestationService(CHAIN, {addr: key})
    try:
        assert await svc._journal_refuses(100, "0x" + "aa" * 32, addr, addr, None) is True
        assert jpath.read_text() == "{corrupt"
    finally:
        reset_vote_journals()
