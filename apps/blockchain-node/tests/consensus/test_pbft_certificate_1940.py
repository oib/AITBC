"""#1940 F3 certificate-contract subtranche — strict PBFT commit certificates.

Once ``pbft_certificate_strict_height`` is armed, the PBFT commit
certificate carried in ``block_metadata.pbft_certificate`` must satisfy the
shared strict contract in ``consensus/pbft_certificate.py`` at BOTH the
producer (``PBFTConsensus.get_certificate`` + the PoA attestation gate) and
the importer (``ProposerSignatureValidator``):

- one coherent ``(sequence_number, view_number)`` group only — votes for
  different views or sequences are rejected, never unioned into a quorum;
- ``sequence_number`` must equal the block height and the shared view must
  match when one is expected;
- the quorum is ``pbft_required_messages(n)`` for the real validator set —
  independent of ``multi_validator_min_attestations``;
- every counted record needs COMMIT phase, explicit matching ``block_hash``,
  strictly-int non-negative view/sequence, the matching
  ``sha256(block_hash:seq:view)`` digest and a real
  ``verify_consensus_message`` signature; malformed records and bad
  signatures never raise and never count;
- pre-threshold/unset keeps the legacy verifier byte-for-byte.

These tests use real secp256k1 keys and signatures throughout. This tranche
pins the certificate contract only — cross-view safety is separate design
work and fleet PBFT stays OFF.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any

import pytest

from aitbc_chain.config import ProposerConfig, settings
from aitbc_chain.consensus.multi_validator_poa import MultiValidatorPoA, ValidatorRole
from aitbc_chain.consensus.pbft import PBFTConsensus, PBFTMessage, PBFTMessageType
from aitbc_chain.consensus.pbft_certificate import strict_certificate_active, validate_commit_certificate
from aitbc_chain.consensus.poa import PoAProposer
from aitbc.crypto.consensus_signing import sign_block_hash, sign_consensus_message

CHAIN = "pbft-cert-1940"
BH = "0x" + "ab" * 32
OTHER_BH = "0x" + "cd" * 32
HEIGHT = 10
VIEW = 3


def _key(byte: str) -> tuple[str, str]:
    from eth_keys import keys

    priv = "0x" + byte * 32
    return keys.PrivateKey(bytes.fromhex(priv[2:])).public_key.to_checksum_address(), priv


ADDR1, KEY1 = _key("11")
ADDR2, KEY2 = _key("22")
ADDR3, KEY3 = _key("33")
ADDR4, KEY4 = _key("44")
ADDR5, KEY5 = _key("55")  # outsider — never in the validator set
MEMBERS = [ADDR1, ADDR2, ADDR3, ADDR4]
SIGNS = {ADDR1: KEY1, ADDR2: KEY2, ADDR3: KEY3, ADDR4: KEY4}


def _digest(block_hash: str, seq: int, view: int) -> str:
    return hashlib.sha256(f"{block_hash}:{seq}:{view}".encode()).hexdigest()


def _commit(
    sender: str,
    priv: str,
    *,
    block_hash: str = BH,
    seq: int = HEIGHT,
    view: int = VIEW,
    message_type: str = "commit",
) -> dict[str, Any]:
    """A real signed PBFT commit record, ``PBFTMessage.to_dict`` shape."""
    msg = {
        "message_type": message_type,
        "sender": sender,
        "view_number": view,
        "sequence_number": seq,
        "digest": _digest(block_hash, seq, view),
    }
    return {
        **msg,
        "signature": sign_consensus_message(msg, priv),
        "timestamp": 0.0,
        "block_hash": block_hash,
    }


def _quorum(
    view: int = VIEW,
    seq: int = HEIGHT,
    senders=(ADDR1, ADDR2, ADDR3),
    block_hash: str = BH,
) -> list[dict[str, Any]]:
    """Three same-tuple commits — the n=4 BFT quorum."""
    return [_commit(a, SIGNS[a], view=view, seq=seq, block_hash=block_hash) for a in senders]


def _validate(cert: list[dict[str, Any]], *, height: int = HEIGHT, view: int | None = VIEW, members=MEMBERS):
    return validate_commit_certificate(cert, BH, members, height=height, view=view, chain_id="test-chain")


# ---------------------------------------------------------------------------
# validate_commit_certificate — the shared strict contract
# ---------------------------------------------------------------------------


class TestValidateCommitCertificate:
    def test_three_same_tuple_commits_accept(self):
        ok, reason = _validate(_quorum())
        assert ok, reason

    def test_two_commits_reject(self):
        ok, reason = _validate(_quorum(senders=(ADDR1, ADDR2)))
        assert not ok
        assert "need 3" in reason

    def test_duplicate_and_case_varied_sender_cannot_inflate(self):
        # Three records but only TWO distinct senders — ADDR2 twice, the
        # second spelling lower-cased. Without dedup this would read as 3.
        cert = [_commit(ADDR1, KEY1), _commit(ADDR2, KEY2), _commit(ADDR2.lower(), KEY2)]
        ok, reason = _validate(cert)
        assert not ok, "duplicate sender must not count twice"
        # A genuinely distinct third member reaches the quorum.
        cert.append(_commit(ADDR3, KEY3))
        ok, reason = _validate(cert)
        assert ok, reason

    def test_mixed_views_individually_valid_reject(self):
        # 2 commits at view 3 + 2 at view 7 — every signature valid, but the
        # certificate mixes rounds: 4 counted records can never form ONE quorum.
        cert = _quorum(view=VIEW, senders=(ADDR1, ADDR2)) + _quorum(view=7, senders=(ADDR3, ADDR4))
        ok, reason = _validate(cert)
        assert not ok
        assert "mixed" in reason

    def test_mixed_sequence_reject(self):
        cert = _quorum() + [_commit(ADDR4, KEY4, seq=HEIGHT + 1)]
        ok, reason = _validate(cert)
        assert not ok
        assert "mixed" in reason

    def test_uniform_wrong_sequence_reject(self):
        cert = _quorum(seq=HEIGHT + 1)
        ok, reason = _validate(cert, height=HEIGHT)
        assert not ok
        assert "sequence" in reason

    @pytest.mark.parametrize("bad", [True, -1, "3", 2.5, None])
    def test_malformed_view_number_never_counts(self, bad):
        good = _quorum(senders=(ADDR1, ADDR2))
        rec = _commit(ADDR3, KEY3)
        rec["view_number"] = bad
        ok, reason = _validate(good + [rec])
        assert not ok, f"view_number={bad!r} must not count"

    @pytest.mark.parametrize("bad", [True, -1, "10", 10.0, None])
    def test_malformed_sequence_number_never_counts(self, bad):
        good = _quorum(senders=(ADDR1, ADDR2))
        rec = _commit(ADDR3, KEY3)
        rec["sequence_number"] = bad
        ok, reason = _validate(good + [rec])
        assert not ok, f"sequence_number={bad!r} must not count"

    def test_only_malformed_records_reject_without_raising(self):
        rec = _commit(ADDR1, KEY1)
        rec["view_number"] = True
        cert: list[Any] = ["not-a-dict", rec, None, 42]
        ok, reason = _validate(cert)  # type: ignore[arg-type]
        assert not ok

    def test_outsider_forged_wrong_block_and_noncommit_do_not_count(self):
        good = _quorum(senders=(ADDR1, ADDR2))
        outsider = _commit(ADDR5, KEY5)  # real signature, not a member
        forged = _commit(ADDR3, KEY4)  # signed by KEY4 but claims ADDR3
        wrong_block = _commit(ADDR3, KEY3, block_hash=OTHER_BH)
        prepare = _commit(ADDR3, KEY3, message_type="prepare")
        ok, reason = _validate(good + [outsider, forged, wrong_block, prepare])
        assert not ok, "only the two member commits may count"
        # The same records with a real third member commit do accept.
        cert = good + [_commit(ADDR3, KEY3)]
        ok, reason = _validate(cert)
        assert ok, reason

    def test_missing_block_hash_field_does_not_count(self):
        rec = _commit(ADDR3, KEY3)
        del rec["block_hash"]
        ok, _ = _validate(_quorum(senders=(ADDR1, ADDR2)) + [rec])
        assert not ok

    def test_wrong_digest_does_not_count(self):
        rec = _commit(ADDR3, KEY3)
        rec["digest"] = "0" * 64
        ok, _ = _validate(_quorum(senders=(ADDR1, ADDR2)) + [rec])
        assert not ok

    def test_requested_view_is_enforced(self):
        cert = _quorum(view=7)
        ok, reason = _validate(cert, view=VIEW)
        assert not ok
        assert "view" in reason
        ok, reason = _validate(cert, view=7)
        assert ok, reason
        ok, reason = _validate(cert, view=None)
        assert ok, reason

    def test_empty_validator_set_rejects(self):
        ok, reason = validate_commit_certificate(_quorum(), BH, [], height=HEIGHT, view=VIEW, chain_id="test-chain")
        assert not ok
        assert "validator set" in reason

    def test_unpinned_view_and_height_boundaries(self):
        ok, _ = _validate(_quorum(), view=None)
        assert ok
        ok, _ = _validate(_quorum(), height=HEIGHT - 1)
        assert not ok


# ---------------------------------------------------------------------------
# strict_certificate_active — the configured-activation-height gate
# ---------------------------------------------------------------------------


class TestStrictCertificateActive:
    @pytest.fixture(autouse=True)
    def _armed(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_certificate_strict_height", 10)

    @pytest.mark.parametrize("height,expected", [(9, False), (10, True), (11, True), (0, False)])
    def test_threshold_boundary(self, height, expected):
        assert strict_certificate_active(height) is expected

    @pytest.mark.parametrize("height", [None, True, "10", 10.5])
    def test_invalid_height_is_inactive(self, height):
        assert strict_certificate_active(height) is False

    def test_unset_threshold_is_inactive(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_certificate_strict_height", None)
        assert strict_certificate_active(10**9) is False

    def test_zero_threshold_activates_at_zero(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_certificate_strict_height", 0)
        assert strict_certificate_active(0) is True
        assert strict_certificate_active(5) is True


# ---------------------------------------------------------------------------
# Producer — PBFTConsensus.get_certificate under the strict gate
# ---------------------------------------------------------------------------


def _make_pbft(members=MEMBERS) -> PBFTConsensus:
    consensus = MultiValidatorPoA(CHAIN)
    for addr in members:
        consensus.add_validator(addr, 1000.0)
        consensus.validators[addr].role = ValidatorRole.PROPOSER
    return PBFTConsensus(consensus, private_key="", chain_id=CHAIN, local_validator=members[0])


def _commit_msg(pbft: PBFTConsensus, sender: str, priv: str, *, seq: int, view: int, block_hash: str = BH) -> PBFTMessage:
    digest = pbft.get_message_digest(block_hash, seq, view)
    msg_data = {
        "message_type": "commit",
        "sender": sender,
        "view_number": view,
        "sequence_number": seq,
        "digest": digest,
    }
    return PBFTMessage(
        message_type=PBFTMessageType.COMMIT,
        sender=sender,
        view_number=view,
        sequence_number=seq,
        digest=digest,
        signature=sign_consensus_message(msg_data, priv),
        timestamp=0.0,
        block_hash=block_hash,
    )


def _seed_commits(pbft: PBFTConsensus, groups: dict[tuple[int, int], list[str]], block_hash: str = BH) -> None:
    """Inject commit messages into ``state.committed_messages`` buckets."""
    for (seq, view), senders in groups.items():
        key = f"{seq}:{view}"
        pbft.state.committed_messages[key] = [
            _commit_msg(pbft, addr, SIGNS[addr], seq=seq, view=view, block_hash=block_hash) for addr in senders
        ]


@pytest.fixture
def _strict_gate(monkeypatch):
    monkeypatch.setattr(settings, "pbft_certificate_strict_height", HEIGHT)


class TestGetCertificateStrict:
    def test_cannot_union_two_plus_one_across_views(self, _strict_gate):
        """2 commits at view 3 + 1 at view 7 = 3 distinct senders — the legacy
        union would pass quorum; the strict gate must return nothing."""
        pbft = _make_pbft()
        _seed_commits(
            pbft,
            {
                (HEIGHT, VIEW): [ADDR1, ADDR2],
                (HEIGHT, 7): [ADDR3],
            },
        )
        assert pbft.get_certificate(BH) == []

    def test_selects_complete_matching_view_group(self, _strict_gate):
        """Two complete groups: the higher view wins deterministically."""
        pbft = _make_pbft()
        _seed_commits(
            pbft,
            {
                (HEIGHT, VIEW): [ADDR1, ADDR2, ADDR3],
                (HEIGHT, 7): [ADDR1, ADDR2, ADDR4],
            },
        )
        cert = pbft.get_certificate(BH)
        assert len(cert) == 3
        assert {m["view_number"] for m in cert} == {7}
        assert {m["sequence_number"] for m in cert} == {HEIGHT}

    def test_incomplete_group_alone_returns_empty(self, _strict_gate):
        pbft = _make_pbft()
        _seed_commits(pbft, {(HEIGHT, VIEW): [ADDR1, ADDR2]})
        assert pbft.get_certificate(BH) == []

    def test_requested_incomplete_view_returns_empty(self, _strict_gate):
        """An explicit view request is honored: no substitution from other views."""
        pbft = _make_pbft()
        _seed_commits(
            pbft,
            {
                (HEIGHT, VIEW): [ADDR1, ADDR2, ADDR3],
                (HEIGHT, 7): [ADDR1, ADDR2],
            },
        )
        assert pbft.get_certificate(BH, view=7) == []
        assert len(pbft.get_certificate(BH, view=VIEW)) == 3

    def test_prethreshold_keeps_legacy_union(self, monkeypatch):
        """Gate unset: the old union-across-buckets body is unchanged — the
        same 2+1 split the strict gate rejects now returns 3 records."""
        monkeypatch.setattr(settings, "pbft_certificate_strict_height", None)
        pbft = _make_pbft()
        _seed_commits(
            pbft,
            {
                (HEIGHT, VIEW): [ADDR1, ADDR2],
                (HEIGHT, 7): [ADDR3],
            },
        )
        cert = pbft.get_certificate(BH)
        assert len(cert) == 3
        assert {m["view_number"] for m in cert} == {VIEW, 7}

    def test_below_threshold_keeps_legacy_union(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_certificate_strict_height", HEIGHT + 1)
        pbft = _make_pbft()
        _seed_commits(
            pbft,
            {
                (HEIGHT, VIEW): [ADDR1, ADDR2],
                (HEIGHT, 7): [ADDR3],
            },
        )
        assert len(pbft.get_certificate(BH)) == 3


# ---------------------------------------------------------------------------
# Producer gate — PoAProposer._collect_and_gate_attestations
# ---------------------------------------------------------------------------


class _FakeMultiValidator:
    def __init__(self, members: list[str]) -> None:
        self._members = members

    def get_consensus_participants(self) -> list[str]:
        return list(self._members)

    def reload_state_if_anomalous(self) -> None:
        pass


def _poa_proposer() -> PoAProposer:
    config = ProposerConfig(
        chain_id=CHAIN,
        proposer_id=ADDR1,
        interval_seconds=5,
        max_block_size_bytes=1_000_000,
        max_txs_per_block=100,
    )
    return PoAProposer(config=config, session_factory=lambda: None)  # type: ignore[arg-type,return-value]


def _wire_proposer(proposer: PoAProposer, pbft_consensus, members=MEMBERS):
    proposer._pbft_consensus = pbft_consensus  # type: ignore[assignment]
    proposer._multi_validator = _FakeMultiValidator(members)  # type: ignore[assignment]


class _RecordingPbft:
    """Duck-typed ``_pbft_consensus``: returns a canned certificate."""

    def __init__(self, certificate: list[dict[str, Any]]) -> None:
        self._certificate = certificate

    def get_certificate(self, block_hash: str, view: int | None = None) -> list[dict[str, Any]]:
        return list(self._certificate)


@pytest.mark.asyncio
class TestPoaCertificateGate:
    @pytest.fixture(autouse=True)
    def _armed(self, monkeypatch):
        monkeypatch.setattr(settings, "pbft_certificate_strict_height", HEIGHT)
        monkeypatch.setattr(settings, "multi_validator_min_attestations", 0)

    async def _run(self, proposer: PoAProposer, round_number: int | None = VIEW):
        block = SimpleNamespace(height=HEIGHT, proposer=ADDR1)
        metadata: dict[str, Any] = {}
        attest_calls: list[int] = []

        async def _fake_collect(block, transactions=None, round_number=None):
            attest_calls.append(1)
            return [{"validator": ADDR2, "signature": "0x00"}] * 5

        proposer._collect_attestations = _fake_collect  # type: ignore[assignment]
        ok = await proposer._collect_and_gate_attestations(block, BH, metadata, round_number=round_number)  # type: ignore[arg-type]
        return ok, metadata, attest_calls

    async def test_missing_certificate_refuses_before_gossip(self):
        proposer = _poa_proposer()
        _wire_proposer(proposer, _RecordingPbft([]))
        ok, _metadata, attest_calls = await self._run(proposer)
        assert ok is False
        assert attest_calls == [], "gossip attestations must not be collected for a bad certificate"

    async def test_invalid_certificate_refuses_before_gossip(self):
        proposer = _poa_proposer()
        _wire_proposer(proposer, _RecordingPbft(_quorum(senders=(ADDR1, ADDR2))))
        ok, _metadata, attest_calls = await self._run(proposer)
        assert ok is False
        assert attest_calls == []

    async def test_mixed_view_certificate_refuses(self):
        proposer = _poa_proposer()
        cert = _quorum(view=VIEW, senders=(ADDR1, ADDR2, ADDR3)) + [_commit(ADDR4, KEY4, view=7)]
        _wire_proposer(proposer, _RecordingPbft(cert))
        ok, _metadata, attest_calls = await self._run(proposer)
        assert ok is False
        assert attest_calls == []

    async def test_matching_strict_certificate_passes(self):
        proposer = _poa_proposer()
        pbft = _make_pbft()
        _seed_commits(pbft, {(HEIGHT, VIEW): [ADDR1, ADDR2, ADDR3]})
        _wire_proposer(proposer, pbft)
        ok, metadata, attest_calls = await self._run(proposer)
        assert ok is True
        assert attest_calls, "a valid certificate proceeds to normal attestation collection"
        assert metadata["pbft_certificate"]
        assert {m["view_number"] for m in metadata["pbft_certificate"]} == {VIEW}

    async def test_requested_view_wins_over_higher_complete_view(self):
        """Complete quórums at view 3 AND view 7: ``round_number=3`` must
        return the view-3 certificate — the producer is asked for THIS
        round's view, not the highest complete group."""
        proposer = _poa_proposer()
        pbft = _make_pbft()
        _seed_commits(
            pbft,
            {
                (HEIGHT, VIEW): [ADDR1, ADDR2, ADDR3],
                (HEIGHT, 7): [ADDR1, ADDR2, ADDR3],
            },
        )
        _wire_proposer(proposer, pbft)
        ok, metadata, attest_calls = await self._run(proposer, round_number=VIEW)
        assert ok is True
        assert attest_calls
        cert = metadata["pbft_certificate"]
        assert {m["view_number"] for m in cert} == {VIEW}
        assert len(cert) == 3

    async def test_wrong_expected_view_refuses(self):
        proposer = _poa_proposer()
        pbft = _make_pbft()
        _seed_commits(pbft, {(HEIGHT, 7): [ADDR1, ADDR2, ADDR3]})
        _wire_proposer(proposer, pbft)
        # The round this node ran is VIEW=3; the only complete group is view 7.
        ok, _metadata, attest_calls = await self._run(proposer, round_number=VIEW)
        assert ok is False
        assert attest_calls == []

    async def test_prethreshold_ignores_certificate_validity(self, monkeypatch):
        """Gate unset: the legacy path is untouched — even an empty certificate
        does not stop the attestation gate."""
        monkeypatch.setattr(settings, "pbft_certificate_strict_height", None)
        proposer = _poa_proposer()
        _wire_proposer(proposer, _RecordingPbft([]))
        ok, _metadata, attest_calls = await self._run(proposer)
        assert ok is True
        assert attest_calls

    async def test_strict_era_rejects_missing_round_number(self):
        """#1940 F3-B: ``round_number=None`` must NOT degrade to the
        highest-view certificate — the strict era pins THIS round's view,
        and a proposal with no derivable round cannot produce a valid one."""
        proposer = _poa_proposer()
        pbft = _make_pbft()
        # A complete quorum exists — at view 7, NOT the round this node ran.
        # Before the fix the unpinned call returned it happily.
        _seed_commits(pbft, {(HEIGHT, 7): [ADDR1, ADDR2, ADDR3]})
        _wire_proposer(proposer, pbft)
        ok, _metadata, attest_calls = await self._run(proposer, round_number=None)
        assert ok is False
        assert attest_calls == []

    async def test_prethreshold_tolerates_missing_round_number(self, monkeypatch):
        """Legacy era keeps tolerating ``round_number=None`` — the view
        argument is only meaningful under the strict contract."""
        monkeypatch.setattr(settings, "pbft_certificate_strict_height", None)
        proposer = _poa_proposer()
        _wire_proposer(proposer, _RecordingPbft([]))
        ok, _metadata, attest_calls = await self._run(proposer, round_number=None)
        assert ok is True
        assert attest_calls


