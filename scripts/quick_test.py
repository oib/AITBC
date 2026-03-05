#!/usr/bin/env python3
"""
Quick Performance Test
"""

import requests
import time

def test_endpoint(url, headers=None):
    start = time.time()
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        end = time.time()
        print(f"✅ {url}: {resp.status_code} in {end-start:.3f}s")
        return True
    except Exception as e:
        end = time.time()
        print(f"❌ {url}: Error in {end-start:.3f}s - {e}")
        return False

print("🧪 Quick Performance Test")
print("=" * 30)

# Test health endpoint
test_endpoint("https://aitbc.bubuit.net/api/v1/health")

# Test with API key
headers = {"X-Api-Key": "test_key_16_characters"}
test_endpoint("https://aitbc.bubuit.net/api/v1/client/jobs", headers)

print("\n✅ Basic connectivity test complete")
