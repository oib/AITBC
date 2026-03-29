#!/usr/bin/env python3
"""CI test script for AITBC API endpoints."""

import requests
import json
import time
import statistics
import sys

# Service ports (must match systemd config)
SERVICES = {
    "coordinator": {"url": "http://localhost:8000", "endpoints": ["/", "/health", "/info"]},
    "exchange": {"url": "http://localhost:8001", "endpoints": ["/", "/api/health", "/health", "/info"]},
    "wallet": {"url": "http://localhost:8003", "endpoints": ["/", "/health", "/wallets"]},
    "blockchain_rpc": {"url": "http://localhost:8006", "endpoints": []},
}

RPC_METHODS = [
    {"method": "eth_blockNumber", "params": []},
    {"method": "eth_getBalance", "params": ["0x0000000000000000000000000000000000000000", "latest"]},
    {"method": "eth_chainId", "params": []},
    {"method": "eth_gasPrice", "params": []},
]


def test_service_endpoints(name, base_url, endpoints, timeout=5):
    results = {"service": name, "endpoints": [], "success": True}
    for ep in endpoints:
        url = f"{base_url}{ep}"
        try:
            r = requests.get(url, timeout=timeout)
            ok = r.status_code in (200, 404, 405)
            results["endpoints"].append({"url": url, "status": r.status_code, "success": ok})
            print(f"  {'✅' if ok else '❌'} {url}: {r.status_code}")
            if not ok:
                results["success"] = False
        except Exception as e:
            results["endpoints"].append({"url": url, "error": str(e), "success": False})
            print(f"  ❌ {url}: {e}")
            results["success"] = False
    return results


def test_rpc(base_url, timeout=5):
    results = {"service": "blockchain_rpc", "methods": [], "success": True}
    for m in RPC_METHODS:
        payload = {"jsonrpc": "2.0", "method": m["method"], "params": m["params"], "id": 1}
        try:
            r = requests.post(base_url, json=payload, timeout=timeout)
            ok = r.status_code == 200
            result_val = r.json().get("result", "N/A") if ok else None
            results["methods"].append({"method": m["method"], "status": r.status_code, "result": str(result_val), "success": ok})
            print(f"  {'✅' if ok else '❌'} {m['method']}: {result_val}")
            if not ok:
                results["success"] = False
        except Exception as e:
            results["methods"].append({"method": m["method"], "error": str(e), "success": False})
            print(f"  ❌ {m['method']}: {e}")
            results["success"] = False
    return results


def test_performance(apis, rounds=10, timeout=5):
    results = {}
    for name, url in apis:
        times = []
        ok_count = 0
        for i in range(rounds):
            try:
                t0 = time.time()
                r = requests.get(url, timeout=timeout)
                dt = time.time() - t0
                times.append(dt)
                if r.status_code in (200, 404, 405):
                    ok_count += 1
            except Exception:
                pass
        if times:
            results[name] = {
                "avg_ms": round(statistics.mean(times) * 1000, 1),
                "min_ms": round(min(times) * 1000, 1),
                "max_ms": round(max(times) * 1000, 1),
                "success_rate": f"{ok_count}/{rounds}",
            }
            print(f"  📊 {name}: avg={results[name]['avg_ms']}ms  ok={ok_count}/{rounds}")
        else:
            results[name] = {"error": "all requests failed"}
            print(f"  ❌ {name}: all requests failed")
    return results


def main():
    all_results = {}
    overall_ok = True

    for name, cfg in SERVICES.items():
        print(f"\n🧪 Testing {name}...")
        if name == "blockchain_rpc":
            r = test_rpc(cfg["url"])
        else:
            r = test_service_endpoints(name, cfg["url"], cfg["endpoints"])
        all_results[name] = r
        if not r["success"]:
            overall_ok = False

    print("\n⚡ Performance tests...")
    perf = test_performance([
        ("Coordinator", "http://localhost:8000/health"),
        ("Exchange", "http://localhost:8001/api/health"),
        ("Wallet", "http://localhost:8003/health"),
    ])
    all_results["performance"] = perf

    with open("api-test-results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'✅' if overall_ok else '⚠️'} API endpoint tests completed")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
