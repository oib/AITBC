"""The genesis key and address may be spelled differently and still be the same key (V23-63).

The hub refused to sign anything, reporting:

    GENESIS_ADDRESS (ait1fe2d63fe87db282083b9159e5857cac788af9e03) does not match the
    secp256k1 address derived from GENESIS_PRIVATE_KEY (0xFe2d63FE87Db282083b9159e5857Cac788af9E03)

Those are the same twenty bytes. The forty hex characters are identical; only the prefix and
the checksum casing differ. The key was correct all along and the comparison was wrong —
`canonical_address` exists for exactly this and was added under V23-54 for the block proposer
check, but `TransactionService` never picked it up.

Which spelling goes on the wire matters separately. The node verifies `from` against the
recovered signer canonically, so either works there — but its account lookups are exact string
matches, so a transaction signed with the derived `0x` spelling asks for the nonce of an
address the chain has no row for.
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


def _legacy(checksummed: str) -> str:
    """The `ait1` spelling of an address the chain also writes as `0x…`."""
    return "ait1" + checksummed.removeprefix("0x").lower()


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


@pytest.mark.parametrize("spelling", ["checksummed", "lowercase", "ait1"])
def test_every_spelling_of_the_right_address_signs(service, derived_address, spelling: str) -> None:
    """The bug in one test: the `ait1` case returned None while naming the same account."""
    address = {
        "checksummed": derived_address,
        "lowercase": derived_address.lower(),
        "ait1": _legacy(derived_address),
    }[spelling]

    transaction = service(address).generate_signed_transaction(to_address="ait1" + "ab" * 20, amount=100, fee=10)

    assert transaction is not None
    assert transaction["signature"]


def test_a_genuinely_different_address_still_fails_closed(service) -> None:
    """Widening the comparison must not stop it rejecting a real mismatch."""
    from eth_keys import keys

    other = keys.PrivateKey(bytes.fromhex("22" * 32)).public_key.to_checksum_address()

    assert service(other).generate_signed_transaction(to_address="ait1" + "ab" * 20, amount=100, fee=10) is None
    assert service(_legacy(str(other))).generate_signed_transaction("ait1" + "ab" * 20, 100, 10) is None


def test_the_configured_spelling_is_what_goes_on_the_wire(service, derived_address) -> None:
    """`from` must be the address the chain has an account row for.

    The node compares `from` to the recovered signer canonically, so the `0x` form would
    verify — but `rpc/accounts.get_account` matches on the exact string, so signing as
    `0x…` when the account is stored as `ait1…` reads the nonce of an account that does
    not exist and the transfer debits nothing.
    """
    legacy = _legacy(derived_address)

    transaction = service(legacy).generate_signed_transaction(to_address="ait1" + "ab" * 20, amount=100, fee=10)

    assert transaction is not None
    assert transaction["from"] == legacy


def test_the_nonce_is_fetched_for_the_configured_spelling(monkeypatch, derived_address) -> None:
    """Same reason: a nonce looked up under the wrong spelling comes back 0 for a used account."""
    legacy = _legacy(derived_address)
    monkeypatch.setenv("GENESIS_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setenv("GENESIS_ADDRESS", legacy)
    built = TransactionService()

    asked: list[str] = []
    monkeypatch.setattr(built, "get_nonce", lambda address: asked.append(address) or 7)
    built.generate_signed_transaction(to_address="ait1" + "ab" * 20, amount=100, fee=10)

    assert asked == [legacy]


def test_the_signature_verifies_against_the_configured_spelling(service, derived_address) -> None:
    """End to end against the node's own verifier, which is the only check that counts."""
    verify = pytest.importorskip(
        "aitbc_chain.rpc.utils", reason="blockchain-node not importable from the root suite"
    ).verify_transaction_signature

    legacy = _legacy(derived_address)
    transaction = service(legacy).generate_signed_transaction(to_address="ait1" + "ab" * 20, amount=100, fee=10)
    signature = transaction.pop("signature")

    assert verify(transaction, signature, legacy)
    assert canonical_address(legacy) == canonical_address(derived_address)
