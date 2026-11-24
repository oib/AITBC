"""Pin for #2899: the secrets classifier must catch mnemonic/seed/recovery
names and password-URLs that carry no username.

Before the fix, ``WALLET_MNEMONIC=word1 word2 ...`` and
``DATABASE_URL=scheme://:password@host`` were written into the generated
.env template in plaintext.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "security" / "migrate_secrets_to_env_files.py"

_spec = importlib.util.spec_from_file_location("migrate_secrets_to_env_files", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["migrate_secrets_to_env_files"] = mod
_spec.loader.exec_module(mod)


def test_mnemonic_seed_recovery_names_are_sensitive():
    for name in (
        "WALLET_MNEMONIC",
        "MNEMONIC_PHRASE",
        "SEED_PHRASE",
        "WALLET_SEED",
        "RECOVERY_KEY",
        "RECOVERY_PHRASE",
    ):
        assert mod._is_sensitive(name, "not-a-url"), name


def test_password_url_without_username_is_sensitive():
    assert mod._is_sensitive("DATABASE_URL", "postgres://:s3cret@db.internal:5432/app")
    assert mod._is_sensitive("REDIS_URL", "redis://:hunter2@cache:6379/0")


def test_plain_urls_and_names_still_pass():
    assert not mod._is_sensitive("DATABASE_URL", "postgres://db.internal:5432/app")
    assert not mod._is_sensitive("LOG_LEVEL", "debug")
    assert not mod._is_sensitive("API_URL", "https://api.example.com/v1")
