"""
CORS configuration security tests.
Validates that wildcard CORS is not used with allow_credentials=True.
"""

import os
import sys
from pathlib import Path

import pytest


def test_agent_coordinator_cors_rejects_wildcard():
    """Test that agent-coordinator config rejects wildcard origins"""
    # Clear cached app modules to avoid import conflicts from other tests
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("app"):
            del sys.modules[mod_name]

    # Set required secret_key to avoid validation error (must be >= 32 chars)
    os.environ["SECRET_KEY"] = "test_secret_key_for_testing_extra_long"

    try:
        from app.config import validated_cors_origins
    except ImportError:
        pytest.skip("app.config import conflict in full suite")

    with pytest.raises(ValueError, match="Wildcard CORS origins are not allowed"):
        validated_cors_origins(["*"])

    # Clean up
    os.environ.pop("SECRET_KEY", None)


def test_agent_coordinator_cors_accepts_localhost():
    """Test that agent-coordinator config accepts localhost origins"""
    # Clear cached app modules to avoid import conflicts from other tests
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("app"):
            del sys.modules[mod_name]

    # Set required secret_key to avoid validation error (must be >= 32 chars)
    os.environ["SECRET_KEY"] = "test_secret_key_for_testing_extra_long"

    try:
        from app.config import validated_cors_origins
    except ImportError:
        pytest.skip("app.config import conflict in full suite")

    origins = [
        "http://localhost:8001",
        "http://localhost:9001",
        "http://127.0.0.1:8001",
    ]
    result = validated_cors_origins(origins)
    assert result == origins

    # Clean up
    os.environ.pop("SECRET_KEY", None)


def test_marketplace_cors_rejects_wildcard():
    """Test that marketplace rejects wildcard origins via environment variable"""
    repo_root = Path(__file__).resolve().parents[2]
    marketplace_src = repo_root / "apps" / "marketplace"
    agent_marketplace_file = marketplace_src / "agent_marketplace.py"

    if not agent_marketplace_file.exists():
        pytest.skip("agent_marketplace.py not found")

    # Set environment variable with wildcard
    os.environ["AITBC_MARKETPLACE_CORS_ORIGINS"] = "*"

    # The marketplace module raises ValueError on import when wildcard is set
    # This is the expected behavior
    with pytest.raises(ValueError, match="Wildcard CORS origins are not allowed"):
        import importlib.util

        spec = importlib.util.spec_from_file_location("agent_marketplace", agent_marketplace_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    # Clean up
    os.environ.pop("AITBC_MARKETPLACE_CORS_ORIGINS", None)


def test_marketplace_cors_accepts_localhost():
    """Test that marketplace accepts localhost origins via environment variable"""
    repo_root = Path(__file__).resolve().parents[2]
    marketplace_src = repo_root / "apps" / "marketplace"
    agent_marketplace_file = marketplace_src / "agent_marketplace.py"

    if not agent_marketplace_file.exists():
        pytest.skip("agent_marketplace.py not found")

    os.environ["AITBC_MARKETPLACE_CORS_ORIGINS"] = "http://localhost:8001,http://localhost:9001"

    # Import the function directly from the file
    import importlib.util

    spec = importlib.util.spec_from_file_location("agent_marketplace", agent_marketplace_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.get_cors_origins()
    assert "http://localhost:8001" in result
    assert "http://localhost:9001" in result

    # Clean up
    os.environ.pop("AITBC_MARKETPLACE_CORS_ORIGINS", None)


def test_no_wildcard_cors_in_coordinator_api_apps():
    """Scan coordinator-api apps for wildcard CORS with credentials"""
    import re

    repo_root = Path(__file__).resolve().parents[2]
    coordinator_src = repo_root / "apps" / "coordinator-api" / "src"

    files_to_check = [
        coordinator_src / "app" / "contexts" / "agent_coordination" / "routers" / "agent_performance.py",
        coordinator_src / "app" / "routers" / "marketplace_enhanced_app.py",
    ]

    wildcard_pattern = re.compile(r'allow_origins\s*=\s*\["\*"\]')
    credentials_pattern = re.compile(r"allow_credentials\s*=\s*True")

    for file_path in files_to_check:
        if not file_path.exists():
            continue

        content = file_path.read_text()
        has_wildcard = wildcard_pattern.search(content) is not None
        has_credentials = credentials_pattern.search(content) is not None

        # If both wildcard and credentials are present, fail the test
        if has_wildcard and has_credentials:
            pytest.fail(f"File {file_path} contains wildcard CORS with credentials enabled")
