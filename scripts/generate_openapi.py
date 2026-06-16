#!/usr/bin/env python3
"""
Generate OpenAPI specifications for all AITBC services.
Run with: TEST_ADMIN_PASSWORD=*** python scripts/generate_openapi.py
"""

import json
import os
import sys
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path("/opt/aitbc")
sys.path.insert(0, str(REPO_ROOT))

# Set required environment variables
os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-chars-long")
os.environ.setdefault("TEST_ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
os.environ.setdefault("WALLET_BIND_PORT", "8108")
os.environ.setdefault("WALLET_DIR", "/tmp/test_wallet")
os.environ.setdefault("KEYSTORE_PASSWORD", "test-password")
os.environ.setdefault("WALLET_IMPORT_PASSWORD", "test-import-password")
os.environ.setdefault("MARKETPLACE_BIND_PORT", "8102")
os.environ.setdefault("BLOCKCHAIN_RPC_URL", "http://localhost:8202")

OUTPUT_DIR = REPO_ROOT / "docs" / "openapi"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_openapi(app_module, app_name, output_file):
    """Generate OpenAPI spec for a FastAPI app."""
    print(f"\nGenerating {app_name} OpenAPI spec...")
    
    try:
        from importlib import import_module
        module = import_module(app_module)
        app = getattr(module, 'app')
        
        # Get OpenAPI spec
        openapi_spec = app.openapi()
        
        # Add service info
        openapi_spec.setdefault("info", {})
        openapi_spec["info"]["title"] = f"AITBC {app_name.title()} Service"
        openapi_spec["info"]["version"] = "0.1.0"
        openapi_spec["info"]["description"] = f"API specification for AITBC {app_name} service"
        
        # Add servers info
        openapi_spec["servers"] = [
            {"url": "http://localhost:8203", "description": "Coordinator API (production)"},
            {"url": "http://localhost:8102", "description": "Marketplace (production)"},
            {"url": "http://localhost:8108", "description": "Wallet (production)"},
            {"url": "http://localhost:8103", "description": "Hermes (production)"},
        ]
        
        # Add common components
        if "components" not in openapi_spec:
            openapi_spec["components"] = {}
        if "securitySchemes" not in openapi_spec["components"]:
            openapi_spec["components"]["securitySchemes"] = {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                },
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key"
                }
            }
        
        # Write to file
        output_path = OUTPUT_DIR / output_file
        with open(output_path, "w") as f:
            json.dump(openapi_spec, f, indent=2)
        
        print(f"  ✓ Generated {output_path} ({len(openapi_spec.get('paths', {}))} paths)")
        return True
        
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("AITBC OpenAPI Specification Generator")
    print("=" * 60)
    
    services = [
        ("app.main", "coordinator-api", "coordinator-api.json"),
        ("marketplace_service.main", "marketplace", "marketplace.json"),
        ("app.main", "wallet", "wallet.json"),
        ("hermes_service.main", "hermes", "hermes.json"),
    ]
    
    # Set paths for each service
    sys.path.insert(0, "/opt/aitbc/apps/coordinator-api/src")
    sys.path.insert(0, "/opt/aitbc/apps/marketplace/src")
    sys.path.insert(0, "/opt/aitbc/apps/wallet/src")
    sys.path.insert(0, "/opt/aitbc/apps/hermes/src")

    # Set required environment variables
    os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
    os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
    os.environ.setdefault("MARKETPLACE_DATABASE_URL", "sqlite+aiosqlite:///test.db")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-chars-long")
    os.environ.setdefault("TEST_ADMIN_PASSWORD", "test-admin-password")
    os.environ.setdefault("COORDINATOR_API_KEY", "test-key")
    os.environ.setdefault("WALLET_BIND_PORT", "8108")
    os.environ.setdefault("WALLET_DIR", "/tmp/test_wallet")
    os.environ.setdefault("KEYSTORE_PASSWORD", "test-password")
    os.environ.setdefault("WALLET_IMPORT_PASSWORD", "test-import-password")
    os.environ.setdefault("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
    os.environ.setdefault("MARKETPLACE_BIND_PORT", "8102")
    os.environ.setdefault("MARKETPLACE_DATABASE_URL", "sqlite+aiosqlite:///test.db")

    results = []
    for app_module, app_name, output_file in services:
        result = generate_openapi(app_module, app_name, output_file)
        results.append((app_name, result))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    
    if all(r[1] for r in results):
        print(f"\nAll specs generated in: {OUTPUT_DIR}")
        return 0
    else:
        print("\nSome specs failed to generate")
        return 1


if __name__ == "__main__":
    sys.exit(main())