# ---------------------------------------------------------------------------
# Importer — ProposerSignatureValidator under the strict gate
# ---------------------------------------------------------------------------


def _make_block_hash(chain_id: str, height: int, parent_hash: str, timestamp) -> str:
    payload = f"{chain_id}|{height}|{parent_hash}|{timestamp.isoformat()}".encode()
    return "0x" + hashlib.sha256(payload).hexdigest()


def _import_block_hash(height: int = HEIGHT, chain_id: str = CHAIN) -> str:
    """The deterministic hash ``_import_block`` seals — commit records must bind to it."""
    from datetime import UTC, datetime

    ts = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
    return _make_block_hash(chain_id, height, "0x00", ts)


def _import_block(
    certificate: list[dict[str, Any]] | None,
    *,
    height: int = HEIGHT,
    chain_id: str = CHAIN,
    metadata_override: str | None = None,
) -> dict[str, Any]:
    """A fully-signed importable block whose metadata carries ``certificate``.

    ``metadata_override`` replaces ``block_metadata`` verbatim — for raw
    JSON shapes (empty string, deep nesting, non-object JSON) that
    ``json.dumps`` of a dict cannot express.
    """
    from datetime import UTC, datetime

    ts = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
    block_hash = _import_block_hash(height, chain_id)
    header = {
        "chain_id": chain_id,
        "height": height,
        "hash": block_hash,
        "parent_hash": "0x00",
        "proposer": ADDR1,
        "state_root": "0x" + "11" * 32,
        "bridge_state_root": "0x" + "22" * 32,
    }
    metadata: dict[str, Any] = {}
    if certificate is not None:
        metadata["pbft_certificate"] = certificate
    return {
        **header,
        "timestamp": ts.isoformat(),
        "signature": sign_block_hash(header, KEY1),
        "block_metadata": metadata_override if metadata_override is not None else json.dumps(metadata),
    }


