"""Recursive redaction of credential fields in structured CLI output (#2355).

``aitbc ai jobs``/``status``/``results`` print coordinator job records
verbatim, and paid ``transcribe`` submissions carry a per-job shop-gate
credential pair — ``payload.access_key`` / ``payload.access_secret`` — that
must never land in logs or scrollback. :func:`redact_secrets` walks the
payload before it reaches a renderer and masks the *values* of secret-named
keys; key names stay visible so the output still shows which fields existed.

The name matcher is deliberately narrower than the env/field deny list in
``commands/system.py``: it is tuned for response payloads, where
``payment_token`` is a currency symbol ("AITBC") and ``access_key`` is the
public half of a key/secret pair — both must stay readable. It is also
self-contained: ``utils`` cannot import ``commands.system`` without a
circular import.
"""

from __future__ import annotations

import re
from typing import Any

# Same marker ``config export``/``config show`` use for api_key.
REDACTED = "***REDACTED***"

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _field_tokens(name: str) -> list[str]:
    """The name split on '_', '-' and lower->UPPER camel boundaries, lowercased."""
    return [t.lower() for t in re.split(r"[_-]+", _CAMEL_BOUNDARY.sub("_", name)) if t]


# Public halves of key/secret pairs and currency-symbol fields that must stay
# visible even though their names look secret-adjacent. Compared on the
# separator-insensitive form so "access-key"/"accessKey" match too.
# ``access_key`` is the public identifier the shop gate pairs with
# ``access_secret`` (MCP-SECRETS-1 keeps it for the same reason);
# ``payment_token`` is the payment currency, not a bearer token.
_KEEP_NORMALIZED = frozenset({"accesskey", "publickey", "pubkey", "paymenttoken"})

# A name ending in one of these takes a path or is a flag
# (``private_key_file``, ``--password-stdin``): the value is not the secret.
_KEEP_LAST_TOKENS = frozenset({"file", "path", "dir", "stdin"})

# Token-level deny list: a name is denied when any token — the name split on
# '_', '-' and camelCase boundaries — is one of these. Token equality, not
# substring: "monkey"/"keystore"/"tokens_used" stay visible, "decode_seed"
# is caught by "seed".
_DENY_TOKENS = frozenset(
    {
        "pass",
        "password",
        "passwd",
        "pwd",
        "passphrase",
        "secret",
        "secrets",
        "passwords",
        "private",
        "privkey",
        "mnemonic",
        "seed",
        "seedphrase",
        "credential",
        "credentials",
        "bearer",
        "cookie",
        "cookies",
        "pw",
        "salt",
    }
)

# Separator-insensitive exact matches for spellings the token split misses
# ("privatekey", "api-key", "csrfToken" normalizes to "csrftoken").
_DENY_NORMALIZED = frozenset(
    {
        "key",
        "keys",
        "token",
        "secret",
        "password",
        "passwd",
        "passphrase",
        "pwd",
        "privatekey",
        "secretkey",
        "apikey",
        "credential",
        "credentials",
        "mnemonic",
        "seed",
        "seedphrase",
        "accesstoken",
        "authtoken",
        "apitoken",
        "sessiontoken",
        "refreshtoken",
        "bearertoken",
        "idtoken",
        "csrftoken",
        "xsrftoken",
    }
)

# A name ending in "key" is denied when its prefix is one of these —
# "private_key"/"api_key"/"wallet_key"/"encryption_key" — while
# "idempotency_key"/"monkey" stay visible. "access" is deliberately absent:
# ``access_key`` is the public half of the pair and stays readable via
# _KEEP_NORMALIZED anyway.
_KEY_PREFIXES = ("private", "secret", "api", "auth", "signing", "wallet", "session", "encryption", "ssh")

# A separator-less name still ends in a deny word: "pgpassword". Single-token
# names only, so two-token fields like "tokens_used" cannot trip it.
_DENY_SUFFIXES = (
    "password",
    "passwd",
    "passphrase",
    "pwd",
    "secret",
    "secrets",
    "passwords",
    "private",
    "credential",
    "credentials",
    "mnemonic",
    "seed",
    "seedphrase",
    "privkey",
    "bearer",
    "authorization",
)


def secret_field_name(name: Any) -> bool:
    """True when a dict key names a credential whose value must be masked."""
    if not isinstance(name, str):
        return False
    lowered = name.lower()
    normalized = lowered.replace("-", "").replace("_", "")
    if normalized in _KEEP_NORMALIZED:
        return False
    tokens = _field_tokens(name)
    if not tokens:
        return False
    if tokens[-1] in _KEEP_LAST_TOKENS:
        return False
    if normalized in _DENY_NORMALIZED:
        return True
    if any(token in _DENY_TOKENS for token in tokens):
        return True
    # ``session_token``/``accessToken``/``csrf_token`` are credentials;
    # ``payment_token`` already returned via _KEEP_NORMALIZED.
    if tokens[-1] == "token":
        return True
    if normalized.endswith("key") and normalized[:-3] in _KEY_PREFIXES:
        return True
    if len(tokens) == 1 and normalized.endswith(_DENY_SUFFIXES):
        return True
    return False


def redact_secrets(value: Any) -> Any:
    """Return ``value`` with secret-named dict values replaced by REDACTED.

    Recurses through dicts and lists/tuples; scalars and key names pass
    through unchanged. Empty/None values stay as-is so optional fields do not
    gain a phantom marker.
    """
    if isinstance(value, dict):
        return {
            key: (REDACTED if secret_field_name(key) and item not in (None, "") else redact_secrets(item))
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_secrets(item) for item in value]
    return value
