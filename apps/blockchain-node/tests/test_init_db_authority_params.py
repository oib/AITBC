"""`init_db` reports unset authority chain parameters but never writes them.

Below state-transition v5 an unset ``governance_executors`` takes the lenient
branch — any funded sender may execute governance — and the settlement/slash
authorities behave the same below their gate heights. These parameters are
consensus state: every node must hold identical values (the state root only
covers accounts, so nothing catches a disagreement), and a value present at
startup would apply to blocks mined before it was legitimately set — synced
GOVERNANCE_EXECUTEs validate against the current table, not the value at
their height. init therefore only warns; genesis and GOVERNANCE_EXECUTE are
the only paths that may write them.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from aitbc_chain.base_models import ChainParameter
from aitbc_chain.database import init_db, session_scope

_PARAMS = ("governance_executors", "escrow_settlement_authority", "bond_slash_authority")
_AUTHORITY = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"


@pytest.fixture
def isolated_chain_env(monkeypatch):
    """No env fallback is consulted, but clear them anyway so the assertions
    about what was *written* cannot be confused by a pre-seeded row."""
    for var in ("GOVERNANCE_EXECUTORS", "BOND_SLASH_AUTHORITY_ADDRESS", "ESCROW_RELEASE_ADDRESS"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def _param(chain_id: str, parameter: str) -> ChainParameter | None:
    with session_scope(chain_id) as session:
        return session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == parameter,
            )
        ).first()


def test_fresh_chain_warns_and_writes_nothing(isolated_chain_env, caplog):
    init_db("bare-chain-authority-check")

    for parameter in _PARAMS:
        assert _param("bare-chain-authority-check", parameter) is None
    warned = [r.message for r in caplog.records if "authority parameter" in r.message]
    assert len(warned) == len(_PARAMS)
    for parameter in _PARAMS:
        assert any(parameter in m and "bare-chain-authority-check" in m for m in warned)


def test_env_is_never_a_source(isolated_chain_env):
    """Env vars may inform a resolver's fallback; init must not persist them."""
    isolated_chain_env.setenv("ESCROW_RELEASE_ADDRESS", _AUTHORITY)
    isolated_chain_env.setenv("BOND_SLASH_AUTHORITY_ADDRESS", _AUTHORITY)
    isolated_chain_env.setenv("GOVERNANCE_EXECUTORS", _AUTHORITY)
    init_db("env-chain-authority-check")

    for parameter in _PARAMS:
        assert _param("env-chain-authority-check", parameter) is None


def test_existing_rows_are_untouched_and_unwarned(isolated_chain_env, caplog):
    """A chain that already has its authorities produces no warning and no writes."""
    chain = "set-chain-authority-check"
    init_db(chain)
    with session_scope(chain) as session:
        for parameter in _PARAMS:
            session.add(
                ChainParameter(
                    chain_id=chain,
                    parameter=parameter,
                    value=_AUTHORITY,
                    proposal_id="test-preset",
                )
            )
        session.commit()
    caplog.clear()

    init_db(chain)

    for parameter in _PARAMS:
        row = _param(chain, parameter)
        assert row.value == _AUTHORITY
        assert row.proposal_id == "test-preset"
    assert not any("authority parameter" in r.message for r in caplog.records)
