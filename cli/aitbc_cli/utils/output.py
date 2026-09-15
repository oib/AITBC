"""CLI output and formatting helpers.

This module is intentionally dependency-light so that submodules (e.g.
``wallet_daemon_client``) can import ``error`` / ``success`` / ``warning``
without forcing the whole ``aitbc_cli.utils`` package to finish loading.
"""

import base64
import logging
from functools import update_wrapper
from typing import Any, cast

import click
from click import echo, secho


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _tabular_rows(message: Any) -> list[dict[str, Any]] | None:
    """Return ``message`` as a list of flat records, or None if it is not tabular.

    A table needs rows of scalars. Anything else -- a nested structure, a bare
    scalar, a ragged mix -- is rendered as JSON instead, which is the honest
    answer for data that has no columns.
    """
    if isinstance(message, dict):
        if all(_is_scalar(v) for v in message.values()):
            # A flat mapping is one record shown as Field/Value rather than as a
            # single very wide row.
            return [{"Field": k, "Value": v} for k, v in message.items()]
        return None
    if isinstance(message, list) and message:
        if all(isinstance(row, dict) and all(_is_scalar(v) for v in row.values()) for row in message):
            return cast(list[dict[str, Any]], message)
        if all(_is_scalar(row) for row in message):
            return [{"Value": row} for row in message]
    return None


def _render_csv(rows: list[dict[str, Any]], headers: list[str]) -> str:
    """Render flat records as CSV."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({h: row.get(h, "") for h in headers})
    return buf.getvalue().rstrip("\n")


def _render(message: Any, format: str) -> str:
    """Serialize structured data in the requested format.

    Until 2026-09-15 this function had a single branch for every format: the
    else-arm was commented "Table format -- just JSON for now". So `table`,
    `yaml` and `csv` were accepted by OUTPUT_FORMAT_OPTION on roughly every
    command in the CLI and all three silently produced JSON.
    """
    import json

    if format == "json":
        return json.dumps(message, indent=2, default=str)

    if format == "yaml":
        try:
            import yaml

            return cast(str, yaml.safe_dump(message, sort_keys=False, default_flow_style=False)).rstrip("\n")
        except ImportError:
            return json.dumps(message, indent=2, default=str)

    rows = _tabular_rows(message)
    if rows is None:
        # Not tabular: JSON is the only faithful rendering.
        return json.dumps(message, indent=2, default=str)

    # Union of keys in order of first appearance, so a row missing a field still
    # lines up under the right column instead of shifting the rest.
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)

    if format == "csv":
        return _render_csv(rows, headers)

    try:
        from tabulate import tabulate
    except ImportError:
        return json.dumps(message, indent=2, default=str)

    body = [[row.get(h, "") for h in headers] for row in rows]
    return tabulate(body, headers=headers, tablefmt="grid")


def output(message, format=None, title=None, **kwargs):
    """Print a regular output message (handles strings and structured data)"""
    if not isinstance(message, str):
        message = _render(message, format or "table")
    # JSON/YAML/CSV output is meant to be machine-readable; do not wrap it in a title.
    if title and format not in ("json", "yaml", "csv"):
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


def resolve_output_format(ctx, command_format: str | None = None) -> str:
    """Return the effective output format for a command.

    Command-level ``--format`` wins, then the global ``--output`` option stored
    in ``ctx.obj["output_format"]``, then the default ``table``.
    """
    if command_format:
        return command_format
    if ctx and ctx.obj:
        return cast(str, ctx.obj.get("output_format", "table"))
    return "table"


def OUTPUT_FORMAT_OPTION(command: Any | None = None, *, default: str | None = None) -> Any:
    """Decorator that adds ``--format`` / ``--output`` aliases to a command.

    Works as ``@OUTPUT_FORMAT_OPTION`` or as a click option factory.
    """

    def decorator(f):
        f = click.option(
            "--format",
            "output_format",
            default=default,
            type=click.Choice(["table", "json", "yaml", "csv"]),
            help="Output format",
        )(f)
        f = click.option(
            "--output",
            "output_format",
            default=default,
            type=click.Choice(["table", "json", "yaml", "csv"]),
            help="Output format (alias for --format)",
        )(f)
        return f

    if command is None:
        return decorator
    return update_wrapper(decorator(command), command)
