#!/usr/bin/env python3
"""
Extract OpenAPI specs from FastAPI applications and publish to docs/api/
"""

import json
import sys
from pathlib import Path

# Add AITBC to path
sys.path.insert(0, str(Path(__file__).parent.parent))

REPO_DIR = Path(__file__).parent.parent
DOCS_DIR = REPO_DIR / "docs"
API_DOCS_DIR = DOCS_DIR / "api"

# Create api docs directory
API_DOCS_DIR.mkdir(exist_ok=True)

# FastAPI applications to extract specs from
APPS = [
    {
        "name": "coordinator-api",
        "module": "apps.coordinator_api.src.app.main:app",
        "output": "coordinator-api-openapi.json",
    },
    {
        "name": "blockchain-node",
        "module": "apps.blockchain_node.src.aitbc_chain.app:app",
        "output": "blockchain-node-openapi.json",
    },
    {
        "name": "marketplace",
        "module": "apps.marketplace.src.marketplace_service.main:app",
        "output": "marketplace-openapi.json",
    },
    {
        "name": "wallet",
        "module": "apps.wallet.src.app.main:app",
        "output": "wallet-openapi.json",
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
        return spec
    except Exception as e:
        print(f"Error extracting spec from {app_config['name']}: {e}")
        return None


def main():
    """Extract OpenAPI specs from all configured applications."""
    print("Extracting OpenAPI specs...")

    for app_config in APPS:
        print(f"  Extracting {app_config['name']}...")
        spec = extract_openapi_spec(app_config)

        if spec:
            output_path = API_DOCS_DIR / app_config["output"]
            with open(output_path, "w") as f:
                json.dump(spec, f, indent=2)
            print(f"    ✓ Saved to {output_path}")
        else:
            print(f"    ✗ Failed to extract {app_config['name']}")

    print(f"\nOpenAPI specs saved to {API_DOCS_DIR}")


if __name__ == "__main__":
    main()
