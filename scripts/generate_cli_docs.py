#!/usr/bin/env python3
"""Regenerate cli/README.md and cli/CLI_USAGE_GUIDE.md from the live CLI tree.

Preserves the curated group descriptions and ordering already in the docs; for
groups that are new or missing from the existing files, it falls back to the
Click help string (first line only).

Usage:
    python scripts/generate_cli_docs.py         # rewrite docs
    python scripts/generate_cli_docs.py --check # exit 1 if docs would change
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Match the sys.path dance in cli_gap_analysis.py so the repo-root aitbc package
# wins over any installed packages/py .pth entries.
os.environ.setdefault("AITBC_SKIP_ENV_FILES", "1")

REPO = Path(__file__).resolve().parents[1]
_repo = str(REPO)
if _repo in sys.path:
    sys.path.remove(_repo)
sys.path.insert(0, _repo)

import click  # noqa: E402

from cli_gap_analysis import cli  # noqa: E402


def _first_line(text: str) -> str:
    """Return the first non-empty line, stripped of trailing punctuation."""
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            return line.rstrip(".\n")
    return ""


def _parse_readme_table(path: Path) -> tuple[list[str], dict[str, str]]:
    """Return (group order, group -> description) from the README table."""
    order: list[str] = []
    descs: dict[str, str] = {}
    if not path.exists():
        return order, descs
    for line in path.read_text().splitlines():
        if not line.strip().startswith("|"):
            continue
        # group | description | subcommands
        m = re.match(r"^\|\s*`?([a-z0-9][a-z0-9_-]*)`?\s*\|\s*(.*?)\s*\|(.*)\|$", line)
        if not m:
            continue
        group = m.group(1)
        desc = m.group(2).strip()
        if not group or not desc:
            continue
        order.append(group)
        descs[group] = desc
    return order, descs


def _parse_usage_guide(path: Path) -> tuple[list[str], dict[str, str]]:
    """Return (group order, group -> description) from the Usage Guide list."""
    order: list[str] = []
    descs: dict[str, str] = {}
    if not path.exists():
        return order, descs
    for line in path.read_text().splitlines():
        m = re.match(r"\s*[-*]\s+`?([a-z0-9_-]+)`?\s*[-—]\s*(.*)", line)
        if not m:
            continue
        group = m.group(1)
        rest = m.group(2)
        # Split off the subcommands suffix but keep the description punctuation.
        if "Subcommands:" in rest:
            desc = rest.split("Subcommands:")[0].rstrip()
        else:
            desc = rest.rstrip()
        if not group:
            continue
        order.append(group)
        descs[group] = desc
    return order, descs


def _collect_descriptions() -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Return group order, README descriptions, and Usage Guide descriptions.

    Each document keeps its own curated descriptions; for a group that is new or
    only exists in one file, the other falls back to CLI help (first line).
    """
    readme_order, readme_descs = _parse_readme_table(REPO / "cli" / "README.md")
    usage_order, usage_descs = _parse_usage_guide(REPO / "cli" / "CLI_USAGE_GUIDE.md")

    # Preserve README order, then any usage-guide-only groups, then sort
    # remaining CLI groups alphabetically at the end.
    seen = set(readme_order)
    order = list(readme_order)
    for group in usage_order:
        if group not in seen:
            order.append(group)
            seen.add(group)

    for group in sorted(cli.commands):
        if group not in seen:
            order.append(group)
            seen.add(group)

    # Fill missing descriptions from CLI help for whichever doc lacks the group.
    for group in order:
        if group not in readme_descs or group not in usage_descs:
            cmd = cli.commands[group]
            fallback = _first_line(cmd.help) if cmd.help else ""
            if group not in readme_descs:
                readme_descs[group] = fallback
            if group not in usage_descs:
                usage_descs[group] = fallback

    return order, readme_descs, usage_descs


def _subcommands(cmd: click.Command) -> list[str] | None:
    """Return sorted subcommand names for a click Group, or None for a leaf."""
    if not isinstance(cmd, click.Group):
        return None
    return sorted(cmd.commands.keys())


def _format_subs(subs: list[str] | None) -> str:
    if not subs:
        return ""
    return ", ".join(f"`{s}`" for s in subs)


def _generate_readme(commands: dict[str, click.Command], order: list[str], descs: dict[str, str]) -> str:
    lines = ["# AITBC CLI", "", "Command-line interface for the AITBC network.", ""]
    lines += ["## Installation", "", "```bash", "pip install ./cli", "aitbc --help", "```", ""]
    lines += ["## Group catalog", "", "| Group | Description | Key subcommands |"]
    lines += ["|-------|-------------|-----------------|"]

    for name in order:
        if name not in commands:
            continue
        cmd = commands[name]
        desc = descs.get(name, "")
        subs = _subcommands(cmd)
        subs_cell = _format_subs(subs)
        lines.append(f"| `{name}` | {desc} | {subs_cell} |")

    lines += [
        "",
        "## Market vs Marketplace",
        "",
        "Two groups sound similar but serve different layers:",
        "",
        "- `aitbc market` — GPU and software offers published by shop miners (Ollama, Whisper, FFmpeg). These are local/shop offers matched by the coordinator and executed on a provider's GPU.",
        "- `aitbc marketplace` — Global on-chain marketplace for cross-chain listings, bridge operations, and chain-wide economy. It is backed by the marketplace service and may bridge to other islands.",
        "",
        "Use `aitbc market` for AI jobs and local GPU offers; use `aitbc marketplace` for chain-wide trading and bridge listings.",
    ]
    return "\n".join(lines) + "\n"


def _generate_usage_guide(commands: dict[str, click.Command], order: list[str], descs: dict[str, str]) -> str:
    lines = [
        "# AITBC CLI Usage Guide",
        "",
        "This guide is generated from the live `aitbc` command tree. Each entry below lists a top-level group and its key subcommands.",
        "",
    ]

    for name in order:
        if name not in commands:
            continue
        cmd = commands[name]
        desc = descs.get(name, "")
        subs = _subcommands(cmd)
        if subs:
            if desc and not desc.endswith((".", "!", "?")):
                desc += "."
            lines.append(f"- `{name}` — {desc} Subcommands: {_format_subs(subs)}")
        else:
            lines.append(f"- `{name}` — {desc}")

    return "\n".join(lines) + "\n"


def _differs(new: str, path: Path) -> bool:
    if not path.exists():
        return True
    return path.read_text() != new


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate CLI docs")
    parser.add_argument("--check", action="store_true", help="Fail if docs would change")
    args = parser.parse_args()

    commands = dict(cli.commands)
    order, readme_descs, usage_descs = _collect_descriptions()

    readme_text = _generate_readme(commands, order, readme_descs)
    usage_text = _generate_usage_guide(commands, order, usage_descs)

    readme_path = REPO / "cli" / "README.md"
    usage_path = REPO / "cli" / "CLI_USAGE_GUIDE.md"

    if args.check:
        dirty = False
        if _differs(readme_text, readme_path):
            print(f"Would change {readme_path.relative_to(REPO)}")
            dirty = True
        if _differs(usage_text, usage_path):
            print(f"Would change {usage_path.relative_to(REPO)}")
            dirty = True
        if dirty:
            return 1
        return 0

    readme_path.write_text(readme_text)
    usage_path.write_text(usage_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
