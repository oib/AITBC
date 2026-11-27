"""Persistence pins for #3053 — agent_identity JSON-column mutations.

SQLAlchemy does not track in-place mutation of plain ``Column(JSON)``
attributes: ``obj.col["k"] = v`` / ``.append()`` / ``del obj.col["k"]``
never dirty the attribute, so the commit's UPDATE omits the column and the
mutation is silently dropped (the #3014 trap; payments core already uses
copy-mutate-reassign). ``agent_identity`` never got the memo — revocation
and suspension evidence, cross-chain ``supported_chains`` registration,
and re-activation cleanup were all lost on commit.

Each test mutates through the service, lets it commit, then re-reads via a
FRESH session on the same engine. Asserting on the in-memory object alone
cannot catch the silent drop — the object still shows the mutation after
the commit that never wrote it.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from coordinator_api.agent_identity.core import AgentIdentityCore
from coordinator_api.agent_identity.registry import CrossChainRegistry
from coordinator_api.contexts.agent_identity.domain.agent_identity import (
    AgentIdentity,
    AgentIdentityCreate,
    CrossChainMapping,
)

OWNER = "0x" + "cd" * 20
ADDR_1 = "0x" + "ab" * 20
ADDR_2 = "0x" + "ef" * 20


def _fresh_identity(db_engine: Engine, agent_id: str) -> AgentIdentity | None:
    with Session(db_engine) as fresh:
        return fresh.exec(select(AgentIdentity).where(AgentIdentity.agent_id == agent_id)).first()


def _fresh_mapping(db_engine: Engine, agent_id: str, chain_id: int) -> CrossChainMapping | None:
    with Session(db_engine) as fresh:
        return fresh.exec(
            select(CrossChainMapping).where(CrossChainMapping.agent_id == agent_id, CrossChainMapping.chain_id == chain_id)
        ).first()


async def _make_identity(db_session: Session, agent_id: str, meta_data: dict | None = None) -> AgentIdentity:
    core = AgentIdentityCore(db_session)
    identity = await core.create_identity(
        AgentIdentityCreate(agent_id=agent_id, owner_address=OWNER, meta_data=meta_data or {})
    )
    return identity


async def test_core_register_cross_chain_persists_supported_chains(db_session: Session, db_engine: Engine) -> None:
    """core.register_cross_chain_identity must persist the appended chain."""
    agent_id = "agent-3053-core-reg"
    identity = await _make_identity(db_session, agent_id)

    core = AgentIdentityCore(db_session)
    await core.register_cross_chain_identity(identity.id, 137, ADDR_1)

    reread = _fresh_identity(db_engine, agent_id)
    assert reread is not None
    assert "137" in reread.supported_chains


async def test_registry_register_cross_chain_persists_supported_chains(db_session: Session, db_engine: Engine) -> None:
    """registry.register_cross_chain_identity must persist the appended chain."""
    agent_id = "agent-3053-reg-reg"
    await _make_identity(db_session, agent_id)

    registry = CrossChainRegistry(db_session)
    result = await registry.register_cross_chain_identity(agent_id, {137: ADDR_1})
    assert result["failed_mappings"] == 0

    reread = _fresh_identity(db_engine, agent_id)
    assert reread is not None
    assert "137" in reread.supported_chains


async def test_core_revoke_identity_persists_revocation_evidence(db_session: Session, db_engine: Engine) -> None:
    """revoke_identity must persist revocation_reason/revoked_at into identity_data."""
    agent_id = "agent-3053-revoke"
    identity = await _make_identity(db_session, agent_id, meta_data={"keep": "me"})

    core = AgentIdentityCore(db_session)
    assert await core.revoke_identity(identity.id, "fraudulent-agent") is True

    reread = _fresh_identity(db_engine, agent_id)
    assert reread is not None
    assert reread.identity_data["revocation_reason"] == "fraudulent-agent"
    assert reread.identity_data["revoked_at"]
    # pre-existing metadata must survive the copy-reassign
    assert reread.identity_data["keep"] == "me"


async def test_core_suspend_identity_persists_suspension_evidence(db_session: Session, db_engine: Engine) -> None:
    """suspend_identity must persist suspension_reason/suspended_at into identity_data."""
    agent_id = "agent-3053-suspend"
    identity = await _make_identity(db_session, agent_id)

    core = AgentIdentityCore(db_session)
    assert await core.suspend_identity(identity.id, "policy-violation") is True

    reread = _fresh_identity(db_engine, agent_id)
    assert reread is not None
    assert reread.identity_data["suspension_reason"] == "policy-violation"
    assert reread.identity_data["suspended_at"]


async def test_core_activate_identity_persists_suspension_cleanup(db_session: Session, db_engine: Engine) -> None:
    """activate_identity must persist the removal of suspension keys."""
    agent_id = "agent-3053-activate"
    identity = await _make_identity(
        db_session,
        agent_id,
        meta_data={"suspension_reason": "old", "suspended_at": "2026-01-01T00:00:00+00:00", "keep": "me"},
    )

    core = AgentIdentityCore(db_session)
    assert await core.activate_identity(identity.id) is True

    reread = _fresh_identity(db_engine, agent_id)
    assert reread is not None
    assert "suspension_reason" not in reread.identity_data
    assert "suspended_at" not in reread.identity_data
    assert reread.identity_data["keep"] == "me"


async def test_registry_revoke_verification_persists_chain_meta_data(db_session: Session, db_engine: Engine) -> None:
    """revoke_verification must persist the revocation evidence into
    chain_meta_data — seeded NON-EMPTY so the buggy in-place path is the
    only one exercised (an empty dict took the ``= {}`` assignment branch
    even before the fix)."""
    agent_id = "agent-3053-meta"
    identity = await _make_identity(db_session, agent_id)
    db_session.add(
        CrossChainMapping(
            agent_id=agent_id,
            chain_id=1,
            chain_type="ethereum",
            chain_address=ADDR_2,
            chain_meta_data={"prior": "keep"},
        )
    )
    db_session.commit()

    registry = CrossChainRegistry(db_session)
    assert await registry.revoke_verification(identity.id, 1, "key-compromised") is True

    reread = _fresh_mapping(db_engine, agent_id, 1)
    assert reread is not None
    assert reread.chain_meta_data["verification_revoked"] is True
    assert reread.chain_meta_data["revocation_reason"] == "key-compromised"
    assert reread.chain_meta_data["revoked_at"]
    assert reread.chain_meta_data["prior"] == "keep"
