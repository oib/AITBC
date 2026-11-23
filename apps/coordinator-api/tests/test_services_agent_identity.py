"""Service-layer tests for agent_identity/services/manager.py (#1372).

Complements the router-level roundtrip pin: these assert the metadata
payload itself survives create -> export -> wipe -> import, and that the
``meta_data`` ctor kwarg is actually wired (pydantic silently dropped the
old ``metadata=`` kwarg, leaving ``identity_data`` empty on every create).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from coordinator_api.contexts.agent_identity.domain.agent_identity import (
    AgentIdentity,
    AgentWallet,
    CrossChainMapping,
)
from coordinator_api.contexts.agent_identity.services.manager import AgentIdentityManager
from coordinator_api.contexts.payments.services import escrow_agent_binding as binding

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


async def test_create_identity_seeds_no_payment_mapping(db_session: Session) -> None:
    """#2686: create must not invent chain addresses.

    The old code seeded each CrossChainMapping with secrets.token_hex(20) —
    an address no key controls — and escrow binding resolves the provider
    payee from chain_address, so a buyer naming provider_agent_id would
    lock and release payment to an unspendable address. Until the owner
    registers a real address, binding must answer 404."""
    mgr = AgentIdentityManager(db_session)
    created = await mgr.create_agent_identity(owner_address=OWNER, chains=[1], display_name="NoMap")
    agent_id = created["agent_id"]

    mappings = await mgr.registry.get_all_cross_chain_mappings(agent_id)
    assert mappings == []

    with pytest.raises(HTTPException) as exc_info:
        binding.resolve_agent_payment_address_sync(db_session, agent_id, chain_id=1)
    assert exc_info.value.status_code == 404


async def test_registry_statistics_counts_populated_db(db_session: Session) -> None:
    """get_registry_statistics must return real counts, not entity rows (#2687)."""
    from coordinator_api.agent_identity.registry import CrossChainRegistry

    db_session.add(AgentIdentity(agent_id="agent_stats1", owner_address=OWNER))
    db_session.add(
        CrossChainMapping(
            agent_id="agent_stats1",
            chain_id=1,
            chain_address="0x" + "ab" * 20,
            is_verified=True,
        )
    )
    db_session.commit()

    stats = await CrossChainRegistry(db_session).get_registry_statistics()
    assert isinstance(stats["total_identities"], int)
    assert isinstance(stats["total_mappings"], int)
    assert stats["total_identities"] >= 1
    assert stats["total_mappings"] >= 1
    assert stats["verified_mappings"] >= 1
    assert 0.0 <= stats["verification_rate"] <= 1.0


async def test_update_identity_maps_meta_and_blocks_trust_fields(db_session: Session) -> None:
    """meta_data/settings land on identity_data/settings_data; status and
    verification_level are not owner-writable (#2689)."""
    mgr = AgentIdentityManager(db_session)
    created = await mgr.create_agent_identity(owner_address=OWNER, chains=[1], display_name="Upd")
    agent_id = created["agent_id"]
    before = await mgr.core.get_identity_by_agent_id(agent_id)
    assert before is not None

    result = await mgr.update_agent_identity(
        agent_id,
        {
            "meta_data": {"k": "v"},
            "settings": {"s": 1},
            "verification_level": "zero-knowledge",
            "status": "suspended",
        },
    )
    assert result.get("update_successful", True) is not False
    assert set(result["updated_fields"]) == {"identity_data", "settings_data"}

    ident = await mgr.core.get_identity_by_agent_id(agent_id)
    assert ident is not None
    assert ident.identity_data == {"k": "v"}
    assert ident.settings_data == {"s": 1}
    # trust fields untouched by the owner update
    assert ident.verification_level == before.verification_level
    assert ident.status == before.status


async def test_import_agent_identity_rejects_existing(db_session: Session) -> None:
    mgr = AgentIdentityManager(db_session)
    created = await mgr.create_agent_identity(owner_address=OWNER, chains=[1], display_name="Dup")
    exported = await mgr.export_agent_identity(created["agent_id"])
    result = await mgr.import_agent_identity(exported)
    assert result["import_successful"] is False
    assert "already exists" in result["error"]


async def test_cleanup_expired_verifications_resets_stale_mapping(db_session: Session) -> None:
    """#2724: an expired verification must reset a mapping verified at/before
    its expiry, and delete the verification row."""
    from datetime import UTC, datetime, timedelta

    from coordinator_api.agent_identity.registry import CrossChainRegistry
    from coordinator_api.contexts.agent_identity.domain.agent_identity import IdentityVerification, VerificationType

    agent_id = "agent_cleanup1"
    now = datetime.now(UTC)
    db_session.add(AgentIdentity(agent_id=agent_id, owner_address=OWNER))
    db_session.add(
        CrossChainMapping(
            agent_id=agent_id,
            chain_id=1,
            chain_address="0x" + "cd" * 20,
            is_verified=True,
            verified_at=now - timedelta(days=10),
            verification_proof={"sig": "abc"},
        )
    )
    db_session.add(
        IdentityVerification(
            agent_id=agent_id,
            chain_id=1,
            verification_type=VerificationType.BASIC,
            verifier_address="0x" + "ef" * 20,
            proof_hash="deadbeef",
            expires_at=now - timedelta(days=1),
            verification_result="approved",
        )
    )
    db_session.commit()

    cleaned = await CrossChainRegistry(db_session).cleanup_expired_verifications()
    assert cleaned == 1

    mapping = await CrossChainRegistry(db_session).get_cross_chain_mapping_by_agent_chain(agent_id, 1)
    assert mapping is not None
    assert mapping.is_verified is False
    assert mapping.verified_at is None
    assert mapping.verification_proof is None
    assert db_session.exec(select(IdentityVerification).where(IdentityVerification.agent_id == agent_id)).first() is None


async def test_cleanup_expired_verifications_keeps_newer_mapping(db_session: Session) -> None:
    """#2724 negative pin: a mapping verified *after* the verification's
    expiry is newer evidence — cleanup must not strip it."""
    from datetime import UTC, datetime, timedelta

    from coordinator_api.agent_identity.registry import CrossChainRegistry
    from coordinator_api.contexts.agent_identity.domain.agent_identity import IdentityVerification, VerificationType

    agent_id = "agent_cleanup2"
    now = datetime.now(UTC)
    expired_at = now - timedelta(days=5)
    db_session.add(AgentIdentity(agent_id=agent_id, owner_address=OWNER))
    db_session.add(
        CrossChainMapping(
            agent_id=agent_id,
            chain_id=1,
            chain_address="0x" + "cd" * 20,
            is_verified=True,
            verified_at=now - timedelta(days=1),  # after expires_at
            verification_proof={"sig": "new"},
        )
    )
    db_session.add(
        IdentityVerification(
            agent_id=agent_id,
            chain_id=1,
            verification_type=VerificationType.BASIC,
            verifier_address="0x" + "ef" * 20,
            proof_hash="deadbeef",
            expires_at=expired_at,
            verification_result="approved",
        )
    )
    db_session.commit()

    cleaned = await CrossChainRegistry(db_session).cleanup_expired_verifications()
    assert cleaned == 1  # the expired verification row is still deleted

    mapping = await CrossChainRegistry(db_session).get_cross_chain_mapping_by_agent_chain(agent_id, 1)
    assert mapping is not None
    assert mapping.is_verified is True
    assert mapping.verified_at is not None
    assert mapping.verification_proof == {"sig": "new"}
