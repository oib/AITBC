"""One account, however it is spelled (V23-64).

`AccountAddress` normalises `0x…`, `ait1…` and `aitbc1…` to one lowercase `ait1` form on the
way into the database and on the way out, and `StateManager._encode_address` does the same for
trie keys. That closes the latent half of V23-63: account lookups were exact string matches, so
an account written in one spelling and queried in another read as absent — and on a chain that
moves money, "absent" means a zero balance and a nonce of 0.

The change arrived without tests. These are them. Two of the cases are the ones that would
actually cost something:

  - the state root must not move for a chain whose accounts are already canonical, because a
    root that moves invalidates every historical block;
  - `Escrow.buyer`/`provider` must still be foreign keys, which they briefly were not.
"""

from __future__ import annotations

import pytest
from sqlalchemy import ForeignKey, ForeignKeyConstraint
from sqlmodel import Session, create_engine, select

from aitbc_chain.metadata import chain_metadata

from aitbc_chain.base_models import Account, Escrow, _to_ait_address
from aitbc_chain.state.merkle_patricia_trie import StateManager

BODY = "fe2d63fe87db282083b9159e5857cac788af9e03"
SPELLINGS = [f"ait1{BODY}", f"0x{BODY}", f"0x{BODY.upper()}", f"aitbc1{BODY}", f"AIT1{BODY.upper()}"]


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    chain_metadata.create_all(engine)
    with Session(engine) as open_session:
        yield open_session


# --- The normalisation itself -----------------------------------------------------------


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_every_spelling_reduces_to_the_same_address(spelling: str) -> None:
    assert _to_ait_address(spelling) == f"ait1{BODY}"


@pytest.mark.parametrize("value", ["", "hub-coordinator", "genesis", "0xnothex", "ait1short", "0x" + "ab" * 21])
def test_anything_that_is_not_an_address_passes_through(value: str) -> None:
    """Proposer ids and aliases share these columns; mangling them would be worse than the bug."""
    assert _to_ait_address(value) == value.strip().lower()


def test_two_different_addresses_do_not_collapse(session) -> None:
    """The whole scheme rests on the mapping being one-to-one on the body."""
    other = "b" * 40
    assert _to_ait_address(f"0x{BODY}") != _to_ait_address(f"0x{other}")


# --- Through the database ---------------------------------------------------------------


@pytest.mark.parametrize("written", SPELLINGS)
@pytest.mark.parametrize("queried", SPELLINGS)
def test_an_account_written_in_any_spelling_is_found_by_any_other(session, written: str, queried: str) -> None:
    session.add(Account(chain_id="ait-test", address=written, balance=3_599_999_999_890, nonce=1))
    session.commit()

    found = session.exec(select(Account).where(Account.address == queried)).first()

    assert found is not None
    assert found.balance == 3_599_999_999_890
    assert found.address == f"ait1{BODY}"


def test_the_same_account_cannot_be_stored_twice_under_two_spellings(session) -> None:
    """Without normalisation these are two rows, and a balance splits across them."""
    session.add(Account(chain_id="ait-test", address=f"ait1{BODY}", balance=100, nonce=0))
    session.commit()
    session.add(Account(chain_id="ait-test", address=f"0x{BODY}", balance=999, nonce=0))

    with pytest.raises(Exception):  # noqa: B017 - the dialect chooses the integrity error type
        session.commit()


def test_escrow_still_references_the_account_table(session) -> None:
    """`foreign_key=` passed to `Column` is read as a dialect option and silently dropped."""
    targets = sorted(str(fk.target_fullname) for fk in Escrow.__table__.foreign_keys)

    assert targets == ["account.address", "account.address", "account.chain_id", "account.chain_id"]
    for name in ("buyer", "provider"):
        column = Escrow.__table__.c[name]
        assert column.foreign_keys, f"{name} lost its foreign key"
        assert all(isinstance(fk, ForeignKey) for fk in column.foreign_keys)
        # The failure mode was silent: the constraint vanished into a dialect option
        # bucket rather than raising, so assert the bucket is empty too.
        assert not dict(column.dialect_options.get("foreign", {}) or {}).get("key")


def test_escrow_foreign_keys_reference_the_whole_account_key(session) -> None:
    """A reference to `account.address` alone is unusable: the key is `(chain_id, address)`.

    SQLite does not complain when such a table is created -- it fails later, and it fails
    globally: `PRAGMA foreign_key_check` reports "foreign key mismatch" and checks no table
    in the database at all.
    """
    constraints = {c.name: c for c in Escrow.__table__.constraints if isinstance(c, ForeignKeyConstraint)}

    assert set(constraints) == {"fk_escrow_buyer_account", "fk_escrow_provider_account"}
    for name, local in (("fk_escrow_buyer_account", "buyer"), ("fk_escrow_provider_account", "provider")):
        constraint = constraints[name]
        assert [c.name for c in constraint.columns] == ["chain_id", local]
        assert [e.column.name for e in constraint.elements] == ["chain_id", "address"]

    account_key = [c.name for c in Account.__table__.primary_key.columns]
    assert account_key == ["chain_id", "address"], "the escrow constraints track this key"


# --- Through the state trie -------------------------------------------------------------


class _Account:
    def __init__(self, balance: int, nonce: int) -> None:
        self.balance, self.nonce = balance, nonce


@pytest.mark.parametrize("spelling", SPELLINGS)
def test_the_trie_key_is_the_same_for_every_spelling(spelling: str) -> None:
    assert StateManager()._encode_address(spelling) == f"ait1{BODY}".encode()


def test_the_state_root_does_not_move_for_an_already_canonical_chain() -> None:
    """The one that would be expensive to get wrong.

    Trie keys feed the state root, and the state root is recorded in every block. If
    normalisation changed the key for accounts that are already `ait1`, every historical
    block would fail verification and the node would diverge from its peers. It does not,
    because `_to_ait_address` is the identity on an address already in that form — but that
    is a property worth holding onto rather than assuming.
    """
    state = StateManager()
    accounts = {f"ait1{BODY}": _Account(3_599_999_999_890, 1), "ait1" + "ab" * 20: _Account(360000, 0)}

    class _Unnormalised(StateManager):
        def _encode_address(self, address: str) -> bytes:
            return address.encode("utf-8")

    assert state.compute_state_root(accounts) == _Unnormalised().compute_state_root(accounts)


def test_the_state_root_agrees_across_spellings() -> None:
    state = StateManager()

    canonical = state.compute_state_root({f"ait1{BODY}": _Account(100, 1)})
    hex_form = state.compute_state_root({f"0x{BODY}": _Account(100, 1)})

    assert canonical == hex_form
