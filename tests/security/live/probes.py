"""Live edge probes — read-only regression checks against a deployed AITBC edge.

These are NOT pytest tests: they issue real HTTP requests to a live target
(default ``https://hub.aitbc.bubuit.net``, override with
``AITBC_LIVE_BASE_URL``) and are meant for the nightly/ops tier, never the
pre-commit or fast CI gate.

Safety contract:

* **GET/HEAD only.** No POST/PUT/DELETE, no auth credentials, no mutations.
* **Skip-graceful.** Any connect/timeout/DNS failure marks the probe SKIP,
  never FAIL — an unreachable target is not a security regression.
* **Rate-limit probes are bounded and credential-gated.** The bucket probe
  sends at most ``AITBC_LIVE_RATELIMIT_PROBE_COUNT`` requests (default 105,
  just over the gateway's 100/min default) and only runs when
  ``AITBC_LIVE_GATEWAY_KEY`` is provided — the limiter counts requests only
  after ``verify_auth`` passes, so unauthenticated bursts prove nothing.
  Disable entirely with ``AITBC_LIVE_PROBE_RATELIMIT=0``.

Coverage map (what is and is not observable over plain GET):

* ``/exchange/`` wallet-admin bypass (#1200), ``/v1/wallets`` loopback gate,
  ``/exchange-api/`` public alias — directly observable status codes.
* Gateway ``X-Gateway-Key`` auth gate — observable 401/403 matrix (the valid
  key is a secret; only negative paths are probed).
* Rate-limit identity — observable only with a valid gateway key (the
  limiter runs after ``verify_auth``): once our bucket is exhausted,
  requests carrying a *forged* ``X-Forwarded-For`` must still get 429. If
  the limiter keyed on client-supplied XFF, the forged header would mint a
  fresh bucket and return a proxied response instead. Two-source bucket
  independence was verified manually during #1189; it is not re-probed
  here (single vantage point).
* ns2 ``realip`` trust scope (#1193) is NOT GET-observable — it lives in
  nginx ``$realip_remote_addr`` resolution and access logs. Covered by the
  #1193 live verification record; a log-side check belongs to ops, not
  this suite.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

import httpx

BASE_URL = os.environ.get("AITBC_LIVE_BASE_URL", "https://hub.aitbc.bubuit.net").rstrip("/")
TIMEOUT = float(os.environ.get("AITBC_LIVE_PROBE_TIMEOUT", "10"))
RATELIMIT_PROBE_COUNT = int(os.environ.get("AITBC_LIVE_RATELIMIT_PROBE_COUNT", "105"))
RATELIMIT_PROBE_ENABLED = os.environ.get("AITBC_LIVE_PROBE_RATELIMIT", "1") == "1"
# The gateway rate limiter sits inside the authenticated proxy handler —
# unauthenticated requests 401 at dependency resolution and never consume a
# bucket. The identity probe therefore needs a valid key, supplied out-of-band
# via env (never committed). Without it the probe SKIPs.
GATEWAY_KEY = os.environ.get("AITBC_LIVE_GATEWAY_KEY", "")


@dataclass
class ProbeResult:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str


def _get(client: httpx.Client, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return client.get(f"{BASE_URL}{path}", headers=headers or {}, timeout=TIMEOUT)


def _run(fn: Callable[[httpx.Client], ProbeResult]) -> ProbeResult:
    try:
        with httpx.Client(follow_redirects=False) as client:
            return fn(client)
    except (httpx.HTTPError, OSError) as exc:
        return ProbeResult(getattr(fn, "__name__", "probe"), "SKIP", f"unreachable: {exc}")


# --- route-scope probes (#1200, #1193-adjacent) ---


def wallet_admin_bypass_closed(client: httpx.Client) -> ProbeResult:
    """``/exchange/v1/wallets`` must NOT reach wallet admin routes (#1200)."""
    resp = _get(client, "/exchange/v1/wallets")
    if resp.status_code == 200:
        return ProbeResult("wallet_admin_bypass_closed", "FAIL", "200 — admin surface exposed")
    return ProbeResult("wallet_admin_bypass_closed", "PASS", f"{resp.status_code}")


def wallet_admin_direct_gated(client: httpx.Client) -> ProbeResult:
    """``/v1/wallets`` stays loopback-only at the edge."""
    resp = _get(client, "/v1/wallets")
    if resp.status_code == 200:
        return ProbeResult("wallet_admin_direct_gated", "FAIL", "200 — loopback gate open")
    return ProbeResult("wallet_admin_direct_gated", "PASS", f"{resp.status_code}")


def exchange_public_alias_alive(client: httpx.Client) -> ProbeResult:
    """Positive control: the legitimate public exchange read alias still works."""
    resp = _get(client, "/exchange-api/orderbook")
    if resp.status_code != 200:
        return ProbeResult("exchange_public_alias_alive", "FAIL", f"{resp.status_code} — public alias broken")
    return ProbeResult("exchange_public_alias_alive", "PASS", "200")


def bridge_admin_ops_not_public(client: httpx.Client) -> ProbeResult:
    """Bridge deposit verify/complete are admin ops — enumerable-list paths
    were already loopback-carved; spot-check a non-enumerable path does not
    resolve to an open admin handler (404/403/405 acceptable, never 200)."""
    resp = _get(client, "/v1/bridge/deposits/probe-nonexistent-id")
    if resp.status_code == 200:
        return ProbeResult("bridge_admin_ops_not_public", "FAIL", "200 on admin route")
    return ProbeResult("bridge_admin_ops_not_public", "PASS", f"{resp.status_code}")


# --- gateway auth gate (#1189-adjacent) ---


def gateway_missing_credentials_401(client: httpx.Client) -> ProbeResult:
    resp = _get(client, "/api/v1/health")
    if resp.status_code != 401:
        return ProbeResult("gateway_missing_credentials_401", "FAIL", f"{resp.status_code}")
    return ProbeResult("gateway_missing_credentials_401", "PASS", "401")


def gateway_wrong_key_403(client: httpx.Client) -> ProbeResult:
    resp = _get(client, "/api/v1/health", headers={"X-Gateway-Key": "live-probe-wrong-key"})
    if resp.status_code != 403:
        return ProbeResult("gateway_wrong_key_403", "FAIL", f"{resp.status_code}")
    return ProbeResult("gateway_wrong_key_403", "PASS", "403")


# --- rate-limit identity (#1189 / R9-4) ---


def rate_limit_bucket_and_xff(client: httpx.Client) -> ProbeResult:
    """Burst past the gateway limit with a valid key, then prove a forged XFF
    cannot mint a fresh bucket: post-exhaustion requests with
    ``X-Forwarded-For: 6.6.6.6`` must still be 429, not a proxied response."""
    if not RATELIMIT_PROBE_ENABLED:
        return ProbeResult("rate_limit_bucket_and_xff", "SKIP", "disabled via AITBC_LIVE_PROBE_RATELIMIT=0")
    if not GATEWAY_KEY:
        return ProbeResult(
            "rate_limit_bucket_and_xff",
            "SKIP",
            "AITBC_LIVE_GATEWAY_KEY unset — limiter only counts authenticated requests",
        )
    auth = {"X-Gateway-Key": GATEWAY_KEY}
    saw_429 = False
    for _ in range(RATELIMIT_PROBE_COUNT):
        resp = _get(client, "/api/v1/health", headers=auth)
        if resp.status_code == 429:
            saw_429 = True
            break
    if not saw_429:
        return ProbeResult(
            "rate_limit_bucket_and_xff",
            "SKIP",
            f"no 429 within {RATELIMIT_PROBE_COUNT} requests — limit higher than probe count",
        )
    forged = _get(client, "/api/v1/health", headers={**auth, "X-Forwarded-For": "6.6.6.6"})
    if forged.status_code != 429:
        return ProbeResult(
            "rate_limit_bucket_and_xff",
            "FAIL",
            f"forged XFF got {forged.status_code} after bucket exhaustion — limiter keys on spoofable header",
        )
    return ProbeResult("rate_limit_bucket_and_xff", "PASS", "429 held under forged XFF")


PROBES: list[Callable[[httpx.Client], ProbeResult]] = [
    wallet_admin_bypass_closed,
    wallet_admin_direct_gated,
    exchange_public_alias_alive,
    bridge_admin_ops_not_public,
    gateway_missing_credentials_401,
    gateway_wrong_key_403,
    rate_limit_bucket_and_xff,
]


def main() -> int:
    print(f"live probes against {BASE_URL} (timeout={TIMEOUT}s)")
    results = [_run(probe) for probe in PROBES]
    failures = 0
    for r in results:
        print(f"  [{r.status:4}] {r.name}: {r.detail}")
        if r.status == "FAIL":
            failures += 1
    print(
        f"{sum(1 for r in results if r.status == 'PASS')} pass, "
        f"{sum(1 for r in results if r.status == 'SKIP')} skip, {failures} fail"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
