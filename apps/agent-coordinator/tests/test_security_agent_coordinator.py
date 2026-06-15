"""Security configuration tests for agent coordinator."""

import os
import sys
from pathlib import Path

import pytest

app_root = Path(__file__).resolve().parents[1]
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from src.app.config import settings, validated_cors_origins  # noqa: E402


def test_default_cors_origins_do_not_allow_wildcard():
    assert "*" not in settings.cors_origins


def test_wildcard_cors_origin_rejected():
    with pytest.raises(ValueError):
        validated_cors_origins(["*"])
