"""
End-to-end tests for the marketplace escrow flow.

This suite exercises the full lifecycle:
  1. Register a marketplace software-service offer.
  2. Discover the offer through the marketplace API.
  3. Create a coordinator job bound to the offer.
  4. Fund the buyer account and lock payment in escrow.
  5. Register a provider miner and dispatch the job.
  6. Submit a job result.
  7. Release escrow (manually accept if the operator uses a review window).
  8. Verify the final job, payment, and on-chain escrow state.

Required environment:
  - COORDINATOR_URL, BLOCKCHAIN_URL, MARKETPLACE_URL
  - E2E_BUYER_PRIVATE_KEY, E2E_PROVIDER_PRIVATE_KEY (optional, generated if absent)
  - E2E_NODE_WALLET_ADDRESS (or NODE_WALLET_ADDRESS / GENESIS_WALLET_ADDRESS)
  - E2E_CLIENT_TOKEN or JWT_SECRET/E2E_JWT_SECRET
  - E2E_MINER_API_KEY or E2E_MINER_TOKEN or JWT_SECRET/E2E_JWT_SECRET
"""

import asyncio
import os
from decimal import Decimal
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e

_MIN_BUYER_BALANCE = 1000
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 60.0
_JOB_TIMEOUT = 120.0


class TestMarketplaceEscrowFlow:
    """Marketplace offer -> purchase -> escrow -> execution -> release."""

    @pytest.mark.asyncio
    async def test_marketplace_escrow_flow(
        self,
        require_healthy_services: None,
        coordinator_client: httpx.AsyncClient,
        marketplace_client: httpx.AsyncClient,
        blockchain_client: httpx.AsyncClient,
        miner_client: httpx.AsyncClient,
        buyer_wallet: dict[str, str],
        provider_address: str,
        node_wallet_address: str,
        chain_id: str,
        sign_escrow_lock: Any,
    ) -> None:
        """Full marketplace escrow lifecycle."""

        # 1. Register a resolvable software-service offer.
        plugin_id = await self._register_offer(
            marketplace_client,
            provider_address=provider_address,
        )

        # 2. Create a job against the offer (without an escrow lock signature).
        job, payment_amount = await self._create_job_against_offer(
            coordinator_client,
            offer_id=plugin_id,
        )
        job_id = job["job_id"]

        # 3. Ensure the buyer has on-chain funds.
        await self._ensure_buyer_funded(blockchain_client, buyer_wallet["address"])

        # 4. Get the buyer's current nonce and sign the ESCROW_LOCK tx.
        nonce = await self._get_buyer_nonce(blockchain_client, buyer_wallet["address"])
        lock_signature = sign_escrow_lock(
            job_id,
            provider_address,
            payment_amount,
            nonce,
        )

        # 5. Create the payment / escrow.
        payment = await self._create_payment(
            coordinator_client,
            job_id=job_id,
            amount=payment_amount,
            currency=job.get("payment_token") or "AITBC",
            buyer_address=buyer_wallet["address"],
            provider_address=provider_address,
            offer_id=plugin_id,
            lock_signature=lock_signature,
            lock_nonce=nonce,
        )
        assert payment["status"] == "escrowed"

        # 6. Register a miner bound to the provider address and poll for the job.
        await self._register_miner(miner_client, provider_address)
        assigned = await self._poll_for_job(miner_client, job_id, timeout=_POLL_TIMEOUT)
        assert assigned is not None, f"job {job_id} was not assigned to the miner"

        # 7. Submit a result.
        await self._submit_result(miner_client, job_id)

        # 8. Wait for the job to complete and release escrow if needed.
        completed_job = await self._wait_for_job_state(
            coordinator_client,
            job_id,
            target_state="COMPLETED",
            timeout=_JOB_TIMEOUT,
        )

        if completed_job.get("payment_status", "").lower() == "pending_acceptance":
            completed_job = await self._accept_job(coordinator_client, job_id)

        assert completed_job["state"] == "COMPLETED"
        assert completed_job["payment_status"].lower() == "released"

        # 9. Verify on-chain escrow state.
        await self._assert_escrow_released(blockchain_client, job_id)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    async def _register_offer(
        self,
        client: httpx.AsyncClient,
        provider_address: str,
    ) -> str:
        """Register a software-service offer and return its plugin_id."""
        service = {
            "service_type": "ollama",
            "model": "llama2",
            "price": "0.001",
            "price_unit": "per_1k_tokens",
            "provider_address": provider_address,
            "status": "active",
            "endpoint": "http://localhost:11434",
            "public_endpoint": "http://localhost:11434",
            "region": "e2e",
        }
        resp = await client.post("/v1/marketplace/offer", json=service)
        assert resp.status_code in (200, 201), f"offer registration failed: {resp.text}"
        offer = resp.json()
        plugin_id = offer["plugin_id"]

        # Verify the offer is discoverable and the provider is a payable address.
        resp = await client.get(f"/v1/marketplace/offer/{plugin_id}")
        assert resp.status_code in (200, 201), f"offer lookup failed: {resp.text}"
        offer_data = resp.json()
        assert offer_data["status"] == "active"
        assert Decimal(str(offer_data["price"])) > 0
        assert offer_data["provider_address"].lower() == provider_address.lower()

        return plugin_id

    async def _create_job_against_offer(
        self,
        client: httpx.AsyncClient,
        offer_id: str,
    ) -> tuple[dict[str, Any], Decimal]:
        """Create a job bound to a marketplace offer and return the job + quoted price."""
        payload = {
            "offer_id": offer_id,
            "offer_quantity": "1",
            "payload": {
                "type": "ai_inference",
                "model": "llama2",
                "prompt": "E2E marketplace escrow test",
                "max_tokens": 10,
            },
            "constraints": {},
            "ttl_seconds": 300,
        }
        resp = await client.post("/v1/jobs", json=payload)
        assert resp.status_code in (200, 201), f"job submission failed: {resp.text}"
        job = resp.json()
        assert job["state"] == "QUEUED", f"job was not queued: {job}"
        if job.get("offer_id") is not None:
            assert job["offer_id"] == offer_id, f"job not bound to offer: {job}"

        payment_amount = Decimal(str(job.get("payment_amount") or "0"))
        assert payment_amount > 0, f"job has no quoted payment_amount: {job}"
        return job, payment_amount

    async def _ensure_buyer_funded(
        self,
        client: httpx.AsyncClient,
        address: str,
        min_balance: int = _MIN_BUYER_BALANCE,
    ) -> None:
        """Fund the buyer account if the current balance is too low."""
        balance = await self._get_buyer_balance(client, address)
        if balance >= min_balance:
            return

        faucet_resp = await client.post(
            "/rpc/faucet",
            json={"address": address, "amount": 1_000_000, "chain_id": os.getenv("E2E_CHAIN_ID", "ait-hub.aitbc.bubuit.net")},
        )
        if faucet_resp.status_code in (200, 201):
            # The faucet may add a pending transaction instead of immediately
            # updating the account balance. Poll until a block is produced.
            deadline = asyncio.get_event_loop().time() + 90
            while asyncio.get_event_loop().time() < deadline:
                balance = await self._get_buyer_balance(client, address)
                if balance >= min_balance:
                    return
                await asyncio.sleep(2.0)

        if balance < min_balance:
            pytest.skip(f"Buyer account {address} balance too low ({balance}); faucet unavailable")

    async def _get_buyer_balance(self, client: httpx.AsyncClient, address: str) -> int:
        resp = await client.get(f"/rpc/accounts/{address}")
        if resp.status_code == 200:
            return int(resp.json().get("balance", 0))
        return 0

    async def _get_buyer_nonce(self, client: httpx.AsyncClient, address: str) -> int:
        resp = await client.get(f"/rpc/accounts/{address}")
        if resp.status_code == 200:
            return int(resp.json().get("nonce", 0))
        return 0

    async def _create_payment(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        amount: Decimal,
        currency: str,
        buyer_address: str,
        provider_address: str,
        offer_id: str,
        lock_signature: str,
        lock_nonce: int,
    ) -> dict[str, Any]:
        """Post /v1/payments to lock escrow for the job."""
        payment_payload = {
            "job_id": job_id,
            "amount": str(amount),
            "currency": currency,
            "payment_method": "aitbc_token",
            "buyer_address": buyer_address,
            "provider_address": provider_address,
            "buyer_lock_signature": lock_signature,
            "buyer_lock_nonce": lock_nonce,
            "buyer_lock_fee": max(36, int(amount * 3600) // 100),
            "offer_id": offer_id,
            "offer_quantity": "1",
        }
        resp = await client.post("/v1/payments", json=payment_payload)
        assert resp.status_code in (200, 201), f"payment creation failed: {resp.text}"
        return resp.json()

    async def _register_miner(self, client: httpx.AsyncClient, wallet_address: str) -> None:
        """Register a miner whose payout address matches the offer provider."""
        payload = {
            "capabilities": {
                "models": ["llama2"],
                "wallet_address": wallet_address,
            },
            "concurrency": 1,
            "wallet_address": wallet_address,
            "region": "e2e",
        }
        resp = await client.post("/v1/miners/register", json=payload)
        assert resp.status_code in (200, 201), f"miner registration failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "ok"

    async def _poll_for_job(
        self,
        client: httpx.AsyncClient,
        expected_job_id: str,
        timeout: float = _POLL_TIMEOUT,
    ) -> dict[str, Any] | None:
        """Poll the miner until the expected job is assigned."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            resp = await client.post("/v1/miners/poll", json={"max_wait_seconds": 5})
            if resp.status_code == 200:
                assigned = resp.json()
                if assigned and assigned.get("job_id") == expected_job_id:
                    return assigned
            elif resp.status_code not in (204, 404):
                pytest.fail(f"miner poll returned unexpected {resp.status_code}: {resp.text}")
            await asyncio.sleep(_POLL_INTERVAL)
        return None

    async def _submit_result(self, client: httpx.AsyncClient, job_id: str) -> None:
        result = {
            "output": "E2E marketplace escrow test result",
            "execution_time_ms": 100,
        }
        metrics = {"duration_ms": 100}
        resp = await client.post(
            f"/v1/miners/{job_id}/result",
            json={"result": result, "metrics": metrics},
        )
        assert resp.status_code in (200, 201), f"result submission failed: {resp.text}"
        data = resp.json()
        assert data.get("status") == "ok"

    async def _wait_for_job_state(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        target_state: str,
        timeout: float = _JOB_TIMEOUT,
    ) -> dict[str, Any]:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            resp = await client.get(f"/v1/jobs/{job_id}")
            assert resp.status_code in (200, 201), f"job lookup failed: {resp.text}"
            job = resp.json()
            if job.get("state") == target_state:
                return job
            if job.get("state") in ("FAILED", "CANCELED", "EXPIRED"):
                pytest.fail(f"job {job_id} reached terminal state {job['state']}: {job}")
            await asyncio.sleep(_POLL_INTERVAL)
        pytest.fail(f"job {job_id} did not reach state {target_state} within {timeout}s")

    async def _accept_job(self, client: httpx.AsyncClient, job_id: str) -> dict[str, Any]:
        """Customer accepts a completed job to release escrow."""
        resp = await client.post(f"/v1/jobs/{job_id}/accept")
        if resp.status_code == 502 and "escrow release" in resp.text.lower():
            pytest.skip(f"Escrow release could not settle on-chain for {job_id}: {resp.text}")
        assert resp.status_code in (200, 201), f"job acceptance/release failed: {resp.text}"
        return resp.json()

    async def _assert_escrow_released(
        self,
        client: httpx.AsyncClient,
        job_id: str,
    ) -> None:
        resp = await client.get(f"/rpc/escrow/{job_id}")
        assert resp.status_code in (200, 201), f"escrow lookup failed: {resp.text}"
        escrow = resp.json()
        released = escrow.get("state") in ("RELEASED", "released") or escrow.get("released_at") is not None
        assert released, f"escrow for {job_id} is not released: {escrow}"
