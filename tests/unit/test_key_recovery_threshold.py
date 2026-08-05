"""Threshold guarantees for aitbc.crypto.key_recovery (CORE-16).

The escrow previously used an XOR n-of-n split while accepting and validating a
``shares_required`` threshold. Recovering with exactly ``shares_required`` shares out of a
larger total XOR'd a subset and returned wrong key material **with no error**, which the
caller would then use as a key.

These tests pin the properties that make the threshold real: any k of n reconstruct, any
fewer refuse, and a caller cannot argue the threshold down.
"""

from __future__ import annotations

import itertools
from os import urandom

import pytest
from aitbc.crypto.errors import CryptoError
from aitbc.crypto.key_recovery import (
    RecoveryShare,
    escrow_key,
    recover_key,
)
from aitbc.crypto.key_recovery import (
    _gf_div,
    _gf_mul,
    _GF_EXP,
    _interpolate_at_zero,
)


class TestFieldArithmetic:
    """GF(2**8) must be a field, or every guarantee above it is void."""

    def test_tables_are_a_bijection(self):
        """A non-generator (2 has order 51, not 255) produces a table that silently lies."""
        assert sorted(_GF_EXP[:255]) == list(range(1, 256))

    def test_one_is_the_multiplicative_identity(self):
        assert all(_gf_mul(1, x) == x for x in range(256))

    def test_division_inverts_multiplication(self):
        assert all(_gf_div(_gf_mul(a, b), b) == a for a in range(1, 256) for b in range(1, 256))

    def test_multiplication_is_commutative(self):
        assert all(_gf_mul(a, b) == _gf_mul(b, a) for a in range(256) for b in range(0, 256, 7))

    def test_division_by_zero_is_rejected(self):
        with pytest.raises(CryptoError):
            _gf_div(5, 0)

    def test_interpolation_recovers_the_constant_term(self):
        def evaluate(x: int, coefficients: list[int]) -> int:
            y = 0
            for coefficient in reversed(coefficients):
                y = _gf_mul(y, x) ^ coefficient
            return y

        coefficients = [99, 13, 200]
        for xs in [(1, 2, 3), (2, 4, 5), (3, 7, 200)]:
            points = [(x, evaluate(x, coefficients)) for x in xs]
            assert _interpolate_at_zero(points) == 99


class TestThresholdRecovery:
    def test_any_k_of_n_reconstructs(self):
        """Every 3-subset of 5 must give the key back -- not just the first three."""
        key = urandom(32)
        escrow = escrow_key("esc", "key", key, shares_total=5, shares_required=3)

        for subset in itertools.combinations(escrow.shares, 3):
            assert recover_key(list(subset)) == key

    @pytest.mark.parametrize(("total", "required"), [(2, 2), (3, 2), (5, 3), (10, 4), (16, 16)])
    def test_thresholds_across_shapes(self, total: int, required: int):
        key = urandom(32)
        escrow = escrow_key("esc", "key", key, shares_total=total, shares_required=required)

        assert recover_key(escrow.shares[:required]) == key

    @pytest.mark.parametrize("size", [1, 16, 32, 64, 257])
    def test_key_sizes(self, size: int):
        key = urandom(size)
        escrow = escrow_key("esc", "key", key, shares_total=5, shares_required=3)

        assert recover_key(escrow.shares[:3]) == key

    def test_key_with_zero_bytes_roundtrips(self):
        """Zero bytes exercise the a==0 branches in the field arithmetic."""
        key = bytes(16) + b"\xff" * 16
        escrow = escrow_key("esc", "key", key, shares_total=4, shares_required=2)

        assert recover_key(escrow.shares[:2]) == key


