"""Deterministic contract_id across every derivation path (Refs #780).

One job must answer with the same contract_id from every RPC worker and every
code path: create, DB-load and lookup all derive from (buyer, provider, job_id)
with no time or randomness mixed in — the two --workers 2 processes returning
different ids for one job was the finding.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest

from aitbc_chain.contracts.escrow import EscrowManager, contract_id_for

BUYER = "0x" + "aa" * 20
PROVIDER = "0x" + "bb" * 20
JOB_ID = "job-det-1"


@pytest.mark.unit
class TestContractIdDeterminism:
    def test_helper_format(self):
        cid = contract_id_for(BUYER, PROVIDER, JOB_ID)
        expected = "escrow_" + hashlib.sha256(f"{BUYER}:{PROVIDER}:{JOB_ID}".encode()).hexdigest()[:16]
        assert cid == expected
        assert cid.startswith("escrow_")
        assert len(cid) == len("escrow_") + 16

    def test_helper_is_repeatable(self):
        """No time/time.time or randomness mixed in — two calls, one answer."""
        assert contract_id_for(BUYER, PROVIDER, JOB_ID) == contract_id_for(BUYER, PROVIDER, JOB_ID)

    def test_different_jobs_differ(self):
        assert contract_id_for(BUYER, PROVIDER, JOB_ID) != contract_id_for(BUYER, PROVIDER, "job-det-2")

    @pytest.mark.asyncio
    async def test_create_matches_load_derivation(self):
        """create_contract must emit the same id the DB-load path derives.

        Before the fix, create mixed time.time() into a plain 16-hex id while
        load_from_db/get_or_load_contract used 'escrow_'+sha256 — the two
        workers literally answered different contract_ids for one job.
        """
        mgr = EscrowManager()
        ok, _, cid = await mgr.create_contract(JOB_ID, BUYER, PROVIDER, Decimal("1"))
        assert ok
        assert cid == contract_id_for(BUYER, PROVIDER, JOB_ID)

    @pytest.mark.asyncio
    async def test_create_is_repeatable_across_managers(self):
        """Two processes (two managers) agree on the id for one job."""
        mgr_a = EscrowManager()
        mgr_b = EscrowManager()
        ok_a, _, cid_a = await mgr_a.create_contract(JOB_ID, BUYER, PROVIDER, Decimal("1"))
        ok_b, _, cid_b = await mgr_b.create_contract(JOB_ID, BUYER, PROVIDER, Decimal("1"))
        assert ok_a and ok_b
        assert cid_a == cid_b
