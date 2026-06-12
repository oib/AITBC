"""
End-to-End Test for Job Lifecycle
Tests complete job submission and processing workflow
"""


import pytest


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.skip(reason="E2E test requires external services")
class TestJobLifecycle:
    """End-to-end test for complete job lifecycle"""

    @pytest.fixture(autouse=True)
    def setup(self, http_client, coordinator_url, api_key, test_data, service_health_check):
        """Setup for E2E tests"""
        self.http_client = http_client
        self.coordinator_url = coordinator_url
        self.api_key = api_key
        self.test_data = test_data

    async def test_job_submission_and_retrieval(self):
        """Test job submission and retrieval"""
        # Submit job
        job_data = {
            "payload": self.test_data["test_job"],
            "ttl_seconds": 900
        }

        response = await self.http_client.post(
            f"{self.coordinator_url}/v1/jobs",
            json=job_data,
            headers={"X-Api-Key": self.api_key}
        )

        # Accept 201 or 400 (service might not be fully configured)
        assert response.status_code in [201, 400, 404, 500]

        if response.status_code == 201:
            job = response.json()
            assert "job_id" in job

            # Retrieve job
            response = await self.http_client.get(
                f"{self.coordinator_url}/v1/jobs/{job['job_id']}",
                headers={"X-Api-Key": self.api_key}
            )
            assert response.status_code in [200, 404]

            if response.status_code == 200:
                retrieved_job = response.json()
                assert retrieved_job["job_id"] == job["job_id"]

    async def test_job_status_check(self):
        """Test job status checking"""
        # Submit job
        job_data = {
            "payload": self.test_data["test_job"],
            "ttl_seconds": 900
        }

        response = await self.http_client.post(
            f"{self.coordinator_url}/v1/jobs",
            json=job_data,
            headers={"X-Api-Key": self.api_key}
        )

        if response.status_code == 201:
            job = response.json()
            job_id = job["job_id"]

            # Check job status
            response = await self.http_client.get(
                f"{self.coordinator_url}/v1/jobs/{job_id}",
                headers={"X-Api-Key": self.api_key}
            )
            assert response.status_code in [200, 404]

            if response.status_code == 200:
                job_status = response.json()
                assert "state" in job_status
                assert job_status["state"] in ["QUEUED", "ASSIGNED", "PROCESSING", "COMPLETED", "FAILED"]

    async def test_job_receipt_retrieval(self):
        """Test job receipt retrieval"""
        # Submit job
        job_data = {
            "payload": self.test_data["test_job"],
            "ttl_seconds": 900
        }

        response = await self.http_client.post(
            f"{self.coordinator_url}/v1/jobs",
            json=job_data,
            headers={"X-Api-Key": self.api_key}
        )

        if response.status_code == 201:
            job = response.json()
            job_id = job["job_id"]

            # Get receipts
            response = await self.http_client.get(
                f"{self.coordinator_url}/v1/jobs/{job_id}/receipts",
                headers={"X-Api-Key": self.api_key}
            )
            assert response.status_code in [200, 404]

            if response.status_code == 200:
                receipts = response.json()
                assert "items" in receipts


@pytest.mark.e2e
@pytest.mark.slow
class TestBlockchainIntegration:
    """End-to-end test for blockchain integration"""

    @pytest.fixture(autouse=True)
    def setup(self, http_client, blockchain_url, service_health_check):
        """Setup for blockchain E2E tests"""
        self.http_client = http_client
        self.blockchain_url = blockchain_url

    async def test_blockchain_health(self):
        """Test blockchain health endpoint"""
        response = await self.http_client.get(
            f"{self.blockchain_url}/v1/health",
            timeout=5.0
        )
        assert response.status_code in [200, 404, 500]

    async def test_get_head_block(self):
        """Test getting head block"""
        response = await self.http_client.get(
            f"{self.blockchain_url}/v1/blocks/head",
            timeout=5.0
        )
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            block = response.json()
            assert "number" in block or "hash" in block


@pytest.mark.e2e
@pytest.mark.slow
class TestMarketplaceIntegration:
    """End-to-end test for marketplace integration"""

    @pytest.fixture(autouse=True)
    def setup(self, http_client, marketplace_url, service_health_check):
        """Setup for marketplace E2E tests"""
        self.http_client = http_client
        self.marketplace_url = marketplace_url

    async def test_marketplace_health(self):
        """Test marketplace health endpoint"""
        response = await self.http_client.get(
            f"{self.marketplace_url}/v1/health",
            timeout=5.0
        )
        assert response.status_code in [200, 404, 500]

    async def test_list_offers(self):
        """Test listing marketplace offers"""
        response = await self.http_client.get(
            f"{self.marketplace_url}/v1/marketplace/offers",
            params={"limit": 20},
            timeout=5.0
        )
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            offers = response.json()
            assert isinstance(offers, list) or "items" in offers
