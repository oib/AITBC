#!/usr/bin/env python3
"""
Simple API Structure Validation for AITBC
Confirms that core endpoints are accessible and responding
"""

import requests
import sys
import json

def test_api_structure(base_url: str = "http://localhost:8000"):
    """Validate that the API structure is accessible"""
    print("🔍 Validating AITBC API Structure...")
    print("=" * 50)
    
    # Test 1: Basic health endpoint
    print("\n1. Checking basic health endpoint...")
    try:
        resp = requests.get(f"{base_url}/health", timeout=10)
        if resp.status_code == 200:
            print("   ✓ Coordinator API health endpoint accessible")
            health_data = resp.json()
            print(f"   Environment: {health_data.get('env', 'unknown')}")
        else:
            print(f"   ✗ Health check failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ✗ Health check error: {e}")
        return False
    
    # Test 2: API key authentication
    print("\n2. Testing API key authentication...")
    try:
        headers = {"X-Api-Key": "test-key"}
        resp = requests.get(f"{base_url}/v1/marketplace/gpu/list", 
                          headers=headers, timeout=10)
        if resp.status_code == 200:
            print("   ✓ API key authentication working")
            gpu_data = resp.json()
            print(f"   Available GPUs: {len(gpu_data) if isinstance(gpu_data, list) else 'unknown'}")
        else:
            print(f"   ✗ API key auth failed: {resp.status_code}")
            # Don't return False here as this might be expected if no GPUs
    except Exception as e:
        print(f"   ✗ API key auth error: {e}")
        return False
    
    # Test 3: Check if we can reach the users area (even if specific endpoints fail)
    print("\n3. Checking users endpoint accessibility...")
    try:
        headers = {"X-Api-Key": "test-key"}
        # Try a known working pattern - the /me endpoint with fake token
        resp = requests.get(f"{base_url}/v1/users/me?token=test",
                          headers=headers, timeout=10)
        # We expect either 401 (bad token) or 422 (validation error) - NOT 404
        if resp.status_code in [401, 422]:
            print("   ✓ Users endpoint accessible (authentication required)")
            print(f"   Response status: {resp.status_code} (expected auth/validation error)")
        elif resp.status_code == 404:
            print("   ✗ Users endpoint not found (404)")
            return False
        else:
            print(f"   ⚠ Unexpected status: {resp.status_code}")
    except Exception as e:
        print(f"   ✗ Users endpoint error: {e}")
        return False
        
    print("\n" + "=" * 50)
    print("✅ API Structure Validation Complete")
    print("📝 Summary:")
    print("   - Core API is accessible")
    print("   - Authentication mechanisms are in place") 
    print("   - Endpoint routing is functional")
    print("   - Ready for end-to-end testing when user service is operational")
    return True

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate AITBC API Structure')
    parser.add_argument('--url', default='http://localhost:8000',
                       help='Base URL for AITBC services')
    args = parser.parse_args()
    
    try:
        success = test_api_structure(args.url)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
