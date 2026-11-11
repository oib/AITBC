"""
AITBC Environment Variable Helpers
Centralized utilities for loading and managing environment variables
"""

import os

from ..exceptions import ConfigurationError


def _current_environment() -> str:
    """Return the current environment name from common env vars."""
    return os.getenv("ENVIRONMENT", os.getenv("APP_ENV", os.getenv("NODE_ENV", "development")))


def is_production() -> bool:
    """Check if the current environment is production."""
    return _current_environment().lower() in ("production", "prod")


def get_env_var(key: str, default: str = "") -> str:
    """
    Get an environment variable with a default value.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Environment variable value or default
    """
    return os.getenv(key, default)


def get_required_env_var(key: str) -> str:
    """
    Get a required environment variable, raise error if not set.

    Args:
        key: Environment variable name

    Returns:
        Environment variable value

    Raises:
        ConfigurationError: If environment variable is not set
    """
    value = os.getenv(key)
    if value is None:
        raise ConfigurationError(f"Required environment variable '{key}' is not set")
    return value


def get_bool_env_var(key: str, default: bool = False) -> bool:
    """
    Get a boolean environment variable.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        True if variable is set to 'true', '1', 'yes', or 'on' (case-insensitive)
        False if variable is set to 'false', '0', 'no', or 'off' (case-insensitive)
        Default value if not set
    """
    value = os.getenv(key, "").lower()
    if not value:
        return default
    return value in ("true", "1", "yes", "on")


def get_int_env_var(key: str, default: int = 0) -> int:
    """
    Get an integer environment variable.

    Args:
        key: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Integer value or default
    """
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def get_float_env_var(key: str, default: float = 0.0) -> float:
    """
    Get a float environment variable.

    Args:
        key: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Float value or default
    """
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def get_list_env_var(key: str, separator: str = ",", default: list | None = None) -> list:
    """
    Get a list environment variable.

    Args:
        key: Environment variable name
        separator: Separator for list items
        default: Default value if not set

    Returns:
        List of values or default
    """
    if default is None:
        default = []
    value = os.getenv(key, "")
    if not value:
        return default
    return [item.strip() for item in value.split(separator) if item.strip()]


# Variables a utility subprocess (ffmpeg, nvidia-smi, journalctl, systemctl,
# systemd-creds, node, circom, ipfs, ...) legitimately needs: PATH lookup,
# locale, temp dirs and shared-library/fontconfig hints. Everything else —
# service secrets like PROPOSER_KEY, VALIDATOR_KEYS, JWT_SECRET — stays out of
# the child's environment (Refs #1760).
_SUBPROCESS_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LANGUAGE",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LD_LIBRARY_PATH",
    "FONTCONFIG_PATH",
    "FONTCONFIG_FILE",
)


def subprocess_env(
    *,
    include: tuple[str, ...] | list[str] = (),
    include_prefixes: tuple[str, ...] | list[str] = (),
) -> dict[str, str]:
    """Minimal environment for a utility subprocess.

    Returns only the allowlisted variables present in ``os.environ``, plus any
    ``include`` names and variables matching ``include_prefixes``. Callers that
    genuinely need service configuration pass it explicitly — e.g. the miner's
    ``aitbc market offer`` child gets ``include_prefixes=("AITBC_", "SHOP_",
    "MINER_")``. Do NOT use this for a child that *is* the workload (the
    hermes agent runtime needs its provider keys).
    """
    env = {k: os.environ[k] for k in _SUBPROCESS_ENV_ALLOWLIST if k in os.environ}
    for key in include:
        if key in os.environ:
            env[key] = os.environ[key]
    for prefix in include_prefixes:
        env.update({k: v for k, v in os.environ.items() if k.startswith(prefix)})
    return env
