"""Plugin Service — real registry for AITBC software marketplace plugins."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException

logger = logging.getLogger(__name__)
_REGISTRY_PATH = Path(os.getenv("DATA_DIR", "/var/lib/aitbc")) / "plugins.json"
_HUB_RPC = os.getenv("HUB_RPC_URL", "https://hub.aitbc.bubuit.net/rpc")
app = FastAPI(
    title="AITBC Plugin Service",
    description="Plugin registry: discover Ollama, Whisper, PeerTube and other software marketplace services",
    version="2.0.0",
)


def _load() -> dict[str, Any]:
    if _REGISTRY_PATH.exists():
        try:
            return json.loads(_REGISTRY_PATH.read_text())
        except Exception:
            pass
    return {}


def _save(registry: dict[str, Any]) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


async def _resolve_offer_id(plugin: dict[str, Any]) -> str | None:
    """Live lookup: find the latest active software_offer on hub for this plugin."""
    service_type = plugin.get("service_type")
    model = plugin.get("model")
    provider_address = plugin.get("provider_address")
    if not service_type:
        return plugin.get("offer_id")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{_HUB_RPC}/transactions", params={"limit": 1000})
            if r.status_code == 200:
                txs = r.json()
                for tx in reversed(txs):
                    p = tx.get("payload", {})
                    if (
                        p.get("action") == "software_offer"
                        and p.get("service_type") == service_type
                        and (not model or p.get("model") == model)
                        and (not provider_address or p.get("provider_address") == provider_address)
                    ):
                        return p.get("offer_id")
    except Exception as e:
        logger.warning("Hub lookup failed: %s", e)
    return plugin.get("offer_id")


@app.get("/health")
async def health():
    registry = _load()
    return {"status": "ok", "service": "plugin-service", "registered_plugins": len(registry)}


@app.get("/")
async def root():
    return {"service": "AITBC Plugin Service", "version": "2.0.0", "endpoints": ["/plugins", "/plugins/{id}", "/register"]}


@app.post("/register")
async def register_plugin(request: dict[str, Any]) -> dict[str, Any]:
    """Register or update a plugin. Key fields: plugin_id, service_type, model, price, price_unit,
    offer_id, endpoint, public_endpoint, provider_address."""
    plugin_id = request.get("plugin_id")
    if not plugin_id:
        svc = request.get("service_type", "unknown")
        mdl = request.get("model", "")
        plugin_id = f"{svc}-{mdl}".strip("-").replace(":", "-").replace("/", "-")
    if not plugin_id:
        raise HTTPException(status_code=400, detail="plugin_id or service_type required")
    registry = _load()
    now = datetime.now(UTC).isoformat()
    entry = {
        **registry.get(plugin_id, {}),
        **{k: v for k, v in request.items() if v is not None},
        "plugin_id": plugin_id,
        "registered_at": registry.get(plugin_id, {}).get("registered_at", now),
        "updated_at": now,
        "status": request.get("status", "active"),
    }
    registry[plugin_id] = entry
    _save(registry)
    logger.info("Plugin registered: %s", plugin_id)
    return {"plugin_id": plugin_id, "status": "registered", "entry": entry}


@app.get("/plugins")
async def list_plugins(service_type: str | None = None, status: str | None = None) -> dict[str, Any]:
    """List all registered plugins, optionally filtered by service_type or status."""
    registry = _load()
    plugins = list(registry.values())
    if service_type:
        plugins = [p for p in plugins if p.get("service_type") == service_type]
    if status:
        plugins = [p for p in plugins if p.get("status") == status]
    return {"plugins": plugins, "total": len(plugins)}


@app.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str) -> dict[str, Any]:
    """Get a single plugin with live offer_id resolution from hub chain."""
    registry = _load()
    plugin = registry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    live_offer_id = await _resolve_offer_id(plugin)
    return {**plugin, "offer_id": live_offer_id}


@app.get("/plugins/{plugin_id}/offer")
async def get_plugin_offer(plugin_id: str) -> dict[str, Any]:
    """Resolve the latest active blockchain offer_id for this plugin."""
    registry = _load()
    plugin = registry.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    offer_id = await _resolve_offer_id(plugin)
    return {
        "plugin_id": plugin_id,
        "offer_id": offer_id,
        "service_type": plugin.get("service_type"),
        "model": plugin.get("model"),
        "price": plugin.get("price"),
        "price_unit": plugin.get("price_unit"),
    }


@app.delete("/plugins/{plugin_id}")
async def unregister_plugin(plugin_id: str) -> dict[str, Any]:
    """Unregister a plugin."""
    registry = _load()
    if plugin_id not in registry:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    del registry[plugin_id]
    _save(registry)
    return {"plugin_id": plugin_id, "status": "unregistered"}


@app.get("/analytics")
async def analytics() -> dict[str, Any]:
    registry = _load()
    by_type: dict[str, int] = {}
    for p in registry.values():
        t = p.get("service_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    return {
        "total_plugins": len(registry),
        "by_service_type": by_type,
        "active": sum(1 for p in registry.values() if p.get("status") == "active"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PLUGIN_PORT", "8016")))
