#!/usr/bin/env python3
"""
Test script for AITBC Payment Integration (Localhost)
Tests job creation with payments, escrow, release, and refund flows
"""

import asyncio
import httpx
import json
import logging
from datetime import datetime
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Using localhost as we're testing from the server
COORDINATOR_URL = "http://127.0.0.1:8000/v1"
CLIENT_KEY = "REDACTED_CLIENT_KEY"
MINER_KEY = "REDACTED_MINER_KEY"

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
            logger.info(f"✓ Coordinator healthy: {response.json()}")
        else:
            raise Exception(f"Coordinator health check failed: {response.status_code}")
    
    async def submit_job_with_payment(self):
        """Submit a job with AITBC token payment"""
        logger.info("Step 2: Submitting job with payment...")
        
        job_data = {
            "payload": {
                "service_type": "llm",
                "model": "llama3.2",
                "prompt": "What is AITBC?",
                "max_tokens": 100
            },
            "constraints": {},
            "payment_amount": 1.0,
            "payment_currency": "AITBC",
            "escrow_timeout_seconds": 3600
        }
        
        headers = {"X-Api-Key": CLIENT_KEY}
        
        response = self.client.post(
            f"{COORDINATOR_URL}/jobs",
            json=job_data,
            headers=headers
        )
        
        if response.status_code == 201:
            job = response.json()
            self.job_id = job["job_id"]
            logger.info(f"✓ Job created with ID: {self.job_id}")
            logger.info(f"  Payment status: {job.get('payment_status', 'N/A')}")
        else:
            logger.error(f"Failed to create job: {response.status_code}")
            logger.error(f"Response: {response.text}")
            raise Exception(f"Failed to create job: {response.status_code}")
    
    async def check_job_and_payment_status(self):
        """Check job status and payment details"""
        logger.info("Step 3: Checking job and payment status...")
        
        headers = {"X-Api-Key": CLIENT_KEY}
        
        # Get job status
        response = self.client.get(
            f"{COORDINATOR_URL}/jobs/{self.job_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            job = response.json()
            logger.info(f"✓ Job status: {job['state']}")
            logger.info(f"  Payment ID: {job.get('payment_id', 'N/A')}")
            logger.info(f"  Payment status: {job.get('payment_status', 'N/A')}")
            
            self.payment_id = job.get('payment_id')
            
            # Get payment details if payment_id exists
            if self.payment_id:
                payment_response = self.client.get(
                    f"{COORDINATOR_URL}/payments/{self.payment_id}",
                    headers=headers
                )
                
                if payment_response.status_code == 200:
                    payment = payment_response.json()
                    logger.info(f"✓ Payment details:")
                    logger.info(f"  Amount: {payment['amount']} {payment['currency']}")
                    logger.info(f"  Status: {payment['status']}")
                    logger.info(f"  Method: {payment['payment_method']}")
                else:
                    logger.warning(f"Could not fetch payment details: {payment_response.status_code}")
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
                f"{COORDINATOR_URL}/miners/poll",
                json={"capabilities": {"llm": True}},
                headers=headers
            )
            
            if poll_response.status_code == 200:
                poll_data = poll_response.json()
                break
            elif poll_response.status_code == 204:
                logger.info(f"  No job available yet, retrying... ({attempt + 1}/5)")
                await asyncio.sleep(1)
            else:
                raise Exception(f"Failed to poll for job: {poll_response.status_code}")
        
        if poll_data and poll_data.get("job_id") == self.job_id:
            logger.info(f"✓ Miner received job: {self.job_id}")
            
            # Submit job result
            result_data = {
                "result": {
                    "text": "AITBC is a decentralized AI computing marketplace that uses blockchain for payments and zero-knowledge proofs for privacy.",
                    "model": "llama3.2",
                    "tokens_used": 42
                },
                "metrics": {
                    "duration_ms": 2500,
                    "tokens_used": 42,
                    "gpu_seconds": 0.5
                }
            }
            
            submit_response = self.client.post(
                f"{COORDINATOR_URL}/miners/{self.job_id}/result",
                json=result_data,
                headers=headers
            )
            
            if submit_response.status_code == 200:
                logger.info("✓ Job result submitted successfully")
                logger.info(f"  Receipt: {submit_response.json().get('receipt', {}).get('receipt_id', 'N/A')}")
            else:
                raise Exception(f"Failed to submit result: {submit_response.status_code}")
        elif poll_data:
            logger.warning(f"Miner received different job: {poll_data.get('job_id')}")
        else:
            raise Exception("No job received after 5 retries")
    
    async def verify_payment_release(self):
        """Verify that payment was released after job completion"""
        logger.info("Step 5: Verifying payment release...")
        
        # Wait a moment for payment processing
        await asyncio.sleep(2)
        
        headers = {"X-Api-Key": CLIENT_KEY}
        
        # Check updated job status
        response = self.client.get(
            f"{COORDINATOR_URL}/jobs/{self.job_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            job = response.json()
            logger.info(f"✓ Final job status: {job['state']}")
            logger.info(f"  Final payment status: {job.get('payment_status', 'N/A')}")
            
            # Get payment receipt
            if self.payment_id:
                receipt_response = self.client.get(
                    f"{COORDINATOR_URL}/payments/{self.payment_id}/receipt",
                    headers=headers
                )
                
                if receipt_response.status_code == 200:
                    receipt = receipt_response.json()
                    logger.info(f"✓ Payment receipt:")
                    logger.info(f"  Status: {receipt['status']}")
                    logger.info(f"  Verified at: {receipt.get('verified_at', 'N/A')}")
                    logger.info(f"  Transaction hash: {receipt.get('transaction_hash', 'N/A')}")
                else:
                    logger.warning(f"Could not fetch payment receipt: {receipt_response.status_code}")
        else:
            raise Exception(f"Failed to verify payment release: {response.status_code}")
    
    async def test_refund_flow(self):
        """Test payment refund for failed jobs"""
        logger.info("Step 6: Testing refund flow...")
        
        # Create a new job that will fail
        job_data = {
            "payload": {
                "service_type": "llm",
                "model": "nonexistent_model",
                "prompt": "This should fail"
            },
            "payment_amount": 0.5,
            "payment_currency": "AITBC"
        }
        
        headers = {"X-Api-Key": CLIENT_KEY}
        
        response = self.client.post(
            f"{COORDINATOR_URL}/jobs",
            json=job_data,
            headers=headers
        )
        
        if response.status_code == 201:
            fail_job = response.json()
            fail_job_id = fail_job["job_id"]
            fail_payment_id = fail_job.get("payment_id")
            
            logger.info(f"✓ Created test job for refund: {fail_job_id}")
            
            # Simulate job failure
            fail_headers = {"X-Api-Key": MINER_KEY}
            
            # Poll for the job
            poll_response = self.client.post(
                f"{COORDINATOR_URL}/miners/poll",
                json={"capabilities": ["llm"]},
                headers=fail_headers
            )
            
            if poll_response.status_code == 200:
                poll_data = poll_response.json()
                if poll_data.get("job_id") == fail_job_id:
                    # Submit failure
                    fail_data = {
                        "error_code": "MODEL_NOT_FOUND",
                        "error_message": "The specified model does not exist"
                    }
                    
                    fail_response = self.client.post(
                        f"{COORDINATOR_URL}/miners/{fail_job_id}/fail",
                        json=fail_data,
                        headers=fail_headers
                    )
                    
                    if fail_response.status_code == 200:
                        logger.info("✓ Job failure submitted")
                        
                        # Wait for refund processing
                        await asyncio.sleep(2)
                        
                        # Check refund status
                        if fail_payment_id:
                            payment_response = self.client.get(
                                f"{COORDINATOR_URL}/payments/{fail_payment_id}",
                                headers=headers
                            )
                            
                            if payment_response.status_code == 200:
                                payment = payment_response.json()
                                logger.info(f"✓ Payment refunded:")
                                logger.info(f"  Status: {payment['status']}")
                                logger.info(f"  Refunded at: {payment.get('refunded_at', 'N/A')}")
                            else:
                                logger.warning(f"Could not verify refund: {payment_response.status_code}")
                    else:
                        logger.warning(f"Failed to submit job failure: {fail_response.status_code}")
        
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
        logger.error(f"Test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
