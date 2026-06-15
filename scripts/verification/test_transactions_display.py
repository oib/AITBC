#!/usr/bin/env python3
"""
Test if transactions are displaying on the explorer
"""

import requests
from bs4 import BeautifulSoup


def main():
    print("🔍 Testing Transaction Display on Explorer")
    print("=" * 60)

    # Check API has transactions
    print("\n1. Checking API for transactions...")
    try:
        response = requests.get("https://aitbc.bubuit.net/api/explorer/transactions")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API has {len(data['items'])} transactions")

            if data["items"]:
                first_tx = data["items"][0]
                print("\n   First transaction:")
                print(f"   Hash: {first_tx['hash']}")
                print(f"   From: {first_tx['from']}")
                print(f"   To: {first_tx.get('to', 'null')}")
                print(f"   Value: {first_tx['value']}")
                print(f"   Status: {first_tx['status']}")
        else:
            print(f"❌ API failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # Check explorer page
    print("\n2. Checking explorer page...")
    try:
        response = requests.get("https://aitbc.bubuit.net/explorer/#/transactions")
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")

            # Check if it says "mock data"
            if "mock data" in soup.text.lower():
                print("❌ Page still shows 'mock data' message")
            else:
                print("✅ No 'mock data' message found")

            # Check for transactions table
            table = soup.find("tbody", {"id": "transactions-table-body"})
            if table:
                rows = table.find_all("tr")
                if len(rows) > 0:
                    if "Loading" in rows[0].text:
                        print("⏳ Still loading transactions...")
                    elif "No transactions" in rows[0].text:
                        print("❌ No transactions displayed")
                    else:
                        print(f"✅ Found {len(rows)} transaction rows")
                else:
                    print("❌ No transaction rows found")
            else:
                print("❌ Transactions table not found")
        else:
            print(f"❌ Failed to load page: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 60)
    print("\n💡 If transactions aren't showing, it might be because:")
    print("   1. JavaScript is still loading")
    print("   2. The API call is failing")
    print("   3. The transactions have empty values")
    print("\n   Try refreshing the page or check browser console for errors")


if __name__ == "__main__":
    main()
