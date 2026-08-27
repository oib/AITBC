"""The genesis key and address must match and the address must be a valid 0x form (V23-63).

The hub now stores and sends only EIP-55 secp256k1/EVM addresses. The genesis
address configured in the environment must be the ``0x`` form of the key that
signs the transaction, otherwise the node will reject the signature.
"""

from __future__ import annotations

import pytest

from aitbc.crypto.signature_recovery import canonical_address
from aitbc.crypto.transaction_service import TransactionService

eth_keys = pytest.importorskip("eth_keys", reason="secp256k1 signing not available")

# The hub's treasury key, as it was actually configured. Not a secret: this is the
# well-known genesis account of a test island, and only the address appears here.
PRIVATE_KEY = "0x" + "11" * 32


@pytest.fixture
def derived_address() -> str:
    from eth_keys import keys

    return str(keys.PrivateKey(bytes.fromhex(PRIVATE_KEY.removeprefix("0x"))).public_key.to_checksum_address())


@pytest.fixture
def service(monkeypatch):
    def _build(address: str) -> TransactionService:
        monkeypatch.setenv("GENESIS_PRIVATE_KEY", PRIVATE_KEY)
        monkeypatch.setenv("GENESIS_ADDRESS", address)
        monkeypatch.setenv("CHAIN_ID", "ait-test")
        built = TransactionService()
        monkeypatch.setattr(built, "get_nonce", lambda _address: 7)
        return built

    return _build


@pytest.mark.parametrize("spelling", ["checksummed", "lowercase", "uppercase"])
def test_every_spelling_of_the_right_address_signs(service, derived_address, spelling: str) -> None:
    """A 0x address in any valid hexadecimal spelling names the same account."""
    address = {
        "checksummed": derived_address,
        "lowercase": derived_address.lower(),
        "uppercase": derived_address.upper().replace("0X", "0x"),
    }[spelling]

    transaction = service(address).generate_signed_transaction(to_address="0x" + "ab" * 20, amount=100, fee=10)

    assert transaction is not None
    assert transaction["signature"]


def test_a_genuinely_different_address_still_fails_closed(service) -> None:
    """Widening the comparison must not stop it rejecting a real mismatch."""
    from eth_keys import keys

    other = keys.PrivateKey(bytes.fromhex("22" * 32)).public_key.to_checksum_address()

    assert service(other).generate_signed_transaction(to_address="0x" + "ab" * 20, amount=100, fee=10) is None
    assert service(other.lower()).generate_signed_transaction("0x" + "ab" * 20, 100, 10) is None


def test_the_configured_spelling_is_what_goes_on_the_wire(service, derived_address) -> None:
    """`from` and `to` are canonical 0x addresses so the node can look them up."""
    configured = derived_address.lower()

    transaction = service(configured).generate_signed_transaction(to_address="0x" + "ab" * 20, amount=100, fee=10)

    assert transaction is not None
    assert transaction["from"] == canonical_address(configured)
    assert transaction["to"] == canonical_address("0x" + "ab" * 20)


def test_the_nonce_is_fetched_for_the_canonical_address(monkeypatch, derived_address) -> None:
    """The nonce lookup uses the same canonical 0x address that goes on the wire."""
    configured = derived_address.lower()
    monkeypatch.setenv("GENESIS_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setenv("GENESIS_ADDRESS", configured)
    built = TransactionService()

    asked: list[str] = []
    monkeypatch.setattr(built, "get_nonce", lambda address: asked.append(address) or 7)
    built.generate_signed_transaction(to_address="0x" + "ab" * 20, amount=100, fee=10)

    assert asked == [canonical_address(configured)]


def test_the_signature_verifies_against_the_canonical_address(service, derived_address) -> None:
    """End to end against the node's own verifier, which is the only check that counts."""
    verify = pytest.importorskip(
        "aitbc_chain.rpc.utils", reason="blockchain-node not importable from the root suite"
    ).verify_transaction_signature

    configured = derived_address.lower()
    transaction = service(configured).generate_signed_transaction(to_address="0x" + "ab" * 20, amount=100, fee=10)
    signature = transaction.pop("signature")

    assert verify(transaction, signature, canonical_address(configured))
    assert canonical_address(configured) == canonical_address(derived_address)
