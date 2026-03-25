#!/usr/bin/env python3
"""
Test GPU registration with mock coordinator
"""

import httpx
import json

COORDINATOR_URL = "http://localhost:8090"

# Test available endpoints
print("=== Testing Mock Coordinator Endpoints ===")
endpoints = [
    "/",
    "/health",
    "/metrics",
    "/miners/register",
    "/miners/list",
    "/marketplace/offers"
]

for endpoint in endpoints:
    try:
        response = httpx.get(f"{COORDINATOR_URL}{endpoint}", timeout=5)
        print(f"{endpoint}: {response.status_code}")
        if response.status_code == 200 and response.text:
            try:
                data = response.json()
                print(f"  Response: {json.dumps(data, indent=2)[:200]}...")
            except:
                print(f"  Response: {response.text[:100]}...")
    except Exception as e:
        print(f"{endpoint}: Error - {e}")

print("\n=== Checking OpenAPI Spec ===")
try:
    response = httpx.get(f"{COORDINATOR_URL}/openapi.json", timeout=5)
    if response.status_code == 200:
        openapi = response.json()
        paths = list(openapi.get("paths", {}).keys())
        print(f"Available endpoints: {paths}")
    else:
        print(f"OpenAPI not available: {response.status_code}")
except Exception as e:
    print(f"Error getting OpenAPI: {e}")
