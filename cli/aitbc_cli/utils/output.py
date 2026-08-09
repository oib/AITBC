"""CLI output and formatting helpers.

This module is intentionally dependency-light so that submodules (e.g.
``wallet_daemon_client``) can import ``error`` / ``success`` / ``warning``
without forcing the whole ``aitbc_cli.utils`` package to finish loading.
"""

import base64
import logging

from click import echo, secho


def output(message, format=None, title=None, **kwargs):
    """Print a regular output message (handles strings and structured data)"""
    if not isinstance(message, str):
        import json

        if format == "json" or format == "yaml":
            message = json.dumps(message, indent=2)
        else:
            # Table format — just JSON for now
            message = json.dumps(message, indent=2)
    if title:
        echo(f"\n{title}")
        echo("=" * len(title))
    echo(message, **kwargs)


def error(message: str, **kwargs):
    """Print an error message in red"""
    secho(message, fg="red", **kwargs)


def success(message: str, **kwargs):
    """Print a success message in green"""
    secho(message, fg="green", **kwargs)


def info(message: str, **kwargs):
    """Print an info message in blue"""
    secho(message, fg="blue", **kwargs)


def warning(message: str, **kwargs):
    """Print a warning message in yellow"""
    secho(message, fg="yellow", **kwargs)


def encode_value(value: str, key: str | None = None) -> str:
    """Lightweight reversible encoding used for CLI compatibility."""
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_value(encoded: str, key: str | None = None) -> str:
    """Reverse the lightweight compatibility encoding."""
    return base64.b64decode(encoded.encode("ascii")).decode("utf-8")


def setup_logging(verbosity: int, debug: bool = False) -> str:
    """Configure basic CLI logging for compatibility with the generated entrypoint."""
    if debug or verbosity >= 2:
        level = logging.DEBUG
        level_name = "DEBUG"
    elif verbosity == 1:
        level = logging.INFO
        level_name = "INFO"
    else:
        level = logging.WARNING
        level_name = "WARNING"

    logging.basicConfig(level=level, format="%(message)s")
    return level_name
