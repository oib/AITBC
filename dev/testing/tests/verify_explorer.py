#!/usr/bin/env python3
"""
Quick verification script to test Explorer endpoints
"""

import asyncio
import httpx
import sys
from pathlib import Path

# Add the blockchain-explorer to Python path
sys.path.append(str(Path(__file__).parent / "apps" / "blockchain-explorer"))

async def test_explorer_endpoints():
    """Test if Explorer endpoints are accessible and working"""
    
    # Test local Explorer (default port)
    explorer_urls = [
        "http://localhost:8000",
        "http://localhost:8080", 
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080"
    ]
    
    print("🔍 Testing Explorer endpoints...")
    
    for base_url in explorer_urls:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Test health endpoint
                health_response = await client.get(f"{base_url}/health")
                if health_response.status_code == 200:
                    print(f"✅ Explorer found at: {base_url}")
                    
                    # Test transaction endpoint with sample hash
                    sample_tx = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
                    tx_response = await client.get(f"{base_url}/api/transactions/{sample_tx}")
                    
                    if tx_response.status_code == 404:
                        print(f"✅ Transaction endpoint exists (404 for non-existent tx is expected)")
                    elif tx_response.status_code == 200:
                        print(f"✅ Transaction endpoint working")
                    else:
                        print(f"⚠️  Transaction endpoint returned: {tx_response.status_code}")
                    
                    # Test chain head endpoint
                    head_response = await client.get(f"{base_url}/api/chain/head")
                    if head_response.status_code == 200:
                        print(f"✅ Chain head endpoint working")
                    else:
                        print(f"⚠️  Chain head endpoint returned: {head_response.status_code}")
                    
                    return True
                    
        except Exception as e:
            continue
    
    print("❌ No running Explorer found on common ports")
    return False

async def test_explorer_code():
    """Test the Explorer code directly"""
    
    print("\n🔍 Testing Explorer code structure...")
    
    try:
        # Import the Explorer app
        from main import app
        
        # Check if transaction endpoint exists
        for route in app.routes:
            if hasattr(route, 'path') and '/api/transactions/' in route.path:
                print(f"✅ Transaction endpoint found: {route.path}")
                break
        else:
            print("❌ Transaction endpoint not found in routes")
            return False
            
        # Check if chain head endpoint exists  
        for route in app.routes:
            if hasattr(route, 'path') and '/api/chain/head' in route.path:
                print(f"✅ Chain head endpoint found: {route.path}")
                break
        else:
            print("❌ Chain head endpoint not found in routes")
            return False
            
        print("✅ All required endpoints found in Explorer code")
        return True
        
    except ImportError as e:
        print(f"❌ Cannot import Explorer app: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing Explorer code: {e}")
        return False

async def main():
    """Main verification"""
    
    print("🚀 AITBC Explorer Verification")
    print("=" * 50)
    
    # Test code structure
    code_ok = await test_explorer_code()
    
    # Test running instance
    running_ok = await test_explorer_endpoints()
    
    print("\n" + "=" * 50)
    print("📊 Verification Results:")
    print(f"Code Structure: {'✅ OK' if code_ok else '❌ ISSUES'}")
    print(f"Running Instance: {'✅ OK' if running_ok else '❌ NOT FOUND'}")
    
    if code_ok and not running_ok:
        print("\n💡 Recommendation: Start the Explorer server")
        print("   cd apps/blockchain-explorer && python main.py")
    elif code_ok and running_ok:
        print("\n🎉 Explorer is fully functional!")
    else:
        print("\n⚠️  Issues found - check implementation")

if __name__ == "__main__":
    asyncio.run(main())
