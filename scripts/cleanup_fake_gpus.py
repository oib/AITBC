#!/usr/bin/env python3
"""
Script to clean up fake GPU entries from the marketplace
"""

import requests
import sys

def delete_fake_gpu(gpu_id):
    """Delete a fake GPU from the marketplace"""
    try:
        response = requests.delete(f"http://localhost:8000/v1/marketplace/gpu/{gpu_id}")
        if response.status_code == 200:
            print(f"✅ Successfully deleted fake GPU: {gpu_id}")
            return True
        else:
            print(f"❌ Failed to delete {gpu_id}: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error deleting {gpu_id}: {e}")
        return False

def main():
    """Main cleanup function"""
    print("=== CLEANING UP FAKE GPU OFFERS ===")
    
    # List of fake GPU IDs to delete
    fake_gpus = [
        "gpu_1bdf8e86",
        "gpu_1b7da9e0", 
        "gpu_9cff5bc2",
        "gpu_ebef80a5",
        "gpu_979b24b8",
        "gpu_e5ab817d"
    ]
    
    print(f"Found {len(fake_gpus)} fake GPUs to delete")
    
    deleted_count = 0
    for gpu_id in fake_gpus:
        if delete_fake_gpu(gpu_id):
            deleted_count += 1
    
    print(f"\n🎉 Cleanup complete! Deleted {deleted_count}/{len(fake_gpus)} fake GPUs")
    
    # Show remaining GPUs
    print("\n📋 Remaining GPUs in marketplace:")
    try:
        response = requests.get("http://localhost:8000/v1/marketplace/gpu/list")
        if response.status_code == 200:
            data = response.json()
            if 'items' in data:
                for gpu in data['items']:
                    print(f"  🎮 {gpu['id']}: {gpu['model']} - {gpu['status']}")
            else:
                print("  No GPUs found")
        else:
            print(f"  Error fetching GPU list: {response.status_code}")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    main()
