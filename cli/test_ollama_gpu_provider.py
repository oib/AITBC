#!/usr/bin/env python3
"""
Ollama GPU Provider Test
Submits an inference job with prompt "hello" and verifies completion.
"""

import argparse
import sys
import time
from typing import Optional

import httpx

DEFAULT_COORDINATOR = "http://127.0.0.1:18000"
DEFAULT_API_KEY = "REDACTED_CLIENT_KEY"
DEFAULT_PROMPT = "hello"
DEFAULT_TIMEOUT = 180
POLL_INTERVAL = 3


def submit_job(client: httpx.Client, base_url: str, api_key: str, prompt: str) -> Optional[str]:
    payload = {
        "payload": {
            "type": "inference",
            "prompt": prompt,
            "parameters": {"prompt": prompt},
        },
        "ttl_seconds": 900,
    }
    response = client.post(
        f"{base_url}/v1/jobs",
        headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    if response.status_code != 201:
        print(f"❌ Job submission failed: {response.status_code} {response.text}")
        return None
    return response_seen_id(response)


def response_seen_id(response: httpx.Response) -> Optional[str]:
    try:
        return response.json().get("job_id")
    except Exception:
        return None


def fetch_status(client: httpx.Client, base_url: str, api_key: str, job_id: str) -> Optional[dict]:
    response = client.get(
        f"{base_url}/v1/jobs/{job_id}",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Status check failed: {response.status_code} {response.text}")
        return None
    return response.json()


def fetch_result(client: httpx.Client, base_url: str, api_key: str, job_id: str) -> Optional[dict]:
    response = client.get(
        f"{base_url}/v1/jobs/{job_id}/result",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    if response.status_code != 200:
        print(f"❌ Result fetch failed: {response.status_code} {response.text}")
        return None
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ollama GPU provider end-to-end test")
    parser.add_argument("--url", default=DEFAULT_COORDINATOR, help="Coordinator base URL")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Client API key")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt to send")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds")
    args = parser.parse_args()

    with httpx.Client() as client:
        print("🧪 Submitting GPU provider job...")
        job_id = submit_job(client, args.url, args.api_key, args.prompt)
        if not job_id:
            return 1
        print(f"✅ Job submitted: {job_id}")

        deadline = time.time() + args.timeout
        status = None
        while time.time() < deadline:
            status = fetch_status(client, args.url, args.api_key, job_id)
            if not status:
                return 1
            state = status.get("state")
            print(f"⏳ Job state: {state}")
            if state == "COMPLETED":
                break
            if state in {"FAILED", "CANCELED", "EXPIRED"}:
                print(f"❌ Job ended in state: {state}")
                return 1
            time.sleep(POLL_INTERVAL)

        if not status or status.get("state") != "COMPLETED":
            print("❌ Job did not complete within timeout")
            return 1

        result = fetch_result(client, args.url, args.api_key, job_id)
        if result is None:
            return 1

        payload = result.get("result") or {}
        output = payload.get("output")
        receipt = result.get("receipt")
        if not output:
            print("❌ Missing output in job result")
            return 1
        if not receipt:
            print("❌ Missing receipt in job result (payment/settlement not recorded)")
            return 1

        print("✅ GPU provider job completed")
        print(f"📝 Output: {output}")
        print(f"🧾 Receipt ID: {receipt.get('receipt_id')}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