def _arm_importer(
    monkeypatch,
    *,
    min_attestations: int,
    strict_height,
    pbft_enabled: bool = False,
    multivalidator: bool = True,
    configured_set: bool = True,
) -> None:
    monkeypatch.setattr(settings, "multi_validator_consensus_enabled", multivalidator)
    monkeypatch.setattr(settings, "multi_validator_min_attestations", min_attestations)
    monkeypatch.setattr(
        settings,
        "validator_set",
        json.dumps([{"address": a} for a in MEMBERS]) if configured_set else "",
    )
    monkeypatch.setattr(settings, "pbft_certificate_strict_height", strict_height)
    monkeypatch.setattr(settings, "pbft_consensus_enabled", pbft_enabled)


class TestImporterStrictCertificate:
    def test_strict_rejects_two_vote_certificate(self, monkeypatch):
        """n=4 quorum is 3: a 2-commit certificate the legacy min=2 counter
        accepts must fail under the strict contract."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=2, strict_height=HEIGHT)
        cert = _quorum(senders=(ADDR1, ADDR2), block_hash=_import_block_hash())
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(cert))
        assert not ok
        assert "commits" in reason or "valid" in reason

    def test_strict_rejects_mixed_view_union(self, monkeypatch):
        """2+2 commits across two views: legacy counts 4 distinct senders and
        accepts; strict rejects the mixed certificate outright."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=2, strict_height=HEIGHT)
        bh = _import_block_hash()
        cert = _quorum(view=VIEW, senders=(ADDR1, ADDR2), block_hash=bh) + _quorum(
            view=7, senders=(ADDR3, ADDR4), block_hash=bh
        )
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(cert))
        assert not ok

    def test_strict_accepts_full_quorum(self, monkeypatch):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=2, strict_height=HEIGHT)
        ok, reason = ProposerSignatureValidator().validate_block_signature(
            _import_block(_quorum(block_hash=_import_block_hash()))
        )
        assert ok, reason

    def test_min_zero_still_enforces_certificate_in_strict_era(self, monkeypatch):
        """``min_attestations=0`` must not bypass a carried certificate: the
        early 'No attestations required' return is strict-era aware."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=0, strict_height=HEIGHT)
        weak = _quorum(senders=(ADDR1, ADDR2), block_hash=_import_block_hash())
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(weak))
        assert not ok, "weak certificate must be enforced even at min_attestations=0"

    def test_min_zero_non_pbft_block_unaffected_in_strict_era(self, monkeypatch):
        """A block with no pbft_certificate keeps 'No attestations required'."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=0, strict_height=HEIGHT)
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(None))
        assert ok, reason

    def test_min_zero_valid_certificate_accepted_in_strict_era(self, monkeypatch):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=0, strict_height=HEIGHT)
        ok, reason = ProposerSignatureValidator().validate_block_signature(
            _import_block(_quorum(block_hash=_import_block_hash()))
        )
        assert ok, reason

    @pytest.mark.parametrize("strict_height", [None, HEIGHT + 1])
    def test_prethreshold_preserves_legacy_two_vote_acceptance(self, monkeypatch, strict_height):
        """Unset or below-threshold: the legacy counter still accepts a
        2-commit certificate against min_attestations=2 — byte-equivalent."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=2, strict_height=strict_height)
        cert = _quorum(senders=(ADDR1, ADDR2), block_hash=_import_block_hash())
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(cert))
        assert ok, reason


class TestImporterStrictPbftEnabled:
    """``pbft_consensus_enabled`` + strict era: the commit certificate is
    MANDATORY — a proposer cannot omit it and fall back to a gossip
    attestation quorum, and malformed metadata can never reach the legacy
    attestation path."""

    @pytest.mark.parametrize("min_attestations", [0, 2])
    def test_missing_certificate_key_rejects(self, monkeypatch, min_attestations):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=min_attestations, strict_height=HEIGHT, pbft_enabled=True)
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(None))
        assert not ok
        assert "pbft_certificate" in reason

    @pytest.mark.parametrize("min_attestations", [0, 2])
    def test_missing_metadata_rejects(self, monkeypatch, min_attestations):
        """Empty ``block_metadata`` is itself a rejection when PBFT is armed —
        even at ``min_attestations=0``."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=min_attestations, strict_height=HEIGHT, pbft_enabled=True)
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(None, metadata_override=""))
        assert not ok
        assert "block_metadata" in reason

    @pytest.mark.parametrize("min_attestations", [0, 2])
    def test_nonobject_metadata_rejects(self, monkeypatch, min_attestations):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=min_attestations, strict_height=HEIGHT, pbft_enabled=True)
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(None, metadata_override="[1, 2, 3]"))
        assert not ok
        assert "JSON object" in reason

    @pytest.mark.parametrize("min_attestations", [0, 2])
    def test_nonlist_certificate_rejects(self, monkeypatch, min_attestations):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=min_attestations, strict_height=HEIGHT, pbft_enabled=True)
        ok, reason = ProposerSignatureValidator().validate_block_signature(
            _import_block(None, metadata_override=json.dumps({"pbft_certificate": {"not": "a list"}}))
        )
        assert not ok
        assert "not a list" in reason

    @pytest.mark.parametrize("min_attestations", [0, 2])
    def test_unsigned_certificate_list_rejects(self, monkeypatch, min_attestations):
        """A certificate-shaped list without valid commit signatures fails
        the shared strict verifier — not the attestation counter."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=min_attestations, strict_height=HEIGHT, pbft_enabled=True)
        garbage = [{"message_type": "commit", "sender": ADDR1, "signature": "0x00"}]
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(garbage))
        assert not ok
        assert "valid" in reason.lower() or "commit" in reason.lower()

    @pytest.mark.parametrize("min_attestations", [0, 2])
    def test_deep_json_metadata_rejects_without_raising(self, monkeypatch, min_attestations):
        """Pathologically nested JSON raises ``RecursionError`` inside the
        parser — the strict-era gate must catch it and reject, never let it
        escape ``_validate_attestations``."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=min_attestations, strict_height=HEIGHT, pbft_enabled=True)
        deep = "[" * 100_000 + "]" * 100_000
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(None, metadata_override=deep))
        assert not ok
        assert "block_metadata" in reason

    @pytest.mark.parametrize("min_attestations", [0, 2])
    def test_valid_certificate_accepted(self, monkeypatch, min_attestations):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=min_attestations, strict_height=HEIGHT, pbft_enabled=True)
        ok, reason = ProposerSignatureValidator().validate_block_signature(
            _import_block(_quorum(block_hash=_import_block_hash()))
        )
        assert ok, reason

    def test_deep_json_pbft_off_defers_to_legacy_without_raising(self, monkeypatch):
        """PBFT off: the early helper returns ``None`` on unparseable metadata
        and the legacy 'No attestations required' answer stands at min=0 —
        the ``RecursionError`` never escapes the new helper."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=0, strict_height=HEIGHT, pbft_enabled=False)
        deep = "[" * 100_000 + "]" * 100_000
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(None, metadata_override=deep))
        assert ok, reason

    def test_pbft_off_noncert_block_uses_normal_attestation_path(self, monkeypatch):
        """PBFT off + strict era + no ``pbft_certificate`` key: the helper
        returns ``None`` and the block is judged by the ordinary attestation
        rules — 'Insufficient attestations', never a certificate verdict."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=2, strict_height=HEIGHT, pbft_enabled=False)
        ok, reason = ProposerSignatureValidator().validate_block_signature(_import_block(None))
        assert not ok
        assert "ttestation" in reason


