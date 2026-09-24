#!/usr/bin/env python3
"""
Extract OpenAPI specs from FastAPI applications and publish to docs/api/
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from openapi_error_responses import enrich  # noqa: E402  (after the sys.path setup above)

# Add AITBC to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "coordinator-api" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "blockchain-node" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "market" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "wallet" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "agent-coordinator" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api-gateway" / "src"))

# Defaults for services that require environment variables to import
os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
os.environ.setdefault("MARKET_DATABASE_URL", "sqlite+aiosqlite:///./test_market.db")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_api.db")
os.environ.setdefault("WALLET_BIND_PORT", "8108")
# A keystore directory, so not a fixed path: `/tmp/test_wallet` is guessable and shared, and
# two people generating specs on one host would have written keys into each other's. The
# wallet app only has to be able to construct its settings here; nothing reads this back.
os.environ.setdefault("WALLET_DIR", tempfile.mkdtemp(prefix="aitbc-openapi-wallet-"))
# The API key manager creates a file lock alongside its storage path. On a fresh CI runner
# /var/lib/aitbc does not exist and is not writable, so point it at a temp directory.
api_keys_dir = tempfile.mkdtemp(prefix="aitbc-openapi-apikeys-")
os.environ.setdefault("API_KEY_STORAGE_PATH", os.path.join(api_keys_dir, "api_keys.json"))
os.environ.setdefault("KEYSTORE_PASSWORD", "test-password")
os.environ.setdefault("WALLET_IMPORT_PASSWORD", "test-import-password")
os.environ.setdefault("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8202")
# agent-coordinator refuses to start without these; the values are irrelevant to the
# generated schema and never leave this process.
# Both must be at least 32 characters or the apps refuse to construct their settings.
os.environ.setdefault("SECRET_KEY", "openapi-spec-extraction-placeholder-key")
os.environ.setdefault("JWT_SECRET", "openapi-spec-extraction-placeholder-jwt")

# Assigned, not `setdefault`: this one decides what gets published, so it cannot be left to
# whatever the caller happens to have exported. coordinator-api gates 38 routes on
# `settings.debug` -- the agent, swarm and dashboard mock endpoints, in-memory and
# unauthenticated, whose own comments say "never enabled in production" -- and it also gates
# `/docs` and `/redoc`. Generating with DEBUG set therefore publishes a spec advertising mock
# endpoints as the API. `tests/integration/conftest.py` sets `DEBUG=true` for the session, so
# this is not hypothetical: any generation from inside a test process produced the wrong spec,
# which is how it was found (V23-82). The published spec is the production surface.
os.environ["DEBUG"] = "false"

# Same for the gateway's service URLs: api-v2-map.json records the upstream each
# qualifier forwards to, so generating on a host that exports MARKET_SERVICE_URL
# or friends would publish that host's topology into the committed file. Pop
# them so the map always records the deployment-agnostic defaults.
for _service_url_env in (
    "MARKET_SERVICE_URL",
    "MARKETPLACE_SERVICE_URL",
    "COORDINATOR_URL",
    "GOVERNANCE_SERVICE_URL",
    "EXCHANGE_SERVICE_URL",
    "TRADING_SERVICE_URL",
    "WALLET_SERVICE_URL",
    "AGENT_COORDINATOR_URL",
    "POOL_HUB_URL",
    "EXPLORER_SERVICE_URL",
):
    os.environ.pop(_service_url_env, None)

REPO_DIR = Path(__file__).parent.parent
DOCS_DIR = REPO_DIR / "docs"
API_DOCS_DIR = DOCS_DIR / "api"

# FastAPI applications to extract specs from
APPS = [
    {
        "name": "coordinator-api",
        "module": "coordinator_api.main:app",
        "output": "coordinator-api-openapi.json",
    },
    {
        "name": "blockchain-node",
        "module": "aitbc_chain.app:app",
        "output": "blockchain-node-openapi.json",
    },
    {
        "name": "market",
        "module": "market_service.main:app",
        "output": "market-openapi.json",
    },
    {
        "name": "wallet",
        "module": "wallet_app.main:app",
        "output": "wallet-openapi.json",
    },
    {
        # Was only ever published by hand as docs/openapi/agent.json, which had drifted to
        # 11 paths against the app's actual 100.
        "name": "agent-coordinator",
        "module": "agent_app.main:app",
        "output": "agent-coordinator-openapi.json",
    },
]


# Which /api/v2 qualifier each extracted app answers for. Apps without a
# committed spec still get a qualifier entry — the map documents the whole
# surface, with "spec": null marking the undocumented upstreams.
V2_QUALIFIER_FOR_APP = {
    "coordinator-api": "coordinator",
    "blockchain-node": "chain",
    "market": "market",
    "wallet": "wallet",
    "agent-coordinator": "agent-coordinator",
}

_V2_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def build_v2_map(specs: dict[str, dict]) -> dict:
    """The generated /api/v2 route map.

    Qualifiers and base URLs come from api_gateway.main's own tables, so the
    committed map cannot drift from what the gateway serves without the drift
    check noticing. Every spec path p on a service is reachable publicly at
    /api/v2/<qualifier><p> — the gateway forwards the remainder verbatim.
    """
    from api_gateway.main import _V2_SERVICE_ENV, _V2_SERVICE_URLS

    services: dict[str, dict] = {}
    for qualifier in sorted(_V2_SERVICE_URLS):
        app_name = next((a for a, q in V2_QUALIFIER_FOR_APP.items() if q == qualifier), None)
        spec = specs.get(app_name) if app_name else None
        operations = []
        if spec:
            for path, methods in sorted(spec.get("paths", {}).items()):
                operations.append(
                    {
                        "public": f"/api/v2/{qualifier}{path}",
                        "upstream": path,
                        "methods": sorted(m.upper() for m in methods if m.upper() in _V2_HTTP_METHODS),
                    }
                )
        services[qualifier] = {
            "env": _V2_SERVICE_ENV[qualifier],
            "base_url": _V2_SERVICE_URLS[qualifier],
            "spec": f"{app_name}-openapi.json" if app_name else None,
            "operations": operations,
        }
    return {
        "api": "v2",
        "public_prefix": "/api/v2",
        "gateway_prefix": "/v2",
        "rule": "/api/v2/<service>/<upstream path> forwards <upstream path> to the service verbatim",
        "services": services,
    }


def extract_openapi_spec(app_config: dict) -> dict | None:
    """Extract OpenAPI spec from a FastAPI application."""
    try:
        # Import the FastAPI app using importlib
        from importlib import import_module

        module_path, app_name = app_config["module"].split(":")
        module = import_module(module_path)
        app = getattr(module, app_name)

        # Get OpenAPI spec
        spec = app.openapi()
        # FastAPI infers responses from signatures, so it documents 2xx and 422 and nothing
        # else -- 703 operations across these five apps and not one 404, though 89 routes
        # return one. `enrich` reads the handlers and adds what they actually answer with
        # (V23-80).
        return enrich(spec, app)
    except Exception as e:
        print(f"Error extracting spec from {app_config['name']}: {e}")
        import traceback

        traceback.print_exc()
        return None


def main():
    """Extract OpenAPI specs from all configured applications."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=API_DOCS_DIR,
        help=(
            "Where to write the specs (default: docs/api). The drift check points this at a "
            "temporary directory so that asking whether the specs are current does not "
            "rewrite them."
        ),
    )
    args = parser.parse_args()
    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Extracting OpenAPI specs...")

    failed = []
    specs: dict[str, dict] = {}
    for app_config in APPS:
        print(f"  Extracting {app_config['name']}...")
        spec = extract_openapi_spec(app_config)

        if spec:
            specs[app_config["name"]] = spec
            output_path = out_dir / app_config["output"]
            with open(output_path, "w") as f:
                json.dump(spec, f, indent=2)
                # Trailing newline: pre-commit's end-of-file-fixer adds one, so without it
                # here every regeneration differs from what is committed and
                # `make openapi-check` reports drift that is not there.
                f.write("\n")
            print(f"    ✓ Saved to {output_path}")
        else:
            print(f"    ✗ Failed to extract {app_config['name']}")
            failed.append(app_config["name"])

    if not failed:
        v2_map = build_v2_map(specs)
        map_path = out_dir / "api-v2-map.json"
        with open(map_path, "w") as f:
            json.dump(v2_map, f, indent=2)
            f.write("\n")
        print(f"  ✓ Saved to {map_path}")

    print(f"\nOpenAPI specs saved to {out_dir}")

    # An app that will not import used to be reported on stdout and then forgotten: the
    # script exited 0, its stale spec stayed on disk untouched, and `make openapi-check`
    # diffed that stale file against itself and passed. The drift guard therefore reported
    # "no drift" for a service it had not managed to look at (V23-82). Extraction failing is
    # itself the finding -- either the app is broken or the placeholder environment above no
    # longer satisfies it -- so it fails the run.
    if failed:
        print(f"Extraction failed for: {', '.join(failed)}", file=sys.stderr)
        print("The specs for those apps are unchanged and cannot be trusted.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
