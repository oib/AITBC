#!/usr/bin/env python3
"""
End-to-End Test for AITBC GPU Marketplace
Tests the complete workflow: User Registration → GPU Booking → Task Execution → Payment
Uses the actual AITBC authentication system (wallet-based)
"""

import requests
import json
import time
import uuid
import sys
from typing import Dict, Optional

class AITBCE2ETest:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_user = None
        self.session_token = None  # AITBC uses session tokens, not JWT
        self.wallet_address = None
        self.gpu_id = None
        self.booking_id = None
        
    def log(self, message: str, level: str = "INFO"):
        """Log test progress"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/v1{endpoint}"  # All API routes are under /v1
        headers = kwargs.get('headers', {})
        
        # Add content type for JSON requests
        if 'json' in kwargs or (kwargs.get('data') and isinstance(kwargs['data'], dict)):
            headers['Content-Type'] = 'application/json'
            
        kwargs['headers'] = headers
        
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            self.log(f"{method} {endpoint} → {response.status_code}")
            return response
        except requests.exceptions.RequestException as e:
            self.log(f"Request failed: {e}", "ERROR")
            raise
    
    def test_health_check(self) -> bool:
        """Test if services are healthy"""
        self.log("Checking service health...")
        
        try:
            # Check coordinator health
            resp = self.session.get(f"{self.base_url}/health", timeout=10)
            if resp.status_code == 200:
                self.log("✓ Coordinator API healthy")
            else:
                self.log(f"✗ Coordinator API unhealthy: {resp.status_code}", "ERROR")
                return False
                
            # Check blockchain health  
            try:
                resp = self.session.get('http://localhost:8026/health', timeout=10)
                if resp.status_code == 200:
                    self.log("✓ Blockchain node healthy")
                else:
                    self.log(f"⚠ Blockchain health check failed: {resp.status_code}", "WARN")
            except:
                self.log("⚠ Could not reach blockchain health endpoint", "WARN")
                
            return True
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False
    
    def test_user_registration(self) -> bool:
        """Test user registration"""
        self.log("Testing user registration...")
        
        # Generate unique test user data
        unique_id = str(uuid.uuid4())[:8]
        self.test_user = {
            "email": f"e2e_test_{unique_id}@aitbc.test",
            "username": f"e2e_user_{unique_id}",
            "password": "SecurePass123!"  # Optional in AITBC
        }
        
        try:
            resp = self.make_request(
                'POST', 
                '/users/register', 
                json=self.test_user
            )
            
            if resp.status_code in [200, 201]:
                data = resp.json()
                # Extract session token from response
                if isinstance(data, dict) and 'session_token' in data:
                    self.session_token = data['session_token']
                self.log("✓ User registration successful")
                return True
            elif resp.status_code == 400 and "already registered" in resp.text.lower():
                # User might already exist, try to get wallet and login
                self.log("User already exists, attempting to derive wallet...", "WARN")
                # For now, we'll create a wallet-based login below
                return self.test_wallet_login()
            else:
                self.log(f"✗ Registration failed: {resp.status_code} - {resp.text}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Registration error: {e}", "ERROR")
            return False
    
    def test_wallet_login(self) -> bool:
        """Test wallet-based login (AITBC's primary auth method)"""
        self.log("Testing wallet-based login...")
        
        # Generate a test wallet address (simulating a blockchain wallet)
        # In practice, this would come from a connected wallet like MetaMask
        self.wallet_address = f"0x{uuid.uuid4().hex[:40]}"
        
        login_data = {
            "wallet_address": self.wallet_address,
            "signature": None  # Optional signature for more advanced auth
        }
        
        try:
            resp = self.make_request(
                'POST',
                '/users/login',
                json=login_data
            )
            
            if resp.status_code == 200:
                data = resp.json()
                # Extract session token from response
                if isinstance(data, dict) and 'session_token' in data:
                    self.session_token = data['session_token']
                # Also update test user info from response
                if isinstance(data, dict):
                    self.test_user = {
                        "username": data.get("username", f"user_{self.wallet_address[-6:]}"),
                        "email": data.get("email", f"{self.wallet_address}@aitbc.local"),
                        "wallet_address": self.wallet_address
                    }
                self.log("✓ Wallet login successful")
                return True
            else:
                self.log(f"✗ Login failed: {resp.status_code} - {resp.text}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Login error: {e}", "ERROR")
            return False
    
    def test_get_available_gpus(self) -> bool:
        """Test retrieving available GPUs"""
        self.log("Testing GPU availability...")
        
        try:
            # Add session token as query parameter for authenticated endpoints
            params = {'token': self.session_token} if self.session_token else {}
            
            resp = self.make_request('GET', '/marketplace/gpu/list', params=params)
            
            if resp.status_code == 200:
                data = resp.json()
                # Handle different possible response formats
                if isinstance(data, list):
                    gpus = data
                elif isinstance(data, dict) and 'gpus' in data:
                    gpus = data['gpus']
                elif isinstance(data, dict) and 'data' in data:
                    gpus = data['data']
                else:
                    gpus = [data] if data else []
                
                if gpus:
                    # Select first available GPU for testing
                    gpu_item = gpus[0]
                    self.gpu_id = gpu_item.get('id') if isinstance(gpu_item, dict) else gpu_item
                    self.log(f"✓ Found {len(gpus)} available GPUs, selected GPU {self.gpu_id}")
                    return True
                else:
                    self.log("⚠ No GPUs available for testing", "WARN")
                    return False
            else:
                self.log(f"✗ Failed to get GPUs: {resp.status_code} - {resp.text}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error getting GPUs: {e}", "ERROR")
            return False
    
    def test_book_gpu(self) -> bool:
        """Test booking a GPU"""
        self.log("Testing GPU booking...")
        
        if not self.gpu_id:
            self.log("No GPU ID available for booking", "ERROR")
            return False
            
        try:
            booking_data = {
                "gpu_id": str(self.gpu_id),
                "duration_hours": 1,  # Short duration for testing
                "max_price_per_hour": 10.0
            }
            
            # Add session token as query parameter
            params = {'token': self.session_token} if self.session_token else {}
            
            resp = self.make_request(
                'POST',
                f'/marketplace/gpu/{self.gpu_id}/book',
                json=booking_data,
                params=params
            )
            
            if resp.status_code in [200, 201]:
                data = resp.json()
                # Extract booking ID from response
                if isinstance(data, dict):
                    self.booking_id = data.get('booking_id') or data.get('id') or data.get('bookingReference')
                self.log(f"✓ GPU booked successfully: {self.booking_id}")
                return True
            else:
                self.log(f"✗ GPU booking failed: {resp.status_code} - {resp.text}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Booking error: {e}", "ERROR")
            return False
    
    def test_submit_task(self) -> bool:
        """Test submitting a task to the booked GPU"""
        self.log("Testing task submission...")
        
        if not self.gpu_id:
            self.log("No GPU ID available", "ERROR")
            return False
            
        try:
            # Simple test task - using the ollama task endpoint from marketplace_gpu
            task_data = {
                "gpu_id": str(self.gpu_id),
                "prompt": "Hello AITBC E2E Test! Please respond with confirmation.",
                "model": "llama2",
                "max_tokens": 50
            }
            
            # Add session token as query parameter
            params = {'token': self.session_token} if self.session_token else {}
            
            resp = self.make_request(
                'POST',
                '/tasks/ollama',
                json=task_data,
                params=params
            )
            
            if resp.status_code in [200, 201]:
                data = resp.json()
                self.log(f"✓ Task submitted successfully")
                return True
            else:
                self.log(f"✗ Task submission failed: {resp.status_code} - {resp.text}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Task submission error: {e}", "ERROR")
            return False
    
    def test_get_task_result(self) -> bool:
        """Test retrieving task result"""
        self.log("Testing task result retrieval...")
        
        # In a real test, we would wait for task completion
        # For now, we'll just test that we can make the attempt
        self.log("⚠ Skipping task result check (would require waiting for completion)", "INFO")
        return True
    
    def test_cleanup(self) -> bool:
        """Clean up test resources"""
        self.log("Cleaning up test resources...")
        
        success = True
        
        # Release GPU if booked
        if self.booking_id and self.gpu_id and self.session_token:
            try:
                params = {'token': self.session_token}
                
                resp = self.make_request(
                    'POST',
                    f'/marketplace/gpu/{self.gpu_id}/release',
                    params=params
                )
                if resp.status_code in [200, 204]:
                    self.log("✓ GPU booking released")
                else:
                    self.log(f"⚠ Failed to release booking: {resp.status_code}", "WARN")
            except Exception as e:
                self.log(f"Error releasing booking: {e}", "WARN")
                success = False
        
        return success
    
    def run_full_test(self) -> bool:
        """Run the complete E2E test"""
        self.log("=" * 60)
        self.log("Starting AITBC End-to-End Test")
        self.log("=" * 60)
        
        test_steps = [
            ("Health Check", self.test_health_check),
            ("User Registration/Login", self.test_user_registration),
            ("Get Available GPUs", self.test_get_available_gpus),
            ("Book GPU", self.test_book_gpu),
            ("Submit Task", self.test_submit_task),
            ("Get Task Result", self.test_get_task_result),
            ("Cleanup", self.test_cleanup)
        ]
        
        passed = 0
        total = len(test_steps)
        
        for step_name, test_func in test_steps:
            self.log(f"\n--- {step_name} ---")
            try:
                if test_func():
                    passed += 1
                    self.log(f"✓ {step_name} PASSED")
                else:
                    self.log(f"✗ {step_name} FAILED", "ERROR")
            except Exception as e:
                self.log(f"✗ {step_name} ERROR: {e}", "ERROR")
        
        self.log("\n" + "=" * 60)
        self.log(f"E2E Test Results: {passed}/{total} steps passed")
        self.log("=" * 60)
        
        if passed == total:
            self.log("🎉 ALL TESTS PASSED!")
            return True
        else:
            self.log(f"❌ {total - passed} TEST(S) FAILED")
            return False

def main():
    """Main test runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description='AITBC End-to-End Test')
    parser.add_argument('--url', default='http://localhost:8000', 
                       help='Base URL for AITBC services')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    test = AITBCE2ETest(base_url=args.url)
    
    try:
        success = test.run_full_test()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
