#!/usr/bin/env python3
"""Generate cli/README.md and cli/CLI_USAGE_GUIDE.md from the live CLI tree."""

import os
import sys
from pathlib import Path

os.environ["AITBC_SKIP_ENV_FILES"] = "1"

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "cli") not in sys.path:
    sys.path.insert(0, str(REPO / "cli"))

from aitbc_cli.core.main import cli


def command_help(cmd):
    return (cmd.help or "").split("\n")[0].strip()


def subcommand_summary(cmd):
    if not hasattr(cmd, "commands"):
        return ""
    names = sorted(cmd.commands.keys())
    return ", ".join(f"`{n}`" for n in names)


def build_readme():
    lines = [
        "# AITBC CLI",
        "",
        "Command-line interface for the AITBC network.",
        "",
        "## Installation",
        "",
        "```bash",
        "pip install ./cli",
        "aitbc --help",
        "```",
        "",
        "## Group catalog",
        "",
        "| Group | Description | Key subcommands |",
        "|-------|-------------|-----------------|",
    ]
    for name in sorted(cli.commands):
        cmd = cli.commands[name]
        lines.append(f"| `{name}` | {command_help(cmd)} | {subcommand_summary(cmd)} |")
    lines.append("")
    return "\n".join(lines)


def build_usage_guide():
    sections = [
        "# AITBC CLI Usage Guide",
        "",
        "This guide is generated from the live `aitbc` command tree. Each entry below lists a top-level group and its key subcommands.",
        "",
    ]
    for name in sorted(cli.commands):
        cmd = cli.commands[name]
        help_text = command_help(cmd)
        if hasattr(cmd, "commands"):
            subs = ", ".join(f"`{n}`" for n in sorted(cmd.commands))
            sections.append(f"- `{name}` — {help_text}. Subcommands: {subs}")
        else:
            sections.append(f"- `{name}` — {help_text}")
    sections.append("")
    return "\n".join(sections)


def main():
    (REPO / "cli" / "README.md").write_text(build_readme())
    (REPO / "cli" / "CLI_USAGE_GUIDE.md").write_text(build_usage_guide())
    print("Generated:")
    print(f"  {REPO / 'cli' / 'README.md'}")
    print(f"  {REPO / 'cli' / 'CLI_USAGE_GUIDE.md'}")


if __name__ == "__main__":
    main()
