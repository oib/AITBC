"""Security configuration tests for agent coordinator."""

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from src.app.config import settings, validated_cors_origins


def test_default_cors_origins_do_not_allow_wildcard():
    assert "*" not in settings.cors_origins


def test_wildcard_cors_origin_rejected():
    with pytest.raises(ValueError):
        validated_cors_origins(["*"])
