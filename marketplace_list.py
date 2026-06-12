#!/usr/bin/env python3
"""Simple marketplace listing viewer - no full CLI dependencies"""

import sys

import requests

RPC_URL = "http://127.0.0.1:8202"

def list_marketplace():
    """List all marketplace offers from blockchain"""
    try:
        response = requests.get(f"{RPC_URL}/rpc/marketplace/listings", timeout=10)
        response.raise_for_status()
        data = response.json()

        listings = data.get("listings", [])
        total = data.get("total", 0)

        print(f"📦 Marketplace Listings ({total} total)")
        print("=" * 60)

        for listing in listings:
            print(f"\nID: {listing['listing_id']}")
            print(f"  Seller: {listing['seller_address']}")
            print(f"  Type: {listing['item_type']}")
            print(f"  Price: {listing['price']} AIT")
            print(f"  Status: {listing['status']}")
            if listing.get('description'):
                print(f"  Description: {listing['description'][:80]}...")
            print(f"  Created: {listing['created_at']}")

        return 0
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(list_marketplace())