class TestThresholdIsEnforced:
    def test_fewer_than_k_shares_refuse(self):
        key = urandom(32)
        escrow = escrow_key("esc", "key", key, shares_total=5, shares_required=3)

        for count in (1, 2):
            with pytest.raises(CryptoError, match="not enough shares"):
                recover_key(escrow.shares[:count])

    def test_caller_cannot_lower_the_threshold(self):
        """The threshold travels in the share; a smaller shares_required cannot override it.

        This is the exact call that used to return a wrong key silently.
        """
        key = urandom(32)
        escrow = escrow_key("esc", "key", key, shares_total=5, shares_required=3)

        with pytest.raises(CryptoError, match="not enough shares"):
            recover_key(escrow.shares[:2], shares_required=2)

    def test_omitting_shares_required_still_enforces(self):
        key = urandom(32)
        escrow = escrow_key("esc", "key", key, shares_total=5, shares_required=3)

        with pytest.raises(CryptoError, match="not enough shares"):
            recover_key(escrow.shares[:2])

    def test_a_higher_caller_threshold_is_honoured(self):
        """shares_required may tighten the requirement, just not loosen it."""
        key = urandom(32)
        escrow = escrow_key("esc", "key", key, shares_total=5, shares_required=2)

        with pytest.raises(CryptoError, match="not enough shares"):
            recover_key(escrow.shares[:3], shares_required=4)


class TestCorruptShares:
    def test_duplicate_shares_do_not_count_twice(self):
        key = urandom(32)
        escrow = escrow_key("esc", "key", key, shares_total=5, shares_required=3)

        with pytest.raises(CryptoError, match="duplicate"):
            recover_key([escrow.shares[0], escrow.shares[0], escrow.shares[1]])

    def test_shares_from_different_secrets_are_rejected(self):
        alpha = escrow_key("e1", "k1", b"SECRET-ALPHA-32-BYTES-LONG-PAD!!", shares_total=5, shares_required=3)
        bravo = escrow_key("e2", "k2", b"SECRET-BRAVO-32-BYTES-LONG-PAD!!", shares_total=5, shares_required=3)

        with pytest.raises(CryptoError, match="different secrets"):
            recover_key([alpha.shares[0], alpha.shares[1], bravo.shares[2]])

    def test_corrupt_share_body_fails_integrity(self):
        """A tampered share must fail loudly, not yield plausible-looking bytes."""
        escrow = escrow_key("esc", "key", urandom(32), shares_total=5, shares_required=3)
        good = escrow.shares[2]
        corrupt = RecoveryShare(share_id="x", escrow_id="esc", shard=good.shard[:6] + bytes(len(good.shard) - 6))

        with pytest.raises(CryptoError, match="integrity"):
            recover_key([escrow.shares[0], escrow.shares[1], corrupt])

    def test_truncated_shares_are_rejected(self):
        with pytest.raises(CryptoError):
            recover_key([RecoveryShare(share_id="s", escrow_id="e", shard=b"\x01\x02")])

    def test_mismatched_lengths_are_rejected(self):
        shares = [
            RecoveryShare(share_id="s1", escrow_id="e", shard=b"abcdefgh"),
            RecoveryShare(share_id="s2", escrow_id="e", shard=b"abcdefg"),
        ]
        with pytest.raises(CryptoError):
            recover_key(shares)


class TestSplitValidation:
    @pytest.mark.parametrize(
        ("total", "required"),
        [(1, 1), (5, 1), (3, 5), (256, 2)],
    )
    def test_invalid_shapes_are_rejected(self, total: int, required: int):
        with pytest.raises(ValueError):
            escrow_key("esc", "key", urandom(16), shares_total=total, shares_required=required)

    def test_empty_key_is_rejected(self):
        with pytest.raises(ValueError):
            escrow_key("esc", "key", b"", shares_total=3, shares_required=2)

    def test_shares_differ_from_each_other_and_from_the_key(self):
        key = b"A" * 32
        escrow = escrow_key("esc", "key", key, shares_total=5, shares_required=3)

        bodies = [share.shard[6:] for share in escrow.shares]
        assert len(set(bodies)) == len(bodies)
        assert key not in b"".join(bodies)

    def test_splitting_twice_gives_different_shares(self):
        """Fresh CSPRNG coefficients per split; identical shares would leak structure."""
        key = b"A" * 32
        first = escrow_key("esc", "key", key, shares_total=3, shares_required=2)
        second = escrow_key("esc", "key", key, shares_total=3, shares_required=2)

        assert [s.shard for s in first.shares] != [s.shard for s in second.shares]
        assert recover_key(first.shares[:2]) == recover_key(second.shares[:2]) == key
