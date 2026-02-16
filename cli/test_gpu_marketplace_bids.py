#!/usr/bin/env python3
"""
GPU Marketplace Bids Test
Tests complete marketplace bid workflow: offers listing → bid submission → bid tracking.
"""

import argparse
import sys
import time
from typing import Optional

import httpx

DEFAULT_COORDINATOR = "http://localhost:8000"
DEFAULT_API_KEY = "${CLIENT_API_KEY}"
DEFAULT_PROVIDER = "test_miner_123"
DEFAULT_CAPACITY = 100
DEFAULT_PRICE = 0.05
DEFAULT_TIMEOUT = 300
POLL_INTERVAL = 5


def list_offers(client: httpx.Client, base_url: str, api_key: str, 
                status: Optional[str] = None, gpu_model: Optional[str] = None) -> Optional[dict]:
    """List marketplace offers with optional filters"""
    params = {"limit": 20}
    if status:
        params["status"] = status
    if gpu_model:
        params["gpu_model"] = gpu_model
    
    response = client.get(
        f"{base_url}/v1/marketplace/offers",
        headers={"X-Api-Key": api_key},
        params=params,
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to list offers: {response.status_code} {response.text}")
        return None
    return response.json()


def submit_bid(client: httpx.Client, base_url: str, api_key: str, 
               provider: str, capacity: int, price: float, 
               notes: Optional[str] = None) -> Optional[str]:
    """Submit a marketplace bid"""
    payload = {
        "provider": provider,
        "capacity": capacity,
        "price": price
    }
    if notes:
        payload["notes"] = notes
    
    response = client.post(
        f"{base_url}/v1/marketplace/bids",
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    if response.status_code != 202:
        print(f"❌ Bid submission failed: {response.status_code} {response.text}")
        return None
    return response.json().get("id")


def list_bids(client: httpx.Client, base_url: str, api_key: str,
              status: Optional[str] = None, provider: Optional[str] = None) -> Optional[dict]:
    """List marketplace bids with optional filters"""
    params = {"limit": 20}
    if status:
        params["status"] = status
    if provider:
        params["provider"] = provider
    
    response = client.get(
        f"{base_url}/v1/marketplace/bids",
        headers={"X-Api-Key": api_key},
        params=params,
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to list bids: {response.status_code} {response.text}")
        return None
    return response.json()


def get_bid_details(client: httpx.Client, base_url: str, api_key: str, bid_id: str) -> Optional[dict]:
    """Get detailed information about a specific bid"""
    response = client.get(
        f"{base_url}/v1/marketplace/bids/{bid_id}",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to get bid details: {response.status_code} {response.text}")
        return None
    return response.json()


def get_marketplace_stats(client: httpx.Client, base_url: str, api_key: str) -> Optional[dict]:
    """Get marketplace statistics"""
    response = client.get(
        f"{base_url}/v1/marketplace/stats",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Failed to get marketplace stats: {response.status_code} {response.text}")
        return None
    return response.json()


def monitor_bid_status(client: httpx.Client, base_url: str, api_key: str, 
                      bid_id: str, timeout: int) -> Optional[str]:
    """Monitor bid status until it's accepted/rejected or timeout"""
    deadline = time.time() + timeout
    
    while time.time() < deadline:
        bid_details = get_bid_details(client, base_url, api_key, bid_id)
        if not bid_details:
            return None
            
        status = bid_details.get("status")
        print(f"⏳ Bid status: {status}")
        
        if status in {"accepted", "rejected"}:
            return status
        
        time.sleep(POLL_INTERVAL)
    
    print("❌ Bid status monitoring timed out")
    return None


def test_basic_workflow(client: httpx.Client, base_url: str, api_key: str,
                       provider: str, capacity: int, price: float) -> bool:
    """Test basic marketplace bid workflow"""
    print("🧪 Testing basic marketplace bid workflow...")
    
    # Step 1: List available offers
    print("📋 Listing marketplace offers...")
    offers = list_offers(client, base_url, api_key, status="open")
    if not offers:
        print("❌ Failed to list offers")
        return False
    
    offers_list = offers.get("offers", [])
    print(f"✅ Found {len(offers_list)} open offers")
    
    if offers_list:
        print("📊 Sample offers:")
        for i, offer in enumerate(offers_list[:3]):  # Show first 3 offers
            print(f"  {i+1}. {offer.get('gpu_model', 'Unknown')} - ${offer.get('price', 0):.4f}/hr - {offer.get('provider', 'Unknown')}")
    
    # Step 2: Submit bid
    print(f"💰 Submitting bid: {capacity} units at ${price:.4f}/unit from {provider}")
    bid_id = submit_bid(client, base_url, api_key, provider, capacity, price, 
                       notes="Test bid for GPU marketplace")
    if not bid_id:
        print("❌ Failed to submit bid")
        return False
    
    print(f"✅ Bid submitted: {bid_id}")
    
    # Step 3: Get bid details
    print("📄 Getting bid details...")
    bid_details = get_bid_details(client, base_url, api_key, bid_id)
    if not bid_details:
        print("❌ Failed to get bid details")
        return False
    
    print(f"✅ Bid details: {bid_details['provider']} - {bid_details['capacity']} units - ${bid_details['price']:.4f}/unit - {bid_details['status']}")
    
    # Step 4: List bids to verify it appears
    print("📋 Listing bids to verify...")
    bids = list_bids(client, base_url, api_key, provider=provider)
    if not bids:
        print("❌ Failed to list bids")
        return False
    
    bids_list = bids.get("bids", [])
    our_bid = next((b for b in bids_list if b.get("id") == bid_id), None)
    if not our_bid:
        print("❌ Submitted bid not found in bid list")
        return False
    
    print(f"✅ Bid found in list: {our_bid['status']}")
    
    return True


def test_competitive_bidding(client: httpx.Client, base_url: str, api_key: str) -> bool:
    """Test competitive bidding scenario with multiple providers"""
    print("🧪 Testing competitive bidding scenario...")
    
    # Submit multiple bids from different providers
    providers = ["provider_alpha", "provider_beta", "provider_gamma"]
    bid_ids = []
    
    for i, provider in enumerate(providers):
        price = 0.05 - (i * 0.01)  # Decreasing prices
        print(f"💰 {provider} submitting bid at ${price:.4f}/unit")
        
        bid_id = submit_bid(client, base_url, api_key, provider, 50, price, 
                           notes=f"Competitive bid from {provider}")
        if not bid_id:
            print(f"❌ {provider} failed to submit bid")
            return False
        
        bid_ids.append((provider, bid_id))
        time.sleep(1)  # Small delay between submissions
    
    print(f"✅ All {len(bid_ids)} competitive bids submitted")
    
    # List all bids to see the competition
    all_bids = list_bids(client, base_url, api_key)
    if not all_bids:
        print("❌ Failed to list all bids")
        return False
    
    bids_list = all_bids.get("bids", [])
    competitive_bids = [b for b in bids_list if b.get("provider") in providers]
    
    print(f"📊 Found {len(competitive_bids)} competitive bids:")
    for bid in sorted(competitive_bids, key=lambda x: x.get("price", 0)):
        print(f"  {bid['provider']}: ${bid['price']:.4f}/unit - {bid['status']}")
    
    return True


def test_marketplace_stats(client: httpx.Client, base_url: str, api_key: str) -> bool:
    """Test marketplace statistics functionality"""
    print("🧪 Testing marketplace statistics...")
    
    stats = get_marketplace_stats(client, base_url, api_key)
    if not stats:
        print("❌ Failed to get marketplace stats")
        return False
    
    print(f"📊 Marketplace Statistics:")
    print(f"  Total offers: {stats.get('totalOffers', 0)}")
    print(f"  Open capacity: {stats.get('openCapacity', 0)}")
    print(f"  Average price: ${stats.get('averagePrice', 0):.4f}")
    print(f"  Active bids: {stats.get('activeBids', 0)}")
    
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="GPU marketplace bids end-to-end test")
    parser.add_argument("--url", default=DEFAULT_COORDINATOR, help="Coordinator base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Client API key")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="Provider ID for bids")
    parser.add_argument("--capacity", type=int, default=DEFAULT_CAPACITY, help="Bid capacity")
    parser.add_argument("--price", type=float, default=DEFAULT_PRICE, help="Price per unit")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    parser.add_argument("--test", choices=["basic", "competitive", "stats", "all"], 
                       default="all", help="Test scenario to run")
    args = parser.parse_args()

    with httpx.Client() as client:
        print("🚀 Starting GPU marketplace bids test...")
        print(f"📍 Coordinator: {args.url}")
        print(f"🆔 Provider: {args.provider}")
        print(f"💰 Bid: {args.capacity} units at ${args.price:.4f}/unit")
        print()
        
        success = True
        
        if args.test in ["basic", "all"]:
            success &= test_basic_workflow(client, args.url, args.api_key, 
                                        args.provider, args.capacity, args.price)
            print()
        
        if args.test in ["competitive", "all"]:
            success &= test_competitive_bidding(client, args.url, args.api_key)
            print()
        
        if args.test in ["stats", "all"]:
            success &= test_marketplace_stats(client, args.url, args.api_key)
            print()
        
        if success:
            print("✅ All marketplace bid tests completed successfully!")
            return 0
        else:
            print("❌ Some marketplace bid tests failed!")
            return 1


if __name__ == "__main__":
    sys.exit(main())
