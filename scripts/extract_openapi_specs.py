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
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "marketplace" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "wallet" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "agent-coordinator" / "src"))

# Defaults for services that require environment variables to import
os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
os.environ.setdefault("MARKETPLACE_DATABASE_URL", "sqlite+aiosqlite:///./test_marketplace.db")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_api.db")
os.environ.setdefault("WALLET_BIND_PORT", "8108")
# A keystore directory, so not a fixed path: `/tmp/test_wallet` is guessable and shared, and
# two people generating specs on one host would have written keys into each other's. The
# wallet app only has to be able to construct its settings here; nothing reads this back.
os.environ.setdefault("WALLET_DIR", tempfile.mkdtemp(prefix="aitbc-openapi-wallet-"))
os.environ.setdefault("KEYSTORE_PASSWORD", "test-password")
os.environ.setdefault("WALLET_IMPORT_PASSWORD", "test-import-password")
os.environ.setdefault("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
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
        "name": "marketplace",
        "module": "marketplace_service.main:app",
        "output": "marketplace-openapi.json",
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
    for app_config in APPS:
        print(f"  Extracting {app_config['name']}...")
        spec = extract_openapi_spec(app_config)

        if spec:
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
