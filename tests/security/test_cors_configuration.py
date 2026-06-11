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
    repo_root = Path(__file__).resolve().parents[2]
    agent_coordinator_src = repo_root / "apps" / "agent-coordinator" / "src"

    if str(agent_coordinator_src) not in sys.path:
        sys.path.insert(0, str(agent_coordinator_src))

    # Set required secret_key to avoid validation error
    os.environ["SECRET_KEY"] = "test_secret_key_for_testing"

    from app.config import validated_cors_origins

    with pytest.raises(ValueError, match="Wildcard CORS origins are not allowed"):
        validated_cors_origins(["*"])

    # Clean up
    os.environ.pop("SECRET_KEY", None)


def test_agent_coordinator_cors_accepts_localhost():
    """Test that agent-coordinator config accepts localhost origins"""
    repo_root = Path(__file__).resolve().parents[2]
    agent_coordinator_src = repo_root / "apps" / "agent-coordinator" / "src"

    if str(agent_coordinator_src) not in sys.path:
        sys.path.insert(0, str(agent_coordinator_src))

    # Set required secret_key to avoid validation error
    os.environ["SECRET_KEY"] = "test_secret_key_for_testing"

    from app.config import validated_cors_origins

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

    if str(marketplace_src) not in sys.path:
        sys.path.insert(0, str(marketplace_src))

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

    if str(marketplace_src) not in sys.path:
        sys.path.insert(0, str(marketplace_src))

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
        coordinator_src / "app" / "contexts" / "hermes" / "routers" / "hermes_enhanced_app.py",
        coordinator_src / "app" / "services" / "enterprise_integration" / "api_gateway.py",
        coordinator_src / "app" / "services" / "modality_optimization_app.py",
        coordinator_src / "app" / "services" / "multimodal_app.py",
        coordinator_src / "app" / "services" / "gpu_multimodal_app.py",
        coordinator_src / "app" / "routers" / "marketplace_enhanced_app.py",
        coordinator_src / "app" / "services" / "advanced_ai_service.py",
        coordinator_src / "app" / "services" / "adaptive_learning_app.py",
    ]

    wildcard_pattern = re.compile(r'allow_origins\s*=\s*\["\*"\]')
    credentials_pattern = re.compile(r'allow_credentials\s*=\s*True')

    for file_path in files_to_check:
        if not file_path.exists():
            continue

        content = file_path.read_text()
        has_wildcard = wildcard_pattern.search(content) is not None
        has_credentials = credentials_pattern.search(content) is not None

        # If both wildcard and credentials are present, fail the test
        if has_wildcard and has_credentials:
            pytest.fail(f"File {file_path} contains wildcard CORS with credentials enabled")
