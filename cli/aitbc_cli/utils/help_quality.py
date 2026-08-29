"""CLI help-quality analysis helpers.

Used by tests and audit scripts to measure the completeness and clarity of
``aitbc <path> --help`` output across the whole command tree.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import click


def _split_sections(text: str) -> tuple[str, str, str, str]:
    """Split help text into (usage, description, options, commands) blocks.

    Returns the raw text of each section.  Missing sections are empty strings.
    """
    usage = ""
    description = ""
    options = ""
    commands = ""

    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].startswith("Usage:"):
        i += 1
    if i < len(lines):
        usage_lines = [lines[i].lstrip("Usage:").lstrip()]
        i += 1
        while i < len(lines) and lines[i].strip():
            usage_lines.append(lines[i].strip())
            i += 1
        usage = " ".join(usage_lines)
        # skip blank
        while i < len(lines) and not lines[i].strip():
            i += 1
        # collect description
        desc_lines = []
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                break
            if line.startswith("  "):
                # skip section headers that look like "  Examples:"
                if re.match(r"^\s+[A-Z][a-zA-Z ]*:$", line):
                    break
                desc_lines.append(line.strip())
            else:
                break
            i += 1
        description = " ".join(desc_lines)

        # split the rest by sections
        rest = "\n".join(lines[i:])
        if "\nOptions:" in rest:
            options = rest.split("\nOptions:", 1)[1].split("\n\n", 1)[0]
        if "\nCommands:" in rest:
            commands = rest.split("\nCommands:", 1)[1].split("\n\n", 1)[0]

    return usage, description, options, commands


def get_description(text: str) -> str:
    """Return the main description paragraph from click help text."""
    return _split_sections(text)[1]


def get_command_descriptions(text: str) -> list[str]:
    """Return the descriptions of subcommands in a group help text."""
    _, _, _, commands = _split_sections(text)
    if not commands:
        return []
    return re.findall(r"^\s+[a-z0-9_-]+\s{2,}(.+?)$", commands, re.MULTILINE)


def get_option_flags(text: str) -> list[str]:
    """Return all long option flags declared in the Options: section."""
    _, _, options, _ = _split_sections(text)
    if not options:
        return []
    return re.findall(r"^\s+(?:-[a-zA-Z0-9],\s+)?(--[a-z0-9_-]+)\b", options, re.MULTILINE)


def count_options(text: str) -> int:
    """Count the number of distinct options shown in help."""
    return len(get_option_flags(text))


def get_positional_args_from_usage(text: str) -> list[str]:
    """Extract positional argument metavars from the Usage: line.

    Removes bracketed optional and ``[ARGS]...`` parts, then collects
    all-upper-case tokens.
    """
    usage, _, _, _ = _split_sections(text)
    if not usage:
        return []
    usage = re.sub(r"\[[^\]]*\]", "", usage)
    tokens = re.findall(r"\b[A-Z][A-Z0-9_]*\b", usage)
    # click group usage includes literal "COMMAND" and "ARGS" placeholders.
    return [t for t in tokens if t not in {"COMMAND", "ARGS"}]


def has_examples(text: str) -> bool:
    """Return True if the help text contains an Examples: or Example: section."""
    return re.search(r"\b[Ee]xamples?:", text) is not None


def has_arguments_section(text: str) -> bool:
    """Return True if click rendered an explicit Arguments: section."""
    return "\nArguments:" in text


def get_duplicate_flags(command: click.Command) -> dict[str, int]:
    """Use click introspection to find long flags declared more than once."""
    counts: Counter = Counter()
    for param in command.params:
        if isinstance(param, click.Option):
            for opt in param.opts:
                if opt.startswith("--"):
                    counts[opt] += 1
    return {k: v for k, v in counts.items() if v > 1}


def walk_commands(cli: click.Group, prefix: list[str] | None = None) -> list[dict[str, Any]]:
    """Walk the whole command tree and collect help text for every path.

    Uses in-process ``command.get_help(ctx)`` for speed.  Requires the
    top-level group to be importable (e.g. ``aitbc_cli.core.main:cli``).
    """
    results: list[dict[str, Any]] = []
    prefix = prefix or []

    def _walk(command: click.Command, path: list[str]) -> None:
        ctx = command.make_context(path[-1] if path else cli.name or "aitbc", [], resilient_parsing=True)
        text = command.get_help(ctx)
        duplicate_flags = get_duplicate_flags(command)
        results.append(
            {
                "path": path,
                "command": command,
                "text": text,
                "duplicate_flags": duplicate_flags,
            }
        )
        if isinstance(command, click.Group):
            for name in sorted(command.commands):
                _walk(command.commands[name], path + [name])

    _walk(cli, prefix)
    return results


def analyze_help(result: dict[str, Any], min_desc_words: int = 6) -> dict[str, Any]:
    """Analyze a single help result against the 10/10 rubric."""
    text = result["text"]
    path = result["path"]
    description = get_description(text)
    desc_words = len(description.split()) if description else 0
    positional_args = get_positional_args_from_usage(text)
    options_count = count_options(text)
    example_ok = has_examples(text)

    issues: list[str] = []
    if result["duplicate_flags"]:
        issues.append(f"duplicate options: {result['duplicate_flags']}")
    if desc_words < min_desc_words:
        issues.append(f"description too short ({desc_words} words): {description!r}")
    if positional_args and not (has_arguments_section(text) or has_examples(text)):
        # ponytail: until positional args are converted to options or we add
        # a custom Arguments section, this is the main gap.
        issues.append(f"positional args undocumented: {positional_args}")
    if not example_ok:
        issues.append("no examples section")

    return {
        "path": "/".join(path) if path else "(root)",
        "description": description,
        "desc_words": desc_words,
        "positional_args": positional_args,
        "options_count": options_count,
        "has_examples": example_ok,
        "duplicate_flags": result["duplicate_flags"],
        "issues": issues,
        "ok": not issues,
    }


def score(results: list[dict[str, Any]], min_desc_words: int = 6) -> dict[str, Any]:
    """Score the whole CLI tree."""
    analyses = [analyze_help(r, min_desc_words=min_desc_words) for r in results]
    ok = sum(1 for a in analyses if a["ok"])
    total = len(analyses)
    return {
        "total": total,
        "ok": ok,
        "score": round(100 * ok / total, 2) if total else 0.0,
        "failures": [a for a in analyses if not a["ok"]],
    }
