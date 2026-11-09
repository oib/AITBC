"""Service-layer tests for agent_identity/services/manager.py (#1372).

Complements the router-level roundtrip pin: these assert the metadata
payload itself survives create -> export -> wipe -> import, and that the
``meta_data`` ctor kwarg is actually wired (pydantic silently dropped the
old ``metadata=`` kwarg, leaving ``identity_data`` empty on every create).
"""

from __future__ import annotations

from sqlmodel import Session, select

from coordinator_api.contexts.agent_identity.domain.agent_identity import (
    AgentIdentity,
    AgentWallet,
    CrossChainMapping,
)
from coordinator_api.contexts.agent_identity.services.manager import AgentIdentityManager

OWNER = "0x" + "cd" * 20


async def _wipe_agent(db_session: Session, agent_id: str) -> None:
    for model in (AgentIdentity, CrossChainMapping, AgentWallet):
        for row in db_session.exec(select(model).where(model.agent_id == agent_id)).all():
            db_session.delete(row)
    db_session.commit()


async def test_create_identity_preserves_metadata(db_session: Session) -> None:
    mgr = AgentIdentityManager(db_session)
    meta = {"purpose": "roundtrip", "nested": {"k": 1}}
    created = await mgr.create_agent_identity(
        owner_address=OWNER,
        chains=[1],
        display_name="Meta Agent",
        description="d",
        metadata=meta,
        tags=["t1"],
    )
    ident = await mgr.core.get_identity_by_agent_id(created["agent_id"])
    assert ident is not None
    assert ident.identity_data == meta
    assert ident.tags == ["t1"]


async def test_import_agent_identity_roundtrip(db_session: Session) -> None:
    mgr = AgentIdentityManager(db_session)
    meta = {"purpose": "roundtrip", "nested": {"k": 1}}
    created = await mgr.create_agent_identity(
        owner_address=OWNER,
        chains=[1],
        display_name="RT Agent",
        description="roundtrip me",
        metadata=meta,
        tags=["rt"],
    )
    agent_id = created["agent_id"]

    exported = await mgr.export_agent_identity(agent_id)
    assert "identity" in exported, exported

    await _wipe_agent(db_session, agent_id)
    assert await mgr.core.get_identity_by_agent_id(agent_id) is None

    result = await mgr.import_agent_identity(exported)
    assert result["import_successful"] is True, result
    assert result["agent_id"] == agent_id

    ident = await mgr.core.get_identity_by_agent_id(agent_id)
    assert ident is not None
    assert ident.identity_data == meta
    assert ident.tags == ["rt"]
    assert ident.display_name == "RT Agent"

    mappings = await mgr.registry.get_all_cross_chain_mappings(agent_id)
    assert len(mappings) == len(exported.get("cross_chain_mappings", []))


async def test_import_agent_identity_rejects_existing(db_session: Session) -> None:
    mgr = AgentIdentityManager(db_session)
    created = await mgr.create_agent_identity(owner_address=OWNER, chains=[1], display_name="Dup")
    exported = await mgr.export_agent_identity(created["agent_id"])
    result = await mgr.import_agent_identity(exported)
    assert result["import_successful"] is False
    assert "already exists" in result["error"]
