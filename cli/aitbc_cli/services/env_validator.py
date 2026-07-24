"""Environment key and secret-pattern validation for the AITBC CLI (v0.16.1 §B1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


DEFAULT_REQUIRED_KEYS = [
    "AITBC_API_KEY",
    "COORDINATOR_API_URL",
]

DEFAULT_OPTIONAL_KEYS = [
    "OPENAI_API_KEY",
    "GOOGLE_TRANSLATE_API_KEY",
    "DEEPL_API_KEY",
    "EXCHANGE_API_KEY",
]

# ponytail: basic entropy checks; production should use a secret scanner.
_SECRET_PATTERNS = [
    re.compile(r"[A-Za-z0-9]{32,}"),  # long alphanumeric token
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI-style key prefix
    re.compile(r"[a-f0-9]{64}", re.IGNORECASE),  # hex secret
]


@dataclass
class EnvValidationResult:
    """Result of validating an environment map."""

    valid: bool = True
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    present: dict[str, Any] = field(default_factory=dict)


def _looks_like_secret(key: str, value: str) -> bool:
    """Return True if the value for ``key`` looks like a secret token."""
    secret_hints = ["key", "token", "secret", "password", "api_key"]
    if not any(hint in key.lower() for hint in secret_hints):
        return False
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            return True
    return False


def validate_env(
    env: dict[str, str] | None = None,
    *,
    required_keys: list[str] | None = None,
    optional_keys: list[str] | None = None,
    allow_missing: bool = False,
) -> EnvValidationResult:
    """Validate that required keys are present and that secrets look non-trivial."""
    env = env or {}
    required = required_keys or DEFAULT_REQUIRED_KEYS
    optional = optional_keys or DEFAULT_OPTIONAL_KEYS

    result = EnvValidationResult()
    for key in required:
        value = env.get(key)
        if not value:
            result.missing.append(key)
            result.valid = False
        else:
            result.present[key] = "***REDACTED***" if _looks_like_secret(key, value) else value

    for key in optional:
        value = env.get(key)
        if value and _looks_like_secret(key, value) and len(value) < 16:
            result.warnings.append(f"{key} looks short for a secret")
        if value:
            result.present[key] = "***REDACTED***" if _looks_like_secret(key, value) else value

    if not allow_missing and result.missing:
        result.warnings.append(f"Missing required keys: {', '.join(result.missing)}")

    return result


def check_for_hardcoded_secrets(text: str) -> list[str]:
    """Return a list of suspected hardcoded secret lines."""
    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if any(pattern.search(line) for pattern in _SECRET_PATTERNS):
            if any(hint in line.lower() for hint in ["key", "token", "secret", "api_key"]):
                findings.append(f"line {line_no}: potential secret")
    return findings
