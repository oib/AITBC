"""Wallet-service client helpers for the exchange handlers.

The wallet balance/connect routes are served by ``exchange_queries.py``
(``handle_wallet_balance`` / ``handle_wallet_connect``). This module only
carries the shared client config those handlers use: the wallet daemon URL
and the auth headers for its admin-gated ``/v1/wallets`` routes.
"""

import os

WALLET_SERVICE_URL = os.getenv("WALLET_SERVICE_URL", "http://localhost:8108")


def wallet_auth_headers() -> dict[str, str]:
    """Auth headers for the wallet daemon.

    Its /v1/wallets routes are admin-gated, and the daemon accepts
    COORDINATOR_API_KEY when WALLET_API_KEY is unset. Both are in
    /etc/aitbc/blockchain-secrets.env, which this unit already loads.
    """
    key = os.getenv("WALLET_API_KEY") or os.getenv("COORDINATOR_API_KEY", "")
    if not key and os.getenv("AITBC_ENV", "").lower() == "production":
        # An empty key made this port an open submission proxy for the wallet
        # daemon (#1079): refuse rather than call without credentials.
        raise RuntimeError("WALLET_API_KEY/COORDINATOR_API_KEY unset — refusing unauthenticated wallet call")
    return {"X-API-Key": key} if key else {}
