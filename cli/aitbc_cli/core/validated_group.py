"""Click Group subclass that hides deprecated, unvalidated commands.

G8: the CLI shipped ~68 top-level groups, most of which were not exercised by the
live-validated economic loop. This group only exposes the validated surface by
default and routes the rest to a deprecation error unless the user passes
`--show-deprecated`.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import click

from ..utils.http_client import get_logger

logger = get_logger(__name__)


class DeprecatedCommand(click.Command):
    """A stand-in that refuses to run an unvalidated command."""

    def __init__(self, name: str, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.hidden = True
        self.no_args_is_help = False

    def get_help(self, ctx: click.Context) -> str:
        return f"The '{self.name}' command is deprecated and not live-validated."

    def invoke(self, ctx: click.Context) -> Any:
        click.echo(
            f"Error: '{self.name}' is deprecated and not live-validated.",
            err=True,
        )
        click.echo(
            f"Use `aitbc --show-deprecated {self.name} ...` to invoke it at your own risk.",
            err=True,
        )
        raise click.Abort()


class ValidatedGroup(click.Group):
    """A click Group that hides unvalidated commands by default."""

    def __init__(self, *args: Any, validated_commands: set[str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.validated_commands = set(validated_commands or set())

    def _show_deprecated(self, ctx: click.Context | None = None) -> bool:
        from_env = os.environ.get("AITBC_CLI_SHOW_DEPRECATED", "") in ("1", "true", "yes")
        from_argv = "--show-deprecated" in sys.argv
        from_ctx = bool(ctx and ctx.params.get("show_deprecated"))
        return from_env or from_argv or from_ctx

    def list_commands(self, ctx: click.Context) -> list[str]:
        all_commands = list(super().list_commands(ctx))
        if not self.validated_commands or self._show_deprecated(ctx):
            return all_commands
        return [name for name in all_commands if name in self.validated_commands]

    def get_command(self, ctx: click.Context, name: str) -> click.Command | None:
        cmd = super().get_command(ctx, name)
        if cmd is None:
            return None
        if self.validated_commands and name not in self.validated_commands and not self._show_deprecated(ctx):
            return DeprecatedCommand(name)
        return cmd

    def get_help(self, ctx: click.Context) -> str:
        if not self._show_deprecated(ctx) and self.validated_commands:
            help_text = super().get_help(ctx)
            lines = help_text.splitlines()
            lines.append("")
            lines.append("Unvalidated commands are hidden. Use --show-deprecated to see them.")
            return "\n".join(lines)
        return super().get_help(ctx)
