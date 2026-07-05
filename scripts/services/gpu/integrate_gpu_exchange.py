#!/usr/bin/env python3
"""
Integrate GPU Miner with existing Trade Exchange

Note: The exchange frontend (index.html, server.py) was removed in v0.10.3.
The exchange is now a pure API service (simple_exchange.server on port 8106).
GPU marketplace integration should be done via the marketplace service API,
not by editing HTML files.
"""

# Configuration
EXCHANGE_URL = "http://localhost:8106"
GPU_REGISTRY_URL = "http://localhost:8091"


def show_gpu_api_integration():
    """Show how to add a GPU endpoint to the exchange API"""

    api_code = """
# Add to apps/exchange/simple_exchange/handlers/gpu.py:

from .base import RPC_BASE_URL, RPC_TIMEOUT


class GpuMixin:
    def handle_gpu_offers(self):
        \"\"\"GET /api/gpu/offers — list available GPU offers from the GPU registry\"\"\"
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(f"{GPU_REGISTRY_URL}/miners/list", timeout=RPC_TIMEOUT) as response:
                data = json.loads(response.read().decode())
                self.send_json_response({"offers": data.get("gpus", [])})
        except Exception as e:
            self.send_json_response(
                {"error": f"GPU registry unavailable: {e}", "offers": []},
                status=503,
            )

# Then register the route in server.py:
#   ("GET", "/api/gpu/offers", handler.handle_gpu_offers),
"""

    print("📝 To add GPU API endpoint to the exchange:")
    print(api_code)


def main():
    print("🔗 Integrating GPU Miner with Trade Exchange...")
    print()
    print(f"  Exchange API:  {EXCHANGE_URL}")
    print(f"  GPU Registry:  {GPU_REGISTRY_URL}/miners/list")
    print()
    print("ℹ️  The exchange frontend was removed in v0.10.3.")
    print("    GPU integration is now done via the exchange API, not HTML editing.")
    print()

    # Show API integration code
    show_gpu_api_integration()

    print("📊 Integration Summary:")
    print("1. 📝 See above for API endpoint code")
    print(f"2. 🌐 Exchange API available at: {EXCHANGE_URL}")
    print(f"3. 🎯 GPU Registry available at: {GPU_REGISTRY_URL}/miners/list")
    print()
    print("🔄 To test the integrated GPU marketplace:")
    print("1. Restart the exchange: sudo systemctl restart aitbc-exchange")
    print(f"2. Query the exchange API: curl {EXCHANGE_URL}/api/gpu/offers")
    print(f"3. Query the GPU registry: curl {GPU_REGISTRY_URL}/miners/list")


if __name__ == "__main__":
    main()
