#!/usr/bin/env python3
"""
AITBC Blockchain Explorer API
Agent-first API for blockchain data access
"""

import os

import httpx
import uvicorn
from fastapi import FastAPI

from aitbc.aitbc_logging import configure_logging, get_logger
from aitbc.health_checks import create_simple_health_response
from aitbc.rate_limiting import RateLimitMiddleware, client_ip_for_rate_limit, parse_rate_limit

configure_logging(level="INFO", service_name="blockchain-explorer", to_file=True)
logger = get_logger(__name__)

from chain_client import default_chain_id, rpc_url_for  # noqa: E402
from routers.alerts import router as alerts_router  # noqa: E402
from routers.analytics import router as analytics_router  # noqa: E402
from routers.blocks import router as blocks_router  # noqa: E402
from routers.chains import router as chains_router  # noqa: E402
from routers.csp import router as csp_router  # noqa: E402
from routers.export import router as export_router  # noqa: E402
from routers.journal import router as journal_router  # noqa: E402
from routers.messages import router as messages_router  # noqa: E402
from routers.search import router as search_router  # noqa: E402
from routers.transactions import router as transactions_router  # noqa: E402

app = FastAPI(title="AITBC Blockchain Explorer API", version="2.0.0")

app.include_router(chains_router)
app.include_router(alerts_router)
app.include_router(analytics_router)
app.include_router(blocks_router)
app.include_router(transactions_router)
app.include_router(search_router)
app.include_router(export_router)
app.include_router(journal_router)
app.include_router(messages_router)
app.include_router(csp_router)

# EXPLORER-DEEP2-1 (#1745): every read endpoint was unauthenticated and
# unbounded in request rate — the block endpoints alone can serialize
# ~40k embedded tx rows per call. nginx's explorer_api zone only covers the
# /explorer-api/ location on hosts that deploy it; the service also binds
# directly via EXPLORER_BIND_HOST, so the bound lives in-app too. Keyed per
# client IP through the shared resolver: X-Real-IP/X-Forwarded-For are
# honoured only from trusted proxies (#1244), so nginx-fronted traffic keys
# on the real client and a direct bind keys on the TCP peer. /health stays
# exempt so probes cannot trip it. EXPLORER_RATE_LIMIT overrides the default
# ("<count>/<second|minute|hour|day>", same grammar as the other services).
_explorer_rate, _explorer_per = parse_rate_limit(os.getenv("EXPLORER_RATE_LIMIT", "120/minute"))
app.add_middleware(
    RateLimitMiddleware,
    rate=_explorer_rate,
    per=_explorer_per,
    key_func=client_ip_for_rate_limit,
    exclude_paths=["/health"],
    error_message="Explorer rate limit exceeded",
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint"""
    try:
        # Test blockchain node connectivity
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{rpc_url_for(default_chain_id())}/rpc/head", timeout=5.0)
            node_status = "ok" if response.status_code == 200 else "error"
    except Exception:
        node_status = "error"

    return create_simple_health_response(
        "blockchain-explorer",
        version="2.0.0",
        status="ok" if node_status == "ok" else "degraded",
        node_status=node_status,
        features="advanced_search,analytics,export,real_time",
    )


if __name__ == "__main__":
    # Bind policy (docs/deployment/NETWORK_POLICY.md): this is a proxied backend.
    # The bind was hardcoded to 0.0.0.0 with no way to override it, which on a
    # firewall-less host published the explorer to anyone who could route here.
    # It now defaults to loopback. Hosts whose nginx serves /explorer-api/ from a
    # DIFFERENT machine must set EXPLORER_BIND_HOST to this host's private
    # interface address -- loopback would break the proxy.
    host = os.getenv("EXPLORER_BIND_HOST", "127.0.0.1")
    port = int(os.getenv("EXPLORER_BIND_PORT", "8100"))
    uvicorn.run(app, host=host, port=port, log_level="critical", access_log=False)
