"""`init_db` seeds authority chain parameters on chains that have none.

Below state-transition v5 an unset ``governance_executors`` takes the lenient
branch — any funded sender may execute governance. A chain born with an empty
``chain_parameter`` table starts exactly there, which is why creation and
seeding happen inside `init_db` itself. These tests pin the seed order
(donor chain first, env fallbacks second), the never-overwrite guarantee, and
the executors-from-escrow-authority convention the live chain already uses.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from aitbc_chain.base_models import ChainParameter
from aitbc_chain.config import settings
from aitbc_chain.database import init_db, session_scope

_DONOR = "donor-chain-authority-seed"
_ESCROW = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"
_BOND = "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76"
_OTHER = "0x1111111111111111111111111111111111111111"


@pytest.fixture
def authority_env(monkeypatch):
    """Chain-id-independent env, cleared per test then populated explicitly."""
    for var in ("GOVERNANCE_EXECUTORS", "BOND_SLASH_AUTHORITY_ADDRESS", "ESCROW_RELEASE_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(settings, "escrow_settlement_authority", "")
    monkeypatch.setattr(settings, "chain_id", "")
    monkeypatch.setattr("aitbc_chain.database._default_chain_id", "")
    return monkeypatch


def _param(chain_id: str, parameter: str) -> ChainParameter | None:
    with session_scope(chain_id) as session:
        return session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == parameter,
            )
        ).first()


def test_fresh_chain_seeds_from_donor(authority_env):
    """A secondary chain copies the donor's rows verbatim, not the env's."""
    authority_env.setenv("ESCROW_RELEASE_ADDRESS", _ESCROW)
    authority_env.setenv("BOND_SLASH_AUTHORITY_ADDRESS", _BOND)
    init_db(_DONOR)
    assert _param(_DONOR, "escrow_settlement_authority").value == _ESCROW

    authority_env.setenv("ESCROW_RELEASE_ADDRESS", _OTHER)
    authority_env.setenv("BOND_SLASH_AUTHORITY_ADDRESS", _OTHER)
    authority_env.setattr(settings, "chain_id", _DONOR)
    init_db("child-chain-authority-seed")

    # Donor values win over the (deliberately different) env values.
    assert _param("child-chain-authority-seed", "escrow_settlement_authority").value == _ESCROW
    assert _param("child-chain-authority-seed", "bond_slash_authority").value == _BOND
    assert _param("child-chain-authority-seed", "escrow_settlement_authority").proposal_id == "init_db-bootstrap"


def test_env_fallback_when_no_donor(authority_env):
    authority_env.setenv("ESCROW_RELEASE_ADDRESS", _ESCROW)
    authority_env.setenv("BOND_SLASH_AUTHORITY_ADDRESS", _BOND)
    authority_env.setenv("GOVERNANCE_EXECUTORS", _OTHER)
    init_db("env-chain-authority-seed")

    assert _param("env-chain-authority-seed", "escrow_settlement_authority").value == _ESCROW
    assert _param("env-chain-authority-seed", "bond_slash_authority").value == _BOND
    assert _param("env-chain-authority-seed", "governance_executors").value == _OTHER


def test_governance_executors_falls_back_to_escrow_authority(authority_env):
    """The live fleet runs executors == escrow authority; a bare env inherits it."""
    authority_env.setenv("ESCROW_RELEASE_ADDRESS", _ESCROW)
    init_db("exec-chain-authority-seed")

    assert _param("exec-chain-authority-seed", "governance_executors").value == _ESCROW


def test_existing_rows_are_never_overwritten(authority_env):
    authority_env.setenv("ESCROW_RELEASE_ADDRESS", _ESCROW)
    init_db("keep-chain-authority-seed")

    authority_env.setenv("ESCROW_RELEASE_ADDRESS", _OTHER)
    init_db("keep-chain-authority-seed")

    assert _param("keep-chain-authority-seed", "escrow_settlement_authority").value == _ESCROW


def test_unresolvable_param_is_left_unset_and_warned(authority_env, caplog):
    """No donor, no env: nothing is written, and the gap is loud, not silent."""
    init_db("bare-chain-authority-seed")

    assert _param("bare-chain-authority-seed", "governance_executors") is None
    assert _param("bare-chain-authority-seed", "escrow_settlement_authority") is None
    assert _param("bare-chain-authority-seed", "bond_slash_authority") is None
    assert any("authority parameter" in r.message for r in caplog.records)
