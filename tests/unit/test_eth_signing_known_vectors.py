"""Known-vector guards for the eth-* signing family (DEPS-3).

These lock deterministic outputs of the pinned signing stack
(anyio, eth-account, eth-keyfile, eth-rlp, hexbytes) so a future
dependency bump that silently changes raw transaction bytes, hashes,
signatures, or keyfile format fails loudly here instead of on a hub.
The key is the public ethereum-test-vector key #2 (Hardhat account #1),
with no funds anywhere.
"""

import json

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys import keys as eth_keys
from eth_utils import keccak

# Public ethereum-test-vector key #2 — the well-known Hardhat account #1.
KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
ADDRESS = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


def test_eip191_sign_and_recover() -> None:
    acct = Account.from_key(KEY)
    msg = encode_defunct(text="aitbc deps3 vector")
    sig = acct.sign_message(msg)
    assert sig.signature.hex() == (
        "9cbe7c6eb2262cda08223ac0818b9bb63e012292d06f0d9b55160f9f5187a755"
        "348a4909324d82a0651134787e278d057ea8e96516d85c0856228dfc89e2bb5b1b"
    )
    assert Account.recover_message(msg, signature=sig.signature) == ADDRESS


def test_unsafe_sign_hash_vector() -> None:
    """aitbc/crypto/crypto.py signs bare digests via unsafe_sign_hash."""
    sig = Account.from_key(KEY).unsafe_sign_hash(bytes.fromhex("aa" * 32))
    assert sig.signature.hex() == (
        "2bb53e516cc84ff133fcc4375ad466d8fff90c38b53bd841a1f15648f6e3bfd3"
        "0060b9f1cc61e91b8b352d28f295ac5d463f1988d3b5551bdbe5f0501d9b5ce71b"
    )
    assert sig.v == 27


def test_legacy_release_tx_vector() -> None:
    """The bridge release path signs legacy gasPrice transactions."""
    tx = {
        "to": ADDRESS,
        "value": 123456789,
        "gas": 21000,
        "gasPrice": 20_000_000_000,
        "nonce": 7,
        "chainId": 11155111,
    }
    signed = Account.from_key(KEY).sign_transaction(dict(tx))
    assert signed.hash.hex() == "fc48e515d1a08c876ed2ea6bcdfffe4ba039d8c7b98e8be2b9ec51d1aa949595"
    assert signed.raw_transaction.hex() == (
        "f86c078504a817c8008252089470997970c51812dc3a010c7d01b50e0d17dc79c8"
        "84075bcd15808401546d71a0a304ca332dd2deebcacc206f41c20e398b0dda4e6a0"
        "455b0cbe458c13d161767a01582c9dbf1302af54081751d789479fef85c371e8a5f"
        "68261b7de85908d62069"
    )


def test_eip1559_sepolia_tx_vector() -> None:
    tx = {
        "to": "0x52908400098527886E0F7030069857D2E4169EE7",
        "value": 424242,
        "gas": 53000,
        "maxFeePerGas": 30_000_000_000,
        "maxPriorityFeePerGas": 1_500_000_000,
        "nonce": 3,
        "chainId": 11155111,
        "type": 2,
        "accessList": [],
    }
    signed = Account.from_key(KEY).sign_transaction(dict(tx))
    assert signed.hash.hex() == "c73135fa3efd02bca3d4708346595de6291002b108d95ea47944af7b11bc02da"
    assert signed.raw_transaction.hex() == (
        "02f87183aa36a7038459682f008506fc23ac0082cf089452908400098527886e0f"
        "7030069857d2e4169ee78306793280c001a0a16a3644b77c6a45b4c26838673f7f5"
        "570f592e63253f2c08bd4ab9b9619e7c9a0617256ab550f1fcffd4b2a836e1b944"
        "362c8b36c659a430b7b058ec69e8bf643"
    )


def test_keyfile_round_trip() -> None:
    enc = Account.encrypt(KEY, "deps3-vector-pw")
    crypto = enc.get("crypto", enc.get("Crypto", {}))
    assert enc.get("version") == 3
    assert crypto.get("kdf") == "scrypt"
    assert ("0x" + Account.decrypt(enc, "deps3-vector-pw").hex()) == KEY


def test_eth_keys_canonical_json_signature() -> None:
    """Ops-signer pattern: sign_msg_hash over keccak of canonical JSON."""
    tx = {
        "type": "TRANSFER",
        "chain_id": "ait-localnet",
        "from": "0xA",
        "to": "0xB",
        "amount": 5,
        "nonce": 1,
        "fee": 1,
        "payload": {"amount": 5},
    }
    digest = keccak(json.dumps(tx, sort_keys=True, separators=(",", ":")).encode())
    sig = eth_keys.PrivateKey(bytes.fromhex(KEY[2:])).sign_msg_hash(digest)
    assert sig.to_bytes().hex() == (
        "d41ef1a0d5b543302c45cab796d7c417d066679d51330aca33d404228e71b2f564"
        "d1063753b1f47828a08f24b27b73ba93a85c3a085be8b91331ca7abd309ab200"
    )
    assert eth_keys.PrivateKey(bytes.fromhex(KEY[2:])).public_key.to_checksum_address() == ADDRESS
