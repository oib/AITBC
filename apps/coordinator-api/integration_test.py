#!/usr/bin/env python3
"""
AITBC Phase 5 Integration Testing Script
Tests all critical components for Phase 5 Integration & Production Deployment
"""

import requests
import json
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_api_health():
    """Test API health endpoints"""
    print("📡 Testing API Health...")
    try:
        live_response = requests.get('http://127.0.0.1:8000/health/live', timeout=5)
        ready_response = requests.get('http://127.0.0.1:8000/health/ready', timeout=5)
        
        if live_response.status_code == 200 and ready_response.status_code == 200:
            print("✅ API Health: PASSED")
            print(f"   Live Status: {live_response.json()['status']}")
            print(f"   Ready Status: {ready_response.json()['status']}")
            return True
        else:
            print("❌ API Health: FAILED")
            return False
    except Exception as e:
        print(f"❌ API Health: ERROR - {str(e)}")
        return False

def test_zk_service():
    """Test ZK Proof Service"""
    print("\n🔐 Testing ZK Proof Service...")
    try:
        from app.services.zk_proofs import ZKProofService
        zk_service = ZKProofService()
        circuits = list(zk_service.available_circuits.keys())
        if len(circuits) == 4:
            print("✅ ZK Proof Service: PASSED")
            print(f"   Available Circuits: {circuits}")
            return True
        else:
            print("❌ ZK Proof Service: FAILED - Not all circuits available")
            return False
    except Exception as e:
        print(f"❌ ZK Proof Service: ERROR - {str(e)}")
        return False

def test_fhe_service():
    """Test FHE Service"""
    print("\n🔒 Testing FHE Service...")
    try:
        from app.services.fhe_service import FHEService
        fhe_service = FHEService()
        providers = list(fhe_service.providers.keys())
        if 'tenseal' in providers:
            print("✅ FHE Service: PASSED")
            print(f"   Available Providers: {providers}")
            return True
        else:
            print("❌ FHE Service: FAILED - TenSEAL not available")
            return False
    except Exception as e:
        print(f"❌ FHE Service: ERROR - {str(e)}")
        return False

def test_ml_zk_integration():
    """Test ML-ZK Integration"""
    print("\n🤖 Testing ML-ZK Integration...")
    try:
        mlzk_response = requests.get('http://127.0.0.1:8000/v1/ml-zk/circuits', timeout=5)
        if mlzk_response.status_code == 200:
            circuits = mlzk_response.json()['circuits']
            print("✅ ML-ZK Integration: PASSED")
            print(f"   ML Circuits Available: {len(circuits)}")
            for circuit in circuits:
                print(f"   - {circuit['name']}: {circuit['security_level']}")
            return True
        else:
            print("❌ ML-ZK Integration: FAILED")
            return False
    except Exception as e:
        print(f"❌ ML-ZK Integration: ERROR - {str(e)}")
        return False

def test_database_integration():
    """Test Database Integration"""
    print("\n💾 Testing Database Integration...")
    try:
        ready_response = requests.get('http://127.0.0.1:8000/health/ready', timeout=5)
        if ready_response.json().get('database') == 'connected':
            print("✅ Database Integration: PASSED")
            print("   Database Status: Connected")
            return True
        else:
            print("❌ Database Integration: FAILED")
            return False
    except Exception as e:
        print(f"❌ Database Integration: ERROR - {str(e)}")
        return False

def main():
    """Run all integration tests"""
    print("🚀 AITBC Phase 5 Integration Testing - Starting Now!")
    print("=" * 60)
    
    tests = [
        test_api_health,
        test_zk_service,
        test_fhe_service,
        test_ml_zk_integration,
        test_database_integration
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    print("🎯 Integration Testing Summary:")
    
    passed = sum(results)
    total = len(results)
    
    print(f"   Tests Passed: {passed}/{total}")
    print(f"   Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("\n🚀 Phase 5.1 Integration Testing: COMPLETED SUCCESSFULLY!")
        print("📋 Ready for Phase 5.2: Production Deployment!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review and fix issues.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
