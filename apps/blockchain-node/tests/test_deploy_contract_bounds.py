"""#2770: deploy_contract registry hardening.

Three defects: same-second redeploy of (deployer, name) derived an
identical address → IntegrityError 500; bytecode/abi/name/type/deployer
were unbounded; deployer accepted any string. Fields are now bounded,
deployer must be a well-formed 0x address, and the address derivation
uses a nanosecond timestamp plus a bounded IntegrityError retry.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from aitbc_chain.base_models import SmartContract
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import contracts as contracts_mod

DEPLOYER = "0x" + "ab" * 20


@pytest.fixture
def patched_session(monkeypatch):
    """Route session_scope to a fresh in-memory sqlite with all tables."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    chain_metadata.create_all(engine)

    @contextmanager
    def _scope(chain_id: str = "", **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(contracts_mod, "session_scope", _scope)
    return engine


def _deploy(data: dict) -> dict:
    return contracts_mod.deploy_contract(Mock(), data)


# -- field bounds ---------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ({}, "name is required"),
        ({"name": ""}, "name is required"),
        ({"name": 123}, "name is required"),
        ({"name": "x" * 129}, "name too long"),
        ({"name": "ok", "type": "t" * 65}, "type must be a string"),
        ({"name": "ok", "chain_id": "c" * 129}, "chain_id must be a string"),
        ({"name": "ok", "chain_id": 5}, "chain_id must be a string"),
        ({"name": "ok", "deployer": "not-an-address"}, "deployer must be a valid address"),
        ({"name": "ok", "deployer": "0x123"}, "deployer must be a valid address"),
        ({"name": "ok", "deployer": "x" * 200}, "deployer must be a string"),
        ({"name": "ok", "bytecode": "0x" + "ab" * 200000}, "bytecode must be a string"),
        ({"name": "ok", "bytecode": [1, 2, 3]}, "bytecode must be a string"),
        ({"name": "ok", "abi": {"k": "x" * 70000}}, "abi too large"),
    ],
)
def test_invalid_fields_rejected(data, fragment):
    result = _deploy(data)
    assert result["success"] is False
    assert fragment in result["error"]


def test_valid_minimal_deploy(patched_session):
    result = _deploy({"name": "MyContract"})
    assert result["success"] is True
    assert result["contract_address"].startswith("0x")
    assert result["scope"] == "node-local-registry"


def test_deployer_and_bounds_accepted(patched_session):
    result = _deploy(
        {
            "name": "C",
            "deployer": DEPLOYER,
            "bytecode": "0x6000",
            "abi": {"foo": {"type": "function"}},
            "type": "escrow",
            "chain_id": "test-chain",
        }
    )
    assert result["success"] is True


def test_non_dict_abi_coerced_to_empty(patched_session):
    result = _deploy({"name": "C", "abi": ["not", "a", "dict"]})
    assert result["success"] is True


# -- collision handling ----------------------------------------------------


def test_same_name_redeploy_gets_distinct_address(patched_session):
    """Regression: two deploys inside the same wall-clock second used to
    derive the same address and 500 on the unique constraint."""
    first = _deploy({"name": "Same", "deployer": DEPLOYER})
    second = _deploy({"name": "Same", "deployer": DEPLOYER})
    assert first["success"] and second["success"]
    assert first["contract_address"] != second["contract_address"]


def test_integrity_error_retries_with_new_address(patched_session, monkeypatch):
    """A pre-existing row at the first derived address must not 500 — the
    retry derives a fresh one and succeeds."""
    frozen_ns = 1_700_000_000_000_000_000
    monkeypatch.setattr(contracts_mod.time, "time_ns", lambda: frozen_ns)
    colliding = contracts_mod._derive_contract_address(DEPLOYER, "C", frozen_ns)
    with Session(patched_session) as s:
        s.add(
            SmartContract(
                chain_id="",
                address=colliding,
                name="C",
                deployer=DEPLOYER,
                bytecode="",
                abi={},
                state={},
            )
        )
        s.commit()
    result = _deploy({"name": "C", "deployer": DEPLOYER})
    assert result["success"] is True
    assert result["contract_address"] != colliding


def test_persistent_collision_returns_clean_error(patched_session, monkeypatch):
    """If every attempt collides (patched derivation), the caller gets a
    structured error — never an IntegrityError 500."""
    monkeypatch.setattr(contracts_mod, "_derive_contract_address", lambda *a: "0x" + "00" * 20)
    with Session(patched_session) as s:
        s.add(
            SmartContract(
                chain_id="",
                address="0x" + "00" * 20,
                name="C",
                deployer=DEPLOYER,
                bytecode="",
                abi={},
                state={},
            )
        )
        s.commit()
    result = _deploy({"name": "C", "deployer": DEPLOYER})
    assert result["success"] is False
    assert "collision" in result["error"]
