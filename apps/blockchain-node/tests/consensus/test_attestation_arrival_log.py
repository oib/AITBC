"""Attestation arrival log lines (V-9 measurement).

Under v9 a block carries the proposer plus exactly two attestations, and the proposer
keeps the first two valid answers it reads. One validator (hub1) is in ~3% of blocks,
and nothing records why: the answers that lose the race leave no trace, and the ones
that win carry no timing. The collector now writes one INFO line per response that
reaches it -- who, how long after the request was published, and what became of it --
and the attester writes one when it publishes (request age on arrival, as seen on its own
clock): the collector cannot see an answer that comes after the kept ones, the attester can.

The signed responses come from the real attester path (``_handle_request``) rather than a
copy of the message format, so a collector that stops accepting what attesters send fails
here and not only on the fleet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from types import SimpleNamespace

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import remote_attestation as ra_module
from aitbc_chain.consensus.remote_attestation import RemoteAttestationService
from aitbc_chain.metrics import metrics_registry
from eth_keys import keys

CHAIN = "test-chain"
ARRIVAL = "Attestation arrival"
PUBLISHED = "Attestation response published"


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_registry.reset()
    yield
    metrics_registry.reset()


def _identity(seed: str) -> tuple[str, str]:
    key = "0x" + seed * 32
    return keys.PrivateKey(bytes.fromhex(key[2:])).public_key.to_checksum_address(), key


PROPOSER = _identity("22")
ATTESTER_A = _identity("11")
ATTESTER_B = _identity("33")


class _Broker:
    """Stands in for the gossip broker: records publishes, replays scripted responses."""

    def __init__(self, responses=()):
        self.published: list[tuple[str, dict]] = []
        self._responses = list(responses)

    async def publish(self, topic, message):
        self.published.append((topic, message))

    async def subscribe(self, topic, max_queue_size=0):
        return _Subscription(self._responses)


class _Subscription:
    def __init__(self, responses):
        self._responses = list(responses)

    async def get(self):
        if not self._responses:
            await asyncio.Event().wait()  # nothing more arrives: the caller's timeout ends it
        delay, message = self._responses.pop(0)
        if delay:
            await asyncio.sleep(delay)
        return message

    def close(self):
        pass


def _block(block_hash="0xaaaa", height=100):
    return SimpleNamespace(
        height=height,
        hash=block_hash,
        parent_hash="0xparent",
        proposer=PROPOSER[0],
        state_root="0xroot",
        bridge_state_root="",
        timestamp=None,
    )


def _request(block, request_timestamp=None):
    return {
        "header": {
            "chain_id": CHAIN,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash,
            "proposer": block.proposer,
            "state_root": block.state_root,
            "bridge_state_root": block.bridge_state_root,
        },
        "timestamp": time.time() if request_timestamp is None else request_timestamp,
    }


async def _attest(monkeypatch, attester, block, request_timestamp=None):
    """The response ``attester`` publishes for ``block`` -- through the real handler."""
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": PROPOSER[0]}, {"address": ATTESTER_A[0]}, {"address": ATTESTER_B[0]}]),
    )
    broker = _Broker()
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    await RemoteAttestationService(CHAIN, {attester[0]: attester[1]})._handle_request(_request(block, request_timestamp))
    assert broker.published, "the attester did not answer"
    return broker.published[-1][1]


async def _collect(monkeypatch, responses, block, min_count=2, timeout=0.5):
    broker = _Broker(responses)
    monkeypatch.setattr(ra_module, "gossip_broker", broker)
    collector = RemoteAttestationService(CHAIN, {PROPOSER[0]: PROPOSER[1]})
    return await collector.collect_attestations(block, min_count, timeout=timeout)


def _lines(caplog, prefix):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]


class TestProposerArrivalLines:
    async def test_every_kept_answer_is_logged_with_who_when_and_rank(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)
        block = _block()
        first = await _attest(monkeypatch, ATTESTER_A, block)
        second = await _attest(monkeypatch, ATTESTER_B, block)

        got = await _collect(monkeypatch, [(0.0, first), (0.05, second)], block)

        assert [a["validator"] for a in got] == [ATTESTER_A[0], ATTESTER_B[0]]
        lines = _lines(caplog, ARRIVAL)
        assert len(lines) == 2
        assert f"height=100 validator={ATTESTER_A[0]} " in lines[0] and "outcome=valid rank=1" in lines[0]
        assert f"height=100 validator={ATTESTER_B[0]} " in lines[1] and "outcome=valid rank=2" in lines[1]
        arrived = [int(line.split("arrived_ms=")[1].split()[0]) for line in lines]
        assert arrived == sorted(arrived) and arrived[1] >= 40, "the second answer was sent 50 ms after the first"

    async def test_an_answer_that_fails_verification_is_logged_not_counted(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)
        block = _block()
        good = await _attest(monkeypatch, ATTESTER_A, block)
        forged = {**await _attest(monkeypatch, ATTESTER_B, block), "validator": ATTESTER_A[0]}

        got = await _collect(monkeypatch, [(0.0, forged), (0.0, good)], block, min_count=1)

        assert [a["validator"] for a in got] == [ATTESTER_A[0]]
        lines = _lines(caplog, ARRIVAL)
        assert "outcome=invalid_signature" in lines[0]
        assert "outcome=valid rank=1" in lines[1]

    async def test_an_answer_to_an_earlier_block_is_logged_as_stale(self, monkeypatch, caplog):
        """The response topic is shared: a slow validator's answer for block h-1 can land in
        the window of block h. That is the only way a late answer is ever seen."""
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)
        earlier = await _attest(monkeypatch, ATTESTER_A, _block("0xbbbb", height=99))
        block = _block()
        current = await _attest(monkeypatch, ATTESTER_B, block)

        got = await _collect(monkeypatch, [(0.0, earlier), (0.0, current)], block, min_count=1)

        assert [a["validator"] for a in got] == [ATTESTER_B[0]]
        lines = _lines(caplog, ARRIVAL)
        assert f"validator={ATTESTER_A[0]} " in lines[0]
        assert "outcome=stale response_height=99" in lines[0]
        assert "outcome=valid rank=1" in lines[1]

    async def test_a_response_for_another_chain_is_ignored_and_not_logged(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)
        block = _block()
        foreign = {**await _attest(monkeypatch, ATTESTER_A, block), "chain_id": "other-chain"}

        got = await _collect(monkeypatch, [(0.0, foreign)], block, timeout=0.2)

        assert got == []
        assert _lines(caplog, ARRIVAL) == []

    async def test_no_answer_means_no_line(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)

        got = await _collect(monkeypatch, [], _block(), timeout=0.2)

        assert got == []
        assert _lines(caplog, ARRIVAL) == []


class TestAttesterPublishedLine:
    async def test_publishing_logs_who_answered_for_whom_and_the_request_age(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)

        await _attest(monkeypatch, ATTESTER_A, _block(), request_timestamp=time.time() - 0.25)

        lines = _lines(caplog, PUBLISHED)
        assert len(lines) == 1
        assert f"height=100 validator={ATTESTER_A[0]} proposer={PROPOSER[0]} " in lines[0]
        age = int(lines[0].split("request_age_ms=")[1])
        assert 250 <= age < 5000

    async def test_a_request_without_a_timestamp_still_logs(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)
        monkeypatch.setattr(
            settings,
            "validator_set",
            json.dumps([{"address": PROPOSER[0]}, {"address": ATTESTER_A[0]}]),
        )
        broker = _Broker()
        monkeypatch.setattr(ra_module, "gossip_broker", broker)
        request = _request(_block())
        del request["timestamp"]

        await RemoteAttestationService(CHAIN, {ATTESTER_A[0]: ATTESTER_A[1]})._handle_request(request)

        assert broker.published, "the attester must answer whether or not the request carries a timestamp"
        assert "request_age_ms=unknown" in _lines(caplog, PUBLISHED)[0]

    async def test_a_refused_request_logs_no_published_line(self, monkeypatch, caplog):
        """A request for a block from outside the validator set gets no answer and no line."""
        caplog.set_level(logging.INFO, logger=ra_module.logger.name)
        monkeypatch.setattr(settings, "validator_set", json.dumps([{"address": ATTESTER_A[0]}]))
        broker = _Broker()
        monkeypatch.setattr(ra_module, "gossip_broker", broker)

        await RemoteAttestationService(CHAIN, {ATTESTER_A[0]: ATTESTER_A[1]})._handle_request(_request(_block()))

        assert broker.published == []
        assert _lines(caplog, PUBLISHED) == []
