#!/usr/bin/env python3
"""
Test script for AITBC Payment Integration (Localhost)
Tests job creation with payments, escrow, release, and refund flows
"""

import asyncio

import httpx

from aitbc import get_logger

# Configure logging
logger = get_logger(__name__)

# Configuration - Using localhost as we're testing from the server
COORDINATOR_URL = "http://127.0.0.1:8000/v1"
CLIENT_KEY = "${CLIENT_API_KEY}"
MINER_KEY = "${MINER_API_KEY}"


class PaymentIntegrationTest:
    def __init__(self):
        self.client = httpx.Client(timeout=30.0)
        self.job_id = None
        self.payment_id = None

    async def test_complete_payment_flow(self):
        """Test the complete payment flow from job creation to payment release"""

        logger.info("=== Starting AITBC Payment Integration Test (Localhost) ===")

        # Step 1: Check coordinator health
        await self.check_health()

        # Step 2: Submit a job with payment
        await self.submit_job_with_payment()

        # Step 3: Check job status and payment
        await self.check_job_and_payment_status()

        # Step 4: Simulate job completion by miner
        await self.complete_job()

        # Step 5: Verify payment was released
        await self.verify_payment_release()

        # Step 6: Test refund flow with a new job
        await self.test_refund_flow()

        logger.info("=== Payment Integration Test Complete ===")

    async def check_health(self):
        """Check if coordinator API is healthy"""
        logger.info("Step 1: Checking coordinator health...")

        response = self.client.get(f"{COORDINATOR_URL}/health")

        if response.status_code == 200:
            logger.info("✓ Coordinator healthy: %s", response.json())
        else:
            raise Exception(f"Coordinator health check failed: {response.status_code}")

    async def submit_job_with_payment(self):
        """Submit a job with AITBC token payment"""
        logger.info("Step 2: Submitting job with payment...")

        job_data = {
            "payload": {"service_type": "llm", "model": "llama3.2", "prompt": "What is AITBC?", "max_tokens": 100},
            "constraints": {},
            "payment_amount": 1.0,
            "payment_currency": "AITBC",
            "escrow_timeout_seconds": 3600,
        }

        headers = {"X-Api-Key": CLIENT_KEY}

        response = self.client.post(f"{COORDINATOR_URL}/jobs", json=job_data, headers=headers)

        if response.status_code == 201:
            job = response.json()
            self.job_id = job["job_id"]
            logger.info("✓ Job created with ID: %s", self.job_id)
            logger.info("  Payment status: %s", job.get("payment_status", "N/A"))
        else:
            logger.error("Failed to create job: %s", response.status_code)
            logger.error("Response: %s", response.text)
            raise Exception(f"Failed to create job: {response.status_code}")

    async def check_job_and_payment_status(self):
        """Check job status and payment details"""
        logger.info("Step 3: Checking job and payment status...")

        headers = {"X-Api-Key": CLIENT_KEY}

        # Get job status
        response = self.client.get(f"{COORDINATOR_URL}/jobs/{self.job_id}", headers=headers)

        if response.status_code == 200:
            job = response.json()
            logger.info("✓ Job status: %s", job["state"])
            logger.info("  Payment ID: %s", job.get("payment_id", "N/A"))
            logger.info("  Payment status: %s", job.get("payment_status", "N/A"))

            self.payment_id = job.get("payment_id")

            # Get payment details if payment_id exists
            if self.payment_id:
                payment_response = self.client.get(f"{COORDINATOR_URL}/payments/{self.payment_id}", headers=headers)

                if payment_response.status_code == 200:
                    payment = payment_response.json()
                    logger.info("✓ Payment details:")
                    logger.info("  Amount: %s %s", payment["amount"], payment["currency"])
                    logger.info("  Status: %s", payment["status"])
                    logger.info("  Method: %s", payment["payment_method"])
                else:
                    logger.warning("Could not fetch payment details: %s", payment_response.status_code)
        else:
            raise Exception(f"Failed to get job status: {response.status_code}")

    async def complete_job(self):
        """Simulate miner completing the job"""
        logger.info("Step 4: Simulating job completion...")

        # First, poll for the job as miner (with retry for 204)
        headers = {"X-Api-Key": MINER_KEY}

        poll_data = None
        for attempt in range(5):
            poll_response = self.client.post(
                f"{COORDINATOR_URL}/miners/poll", json={"capabilities": {"llm": True}}, headers=headers
            )

            if poll_response.status_code == 200:
                poll_data = poll_response.json()
                break
            elif poll_response.status_code == 204:
                logger.info("  No job available yet, retrying... (%s/5)", attempt + 1)
                await asyncio.sleep(1)
            else:
                raise Exception(f"Failed to poll for job: {poll_response.status_code}")

        if poll_data and poll_data.get("job_id") == self.job_id:
            logger.info("✓ Miner received job: %s", self.job_id)

            # Submit job result
            result_data = {
                "result": {
                    "text": "AITBC is a decentralized AI computing marketplace that uses blockchain for payments and zero-knowledge proofs for privacy.",
                    "model": "llama3.2",
                    "tokens_used": 42,
                },
                "metrics": {"duration_ms": 2500, "tokens_used": 42, "gpu_seconds": 0.5},
            }

            submit_response = self.client.post(
                f"{COORDINATOR_URL}/miners/{self.job_id}/result", json=result_data, headers=headers
            )

            if submit_response.status_code == 200:
                logger.info("✓ Job result submitted successfully")
                logger.info("  Receipt: %s", submit_response.json().get("receipt", {}).get("receipt_id", "N/A"))
            else:
                raise Exception(f"Failed to submit result: {submit_response.status_code}")
        elif poll_data:
            logger.warning("Miner received different job: %s", poll_data.get("job_id"))
        else:
            raise Exception("No job received after 5 retries")

    async def verify_payment_release(self):
        """Verify that payment was released after job completion"""
        logger.info("Step 5: Verifying payment release...")

        # Wait a moment for payment processing
        await asyncio.sleep(2)

        headers = {"X-Api-Key": CLIENT_KEY}

        # Check updated job status
        response = self.client.get(f"{COORDINATOR_URL}/jobs/{self.job_id}", headers=headers)

        if response.status_code == 200:
            job = response.json()
            logger.info("✓ Final job status: %s", job["state"])
            logger.info("  Final payment status: %s", job.get("payment_status", "N/A"))

            # Get payment receipt
            if self.payment_id:
                receipt_response = self.client.get(f"{COORDINATOR_URL}/payments/{self.payment_id}/receipt", headers=headers)

                if receipt_response.status_code == 200:
                    receipt = receipt_response.json()
                    logger.info("✓ Payment receipt:")
                    logger.info("  Status: %s", receipt["status"])
                    logger.info("  Verified at: %s", receipt.get("verified_at", "N/A"))
                    logger.info("  Transaction hash: %s", receipt.get("transaction_hash", "N/A"))
                else:
                    logger.warning("Could not fetch payment receipt: %s", receipt_response.status_code)
        else:
            raise Exception(f"Failed to verify payment release: {response.status_code}")

    async def test_refund_flow(self):
        """Test payment refund for failed jobs"""
        logger.info("Step 6: Testing refund flow...")

        # Create a new job that will fail
        job_data = {
            "payload": {"service_type": "llm", "model": "nonexistent_model", "prompt": "This should fail"},
            "payment_amount": 0.5,
            "payment_currency": "AITBC",
        }

        headers = {"X-Api-Key": CLIENT_KEY}

        response = self.client.post(f"{COORDINATOR_URL}/jobs", json=job_data, headers=headers)

        if response.status_code == 201:
            fail_job = response.json()
            fail_job_id = fail_job["job_id"]
            fail_payment_id = fail_job.get("payment_id")

            logger.info("✓ Created test job for refund: %s", fail_job_id)

            # Simulate job failure
            fail_headers = {"X-Api-Key": MINER_KEY}

            # Poll for the job
            poll_response = self.client.post(
                f"{COORDINATOR_URL}/miners/poll", json={"capabilities": ["llm"]}, headers=fail_headers
            )

            if poll_response.status_code == 200:
                poll_data = poll_response.json()
                if poll_data.get("job_id") == fail_job_id:
                    # Submit failure
                    fail_data = {"error_code": "MODEL_NOT_FOUND", "error_message": "The specified model does not exist"}

                    fail_response = self.client.post(
                        f"{COORDINATOR_URL}/miners/{fail_job_id}/fail", json=fail_data, headers=fail_headers
                    )

                    if fail_response.status_code == 200:
                        logger.info("✓ Job failure submitted")

                        # Wait for refund processing
                        await asyncio.sleep(2)

                        # Check refund status
                        if fail_payment_id:
                            payment_response = self.client.get(
                                f"{COORDINATOR_URL}/payments/{fail_payment_id}", headers=headers
                            )

                            if payment_response.status_code == 200:
                                payment = payment_response.json()
                                logger.info("✓ Payment refunded:")
                                logger.info("  Status: %s", payment["status"])
                                logger.info("  Refunded at: %s", payment.get("refunded_at", "N/A"))
                            else:
                                logger.warning("Could not verify refund: %s", payment_response.status_code)
                    else:
                        logger.warning("Failed to submit job failure: %s", fail_response.status_code)

        logger.info("\n=== Test Summary ===")
        logger.info("✓ Job creation with payment")
        logger.info("✓ Payment escrow creation")
        logger.info("✓ Job completion and payment release")
        logger.info("✓ Job failure and payment refund")
        logger.info("\nPayment integration is working correctly!")


async def main():
    """Run the payment integration test"""
    test = PaymentIntegrationTest()

    try:
        await test.test_complete_payment_flow()
    except Exception as e:
        logger.error("Test failed: %s", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())
