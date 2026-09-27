"""Chain binding of consensus signatures.

Block and attestation signatures are secp256k1 over the keccak256 of a
canonical-JSON header that contains ``chain_id`` (see
``aitbc.crypto.consensus_signing._block_header_message`` and
``RemoteAttestationService._handle_request``). A signature minted for one
chain must therefore never verify against another chain's header — the
property that keeps a retired or parallel chain (e.g. the legacy
``ait-hub1.aitbc.bubuit.net`` data dir on hub1) from replaying signatures
onto ``ait-hub.aitbc.bubuit.net``, where the same validator keys are used.

The verifier also falls back to a legacy raw-block-hash check
(``verify_block_signature``). That fallback is still hash-bound: a
canonical-header signature never validates under it, so the same-hash
worst case — two chains holding a block with an identical hash — stays
safe.
"""

from __future__ import annotations

from aitbc.crypto.consensus_signing import sign_block_hash, sign_consensus_message, verify_block_signature

# Test-only key material: a fixed, well-known throwaway scalar. It
# authenticates nothing and exists solely so the tests can produce real
# secp256k1 signatures.
_TEST_PRIVATE_KEY = "0x" + "11" * 32
_CHAIN_A = "ait-hub.aitbc.bubuit.net"
_CHAIN_B = "ait-hub1.aitbc.bubuit.net"


def _proposer_address() -> str:
    from eth_keys import keys

    return keys.PrivateKey(bytes.fromhex(_TEST_PRIVATE_KEY[2:])).public_key.to_checksum_address()


def _header(chain_id: str, block_hash: str = "0x" + "ab" * 32) -> dict:
    return {
        "chain_id": chain_id,
        "height": 100,
        "hash": block_hash,
        "parent_hash": "0x" + "cd" * 32,
        "proposer": _proposer_address(),
        "state_root": "0x" + "bb" * 32,
        "bridge_state_root": "0x" + "00" * 32,
    }


class TestBlockSignatureChainBinding:
    def test_same_chain_verifies(self):
        header = _header(_CHAIN_A)
        sig = sign_block_hash(header, _TEST_PRIVATE_KEY)
        assert verify_block_signature(header, sig, _proposer_address()) is True

    def test_other_chain_rejected(self):
        """A signature over chain A's header must not verify for chain B."""
        header_a = _header(_CHAIN_A)
        sig = sign_block_hash(header_a, _TEST_PRIVATE_KEY)
        header_b = _header(_CHAIN_B)
        header_b["hash"] = header_a["hash"]  # same height, same hash — worst case
        assert verify_block_signature(header_b, sig, _proposer_address()) is False

    def test_signatures_differ_across_chains(self):
        """Same block content, different chain_id → different signature."""
        sig_a = sign_block_hash(_header(_CHAIN_A), _TEST_PRIVATE_KEY)
        sig_b = sign_block_hash(_header(_CHAIN_B), _TEST_PRIVATE_KEY)
        assert sig_a != sig_b


class TestAttestationChainBinding:
    """Attestations sign the same canonical header shape — same binding."""

    def test_attestation_message_rejected_on_other_chain(self):
        header_a = _header(_CHAIN_A)
        sig = sign_consensus_message(header_a, _TEST_PRIVATE_KEY)
        # Proposer-side verify path uses verify_block_signature(header, sig, validator)
        assert verify_block_signature(header_a, sig, _proposer_address()) is True
        assert verify_block_signature(_header(_CHAIN_B), sig, _proposer_address()) is False
