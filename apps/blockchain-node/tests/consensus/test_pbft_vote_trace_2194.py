"""#2194 — PBFT observability: quorum-gap detail, vote trace flag, intake-drop counters."""

from __future__ import annotations

import logging
import secrets

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus.pbft import PBFTConsensus
from aitbc_chain.consensus.pbft_trace import describe_quorum_gap
from aitbc_chain.metrics import metrics_registry

from .test_pbft import _build_partitioned_nodes, _partitioned_fixture, _prepare_data


def _counter(name: str) -> float:
    return metrics_registry._counters.get(name, 0.0)


@pytest.mark.asyncio
async def test_quorum_timeout_warning_names_missing_validators(caplog):
    keypairs, shared, proposer_addr = _partitioned_fixture("test-pbft-2194-gap")
    partitions = {addr: 0 if addr == proposer_addr else 1 for addr, _ in keypairs}
    _net, nodes = _build_partitioned_nodes("test-pbft-2194-gap", keypairs, shared, partitions)
    with caplog.at_level(logging.WARNING):
        ok = await nodes[proposer_addr].propose_and_wait(
            proposer_addr, "0x" + secrets.token_hex(32), timeout=1.0, sequence=1, view=0
        )
    assert ok is False
    line = next(r.getMessage() for r in caplog.records if "quorum timeout" in r.getMessage())
    assert "voted=[" in line and "missing=[" in line
    others = [a for a, _ in keypairs if a != proposer_addr]
    for addr in others:
        assert addr[:10] in line.split("missing=")[1]
    assert proposer_addr[:10] in line.split("missing=")[0]


def test_describe_quorum_gap_reports_lag():
    class V:
        sender = "0x" + "aa" * 20
        timestamp = 100.0
        _rx_ts = 101.5

    out = describe_quorum_gap(["0x" + "aa" * 20, "0x" + "bb" * 20], [V()])
    assert "lag=1.50s" in out
    assert out.count("0xbbbbbbbb") == 1 and "missing=[0xbbbbbbbb" in out


@pytest.mark.asyncio
async def test_trace_flag_off_emits_nothing(caplog, monkeypatch):
    monkeypatch.setattr(settings, "pbft_vote_trace_enabled", False, raising=False)
    keypairs, shared, proposer_addr = _partitioned_fixture("test-pbft-2194-off")
    partitions = {addr: 0 for addr, _ in keypairs}
    _net, nodes = _build_partitioned_nodes("test-pbft-2194-off", keypairs, shared, partitions)
    with caplog.at_level(logging.INFO):
        await nodes[proposer_addr].propose_and_wait(
            proposer_addr, "0x" + secrets.token_hex(32), timeout=3.0, sequence=1, view=0
        )
    assert not [r for r in caplog.records if "PBFT-TRACE" in r.getMessage()]


@pytest.mark.asyncio
async def test_trace_flag_on_logs_votes_and_phases(caplog, monkeypatch):
    monkeypatch.setattr(settings, "pbft_vote_trace_enabled", True, raising=False)
    keypairs, shared, proposer_addr = _partitioned_fixture("test-pbft-2194-on")
    partitions = {addr: 0 for addr, _ in keypairs}
    _net, nodes = _build_partitioned_nodes("test-pbft-2194-on", keypairs, shared, partitions)
    with caplog.at_level(logging.INFO):
        ok = await nodes[proposer_addr].propose_and_wait(
            proposer_addr, "0x" + secrets.token_hex(32), timeout=5.0, sequence=1, view=0
        )
    assert ok is True
    text = "\n".join(r.getMessage() for r in caplog.records if "PBFT-TRACE" in r.getMessage())
    for needle in (
        "accept type=prepare",
        "accept type=commit",
        "propose.pre_prepare_out",
        "propose.prepare_quorum",
        "propose.commit_quorum",
    ):
        assert needle in text, needle
    # E-1b: every vote/phase line names the block, so a retry with a different body is visible
    assert "hash=0x" in text


@pytest.mark.asyncio
async def test_intake_drop_counted_with_reason(caplog, monkeypatch):
    monkeypatch.setattr(settings, "pbft_vote_trace_enabled", True, raising=False)
    keypairs, shared, proposer_addr = _partitioned_fixture("test-pbft-2194-drop")
    node = PBFTConsensus(shared, private_key="", chain_id="test-pbft-2194-drop", local_validator=keypairs[0][0])
    before_total = _counter("pbft_intake_drop_total")
    before_reason = _counter("pbft_intake_drop_digest_mismatch_total")
    data = _prepare_data(node, keypairs[1][0], "0x" + "11" * 32)
    data["digest"] = "0xbad"
    with caplog.at_level(logging.INFO):
        await node.handle_incoming_message(data)
    assert _counter("pbft_intake_drop_total") == before_total + 1
    assert _counter("pbft_intake_drop_digest_mismatch_total") == before_reason + 1
    assert any("PBFT-TRACE drop" in r.getMessage() and "reason=digest_mismatch" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_malformed_drop_names_type_and_hash(caplog, monkeypatch):
    monkeypatch.setattr(settings, "pbft_vote_trace_enabled", True, raising=False)
    keypairs, shared, _p = _partitioned_fixture("test-pbft-2194-mal")
    node = PBFTConsensus(shared, private_key="", chain_id="test-pbft-2194-mal", local_validator=keypairs[0][0])
    with caplog.at_level(logging.INFO):
        await node.handle_incoming_message({"message_type": "bogus", "block_hash": "0x" + "ab" * 32})
    lines = [r.getMessage() for r in caplog.records if "reason=malformed" in r.getMessage()]
    assert lines and "type=bogus" in lines[0] and "hash=0xabababababab" in lines[0]
