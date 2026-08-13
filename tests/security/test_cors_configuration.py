"""
CORS configuration security tests.
Validates that wildcard CORS is not used with allow_credentials=True.
"""

import os
import sys
from pathlib import Path

import pytest

_AGENT_SRC = str(Path(__file__).resolve().parents[2] / "apps" / "agent-coordinator" / "src")
if _AGENT_SRC not in sys.path:
    sys.path.insert(0, _AGENT_SRC)


def test_agent_coordinator_cors_rejects_wildcard():
    """Test that agent-coordinator config rejects wildcard origins"""
    # Clear cached app modules to avoid import conflicts from other tests
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("app"):
            del sys.modules[mod_name]

    # Set required secret_key to avoid validation error (must be >= 32 chars)
    os.environ["SECRET_KEY"] = "test_secret_key_for_testing_extra_long"

    from agent_app.config import validated_cors_origins

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

    from agent_app.config import validated_cors_origins

    origins = [
        "http://localhost:8001",
        "http://localhost:9001",
        "http://127.0.0.1:8001",
    ]
    result = validated_cors_origins(origins)
    assert result == origins

    # Clean up
    os.environ.pop("SECRET_KEY", None)

    assert "http://localhost:9001" in result

    # Clean up
    os.environ.pop("AITBC_MARKETPLACE_CORS_ORIGINS", None)


def test_no_wildcard_cors_in_coordinator_api_apps():
    """Scan coordinator-api apps for wildcard CORS with credentials"""
    import re

    repo_root = Path(__file__).resolve().parents[2]
    coordinator_src = repo_root / "apps" / "coordinator-api" / "src"

    files_to_check = [
        coordinator_src / "coordinator_api" / "contexts" / "agent_coordination" / "routers" / "agent_performance.py",
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


def test_setup_cors_rejects_wildcard_with_credentials():
    """Test that setup_cors raises when wildcard origins are used with credentials"""
    from fastapi import FastAPI

    from aitbc.middleware.cors import setup_cors

    app = FastAPI()
    with pytest.raises(ValueError, match="Wildcard CORS origins cannot be used with credentials"):
        setup_cors(app, allow_origins=["*"], allow_credentials=True)


def test_setup_cors_allows_wildcard_without_credentials():
    """Test that setup_cors permits wildcard origins when credentials are disabled"""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from aitbc.middleware.cors import setup_cors

    app = FastAPI()
    setup_cors(app, allow_origins=["*"], allow_credentials=False)
    assert any(m.cls is CORSMiddleware for m in app.user_middleware)


def test_setup_cors_allows_specific_origins_with_credentials():
    """Test that setup_cors permits specific origins with credentials enabled"""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from aitbc.middleware.cors import setup_cors

    app = FastAPI()
    setup_cors(app, allow_origins=["http://localhost:3000"], allow_credentials=True)
    assert any(m.cls is CORSMiddleware for m in app.user_middleware)