class TestImporterStrictPbftGateBypass:
    """#1940 F3: ``validate_block_signature`` only enters the multi-validator
    attestation gate when BOTH ``multi_validator_consensus_enabled`` and a
    non-empty ``validator_set`` are configured. With PBFT armed + strict era
    the mandatory certificate must still be enforced on that outer path —
    ``_trusted`` members feed the verifier when no set is configured."""

    @pytest.mark.parametrize("multivalidator,configured_set", [(False, True), (True, False)])
    def test_weak_certificate_rejects(self, monkeypatch, multivalidator, configured_set):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(
            monkeypatch,
            min_attestations=0,
            strict_height=HEIGHT,
            pbft_enabled=True,
            multivalidator=multivalidator,
            configured_set=configured_set,
        )
        weak = _quorum(senders=(ADDR1, ADDR2), block_hash=_import_block_hash())
        ok, reason = ProposerSignatureValidator(trusted_proposers=MEMBERS).validate_block_signature(_import_block(weak))
        assert not ok
        assert "commit" in reason.lower() or "valid" in reason.lower()

    @pytest.mark.parametrize("multivalidator,configured_set", [(False, True), (True, False)])
    def test_missing_certificate_rejects(self, monkeypatch, multivalidator, configured_set):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(
            monkeypatch,
            min_attestations=0,
            strict_height=HEIGHT,
            pbft_enabled=True,
            multivalidator=multivalidator,
            configured_set=configured_set,
        )
        ok, reason = ProposerSignatureValidator(trusted_proposers=MEMBERS).validate_block_signature(_import_block(None))
        assert not ok
        assert "pbft_certificate" in reason

    @pytest.mark.parametrize("multivalidator,configured_set", [(False, True), (True, False)])
    def test_valid_certificate_accepts(self, monkeypatch, multivalidator, configured_set):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(
            monkeypatch,
            min_attestations=0,
            strict_height=HEIGHT,
            pbft_enabled=True,
            multivalidator=multivalidator,
            configured_set=configured_set,
        )
        ok, reason = ProposerSignatureValidator(trusted_proposers=MEMBERS).validate_block_signature(
            _import_block(_quorum(block_hash=_import_block_hash()))
        )
        assert ok, reason

    def test_no_configured_or_trusted_members_cannot_accept(self, monkeypatch):
        """Strict era + PBFT on but NO validator members anywhere — even a
        fully valid 3-commit certificate cannot verify against an empty
        canonical set."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(
            monkeypatch,
            min_attestations=0,
            strict_height=HEIGHT,
            pbft_enabled=True,
            multivalidator=False,
            configured_set=False,
        )
        ok, reason = ProposerSignatureValidator().validate_block_signature(
            _import_block(_quorum(block_hash=_import_block_hash()))
        )
        assert not ok
        assert "validator set" in reason


# ---------------------------------------------------------------------------
# Importer — #1940 F3-B certificate view binding
# ---------------------------------------------------------------------------


def _parent_ts_for_round(round_number: int):
    """A parent timestamp that derives ``round_number`` for the fixed
    ``_import_block`` timestamp under the default 60s proposer window."""
    from datetime import UTC, datetime, timedelta

    block_ts = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)
    return block_ts - timedelta(seconds=(round_number * 60) + 30)


class TestImporterCertificateViewBinding:
    """``pbft_certificate_view_binding_height`` armed + strict era + PBFT on:
    the certificate's coherent view must equal the block's timestamp-derived
    proposer round — the same round the producer pins commits under."""

    def _validator(self, monkeypatch, *, round_number=VIEW, binding_height=HEIGHT, pbft_enabled=True):
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(
            monkeypatch,
            min_attestations=2,
            strict_height=HEIGHT,
            pbft_enabled=pbft_enabled,
        )
        monkeypatch.setattr(settings, "pbft_certificate_view_binding_height", binding_height)
        # Pin the round window so the derivation is deterministic.
        monkeypatch.setattr(settings, "consensus_proposer_round_seconds", 60)
        parent_ts = _parent_ts_for_round(round_number)
        return ProposerSignatureValidator(parent_timestamp_resolver=lambda parent_hash: parent_ts)

    def test_bound_view_matching_accepted(self, monkeypatch):
        """Positive: certificate view == derived proposer round -> accept."""
        validator = self._validator(monkeypatch)
        ok, reason = validator.validate_block_signature(_import_block(_quorum(view=VIEW, block_hash=_import_block_hash())))
        assert ok, reason

    def test_bound_view_mismatch_rejected(self, monkeypatch):
        """Negative: a coherent quorum at a DIFFERENT view is not this
        block's round — reject even though the certificate is otherwise valid."""
        validator = self._validator(monkeypatch)
        ok, reason = validator.validate_block_signature(_import_block(_quorum(view=7, block_hash=_import_block_hash())))
        assert not ok
        assert "expected view" in reason

    def test_underivable_round_rejects_pbft_block(self, monkeypatch):
        """PBFT on + binding armed + strict era: a block whose proposer round
        cannot be derived fails closed — the certificate cannot be bound."""
        from aitbc_chain.sync_validator import ProposerSignatureValidator

        _arm_importer(monkeypatch, min_attestations=2, strict_height=HEIGHT, pbft_enabled=True)
        monkeypatch.setattr(settings, "pbft_certificate_view_binding_height", HEIGHT)
        # No parent_timestamp_resolver -> _derive_attestation_round -> None.
        ok, reason = ProposerSignatureValidator().validate_block_signature(
            _import_block(_quorum(view=VIEW, block_hash=_import_block_hash()))
        )
        assert not ok
        assert "underivable" in reason

    def test_binding_gate_unset_keeps_unpinned_view(self, monkeypatch):
        """Pre-gate: with the binding height unset a coherent wrong-view
        certificate still passes the strict contract — byte-equivalent."""
        validator = self._validator(monkeypatch, binding_height=None)
        ok, reason = validator.validate_block_signature(_import_block(_quorum(view=7, block_hash=_import_block_hash())))
        assert ok, reason

    def test_binding_below_threshold_keeps_unpinned_view(self, monkeypatch):
        """Binding armed at a LATER height: this block is pre-binding and
        keeps the unpinned strict check."""
        validator = self._validator(monkeypatch, binding_height=HEIGHT + 1)
        ok, reason = validator.validate_block_signature(_import_block(_quorum(view=7, block_hash=_import_block_hash())))
        assert ok, reason

    def test_binding_armed_but_pbft_off_stays_unpinned(self, monkeypatch):
        """PBFT off + carried certificate: the binding gate was armed for
        the PBFT producer/importer pair, not for carried-certificate blocks —
        the unpinned strict check still applies."""
        validator = self._validator(monkeypatch, pbft_enabled=False)
        ok, reason = validator.validate_block_signature(_import_block(_quorum(view=7, block_hash=_import_block_hash())))
        assert ok, reason
