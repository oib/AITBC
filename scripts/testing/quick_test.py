#!/usr/bin/env python3
"""Quick connectivity and latency probe against a running AITBC node.

Usage: quick_test.py [BASE_URL]   (or set AITBC_QUICK_TEST_URL)

Every probe declares the status codes it accepts and a mismatch is a failure, which is
the whole difference from what this used to do: it printed a green tick for whatever came
back, returned True either way, and left the process exiting 0. Pointed as it was at
https://aitbc.bubuit.net/api/v1/health -- a name that does not resolve from a node, and
a path the coordinator does not serve -- it could only ever have printed a red line, and
nothing downstream would have noticed if it had.
"""

import os
import sys
import time

import requests

DEFAULT_BASE_URL = "http://localhost:8203"

# (path, accepted status codes, headers).
#
# /v1/client/jobs is probed with a deliberately invalid key, so 401 is the pass: it proves
# the route is mounted and its auth runs. A 404 there would mean the path had moved, which
# is exactly the failure this file was blind to.
PROBES = [
    ("/health", {200}, None),
    ("/v1/client/jobs", {401, 403}, {"X-Api-Key": "test_key_16_characters"}),
]


def probe(url, expected, headers=None):
    """GET url, return True only if it answered with one of the expected codes."""
    wanted = "/".join(str(code) for code in sorted(expected))
    start = time.perf_counter()
    try:
        resp = requests.get(url, headers=headers, timeout=5)
    except requests.RequestException as exc:
        print(f"❌ {url}: {type(exc).__name__} after {time.perf_counter() - start:.3f}s - {exc}")
        return False

    elapsed = time.perf_counter() - start
    if resp.status_code in expected:
        print(f"✅ {url}: {resp.status_code} in {elapsed:.3f}s")
        return True

    print(f"❌ {url}: {resp.status_code} in {elapsed:.3f}s (expected {wanted})")
    return False


def main(argv):
    base = argv[1] if len(argv) > 1 else os.environ.get("AITBC_QUICK_TEST_URL", DEFAULT_BASE_URL)
    base = base.rstrip("/")

    print("🧪 Quick Performance Test")
    print(f"   target: {base}")
    print("=" * 30)

    failed = [path for path, expected, headers in PROBES if not probe(f"{base}{path}", expected, headers)]

    if failed:
        print(f"\n❌ {len(failed)} of {len(PROBES)} probes failed against {base}")
        return 1

    print(f"\n✅ All {len(PROBES)} probes passed against {base}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
