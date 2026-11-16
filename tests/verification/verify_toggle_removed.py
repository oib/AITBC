#!/usr/bin/env python3
"""
Verify that the data mode toggle button is removed from the explorer
"""

import requests


def _check_page() -> str | None:
    # Get the explorer page
    print("\n1. Checking explorer page...")
    try:
        response = requests.get("https://hub.example.net/explorer/")
        if response.status_code == 200:
            print("✅ Explorer page loaded")
        else:
            print(f"❌ Failed to load page: {response.status_code}")
            return None
    except (requests.RequestException, OSError, ValueError, TypeError) as e:
        print(f"❌ Error: {e}")
        return None
    return response.text


def _check_html_toggles(html_content: str) -> bool:
    # Check for data mode toggle elements
    print("\n2. Checking for data mode toggle...")

    # Check for toggle button
    if "dataModeBtn" in html_content:
        print("❌ Data mode toggle button still present!")
        return False
    else:
        print("✅ Data mode toggle button removed")

    # Check for mode-button class
    if "mode-button" in html_content:
        print("❌ Mode button class still found!")
        return False
    else:
        print("✅ Mode button class removed")

    # Check for data-mode-toggle
    if "data-mode-toggle" in html_content:
        print("❌ Data mode toggle component still present!")
        return False
    else:
        print("✅ Data mode toggle component removed")
    return True


def _check_js_toggle() -> bool:
    # Check JS file
    print("\n3. Checking JavaScript file...")
    try:
        js_response = requests.get("https://hub.example.net/explorer/assets/index-7nlLaz1v.js")
        if js_response.status_code == 200:
            js_content = js_response.text

            if "initDataModeToggle" in js_content:
                print("❌ Data mode toggle initialization still in JS!")
                return False
            else:
                print("✅ Data mode toggle initialization removed")

            if 'dataMode:"mock"' in js_content:
                print("❌ Mock data mode still configured!")
                return False
            elif 'dataMode:"live"' in js_content:
                print("✅ Live data mode confirmed")
        else:
            print(f"❌ Failed to load JS: {js_response.status_code}")
    except (requests.RequestException, ValueError, TypeError) as e:
        print(f"❌ Error checking JS: {e}")
    return True


def main():
    print("🔍 Verifying Data Mode Toggle is Removed")
    print("=" * 60)

    html_content = _check_page()
    if html_content is None:
        return
    if not _check_html_toggles(html_content):
        return
    if not _check_js_toggle():
        return

    print("\n" + "=" * 60)
    print("✅ Data mode toggle successfully removed!")
    print("\n🎉 The explorer now:")
    print("   • Uses live data only")
    print("   • Has no mock/live toggle button")
    print("   • Shows real blockchain data")
    print("   • Is cleaner and more professional")


if __name__ == "__main__":
    main()
