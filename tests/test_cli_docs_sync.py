"""Sync test for CLI documentation and actual command tree.

This test parses the generated ``cli/README.md`` and
``cli/CLI_USAGE_GUIDE.md`` and asserts that every top-level group and
explicitly listed subcommand exists in the live CLI, and that every
implemented top-level group is documented.
"""

import os
import shlex
import warnings
import re
from pathlib import Path

import click

os.environ.setdefault("AITBC_SKIP_ENV_FILES", "1")

REPO = Path(__file__).resolve().parents[1]

from cli_gap_analysis import (  # noqa: E402
    cli,
    expand_wildcard,
    parse_readme_table,
    parse_usage_guide_groups,
)


def _build_expected_subcommands(readme_text, usage_text):
    """Merge explicit subcommand lists from README and Usage Guide."""
    readme_groups = parse_readme_table(readme_text)
    usage_groups = parse_usage_guide_groups(usage_text)
    expected = {}
    for g in set(readme_groups) | set(usage_groups):
        r = readme_groups.get(g)
        u = usage_groups.get(g)
        if r is not None:
            expected[g] = r
        elif u is not None:
            expected[g] = u
        else:
            expected[g] = None
    return expected


def test_cli_docs_sync():
    """README/Usage-Guide groups and subcommands must match the live CLI tree."""
    readme_text = (REPO / "cli" / "README.md").read_text()
    usage_text = (REPO / "cli" / "CLI_USAGE_GUIDE.md").read_text()

    top_level = set(cli.commands.keys())
    expected = _build_expected_subcommands(readme_text, usage_text)
    doc_top = set(expected)

    undocumented = top_level - doc_top
    missing = doc_top - top_level

    assert not undocumented, f"Top-level commands missing from docs: {sorted(undocumented)}"
    assert not missing, f"Top-level commands documented but missing from CLI: {sorted(missing)}"

    subcommand_mismatches = []
    for group, subs in expected.items():
        if subs is None:
            continue
        if group not in cli.commands:
            subcommand_mismatches.append(f"{group}: group documented but not in CLI")
            continue
        cmd = cli.commands[group]
        if not isinstance(cmd, click.Group):
            subcommand_mismatches.append(f"{group}: documented as group but is a leaf command")
            continue
        actual = set(cmd.commands.keys())
        documented = set()
        for token in subs:
            documented.update(expand_wildcard(token, actual))
        extra = actual - documented
        missing_subs = documented - actual
        if missing_subs:
            subcommand_mismatches.append(f"{group}: documented but missing: {sorted(missing_subs)}")
        if extra:
            subcommand_mismatches.append(f"{group}: implemented but not documented: {sorted(extra)}")

    assert not subcommand_mismatches, "Subcommand sync failures:\n" + "\n".join(subcommand_mismatches)


def test_man_page_commands_sync():
    """The aitbc.1 COMMANDS section must list exactly the live top-level
    commands, and the DESCRIPTION count must match — both are regenerated
    by scripts/generate_cli_docs.py."""
    man_text = (REPO / "cli" / "man" / "aitbc.1").read_text()
    section = man_text.split("\n.SH COMMANDS\n", 1)[1].split("\n.SH ", 1)[0]
    documented = set(re.findall(r"\\fB([\w-]+)\\fR", section))
    top_level = set(cli.commands)
    assert documented == top_level, (
        f"man page COMMANDS drift: documented-only {sorted(documented - top_level)}, missing {sorted(top_level - documented)}"
    )

    count_match = re.search(r"The CLI provides (\d+) main command groups", man_text)
    assert count_match, "DESCRIPTION command-group count sentence not found"
    assert int(count_match.group(1)) == len(top_level), (
        f"DESCRIPTION says {count_match.group(1)} groups, CLI has {len(top_level)}"
    )


def _man_examples():
    """Extract the curated ``aitbc ...`` example lines from the EXAMPLES
    section of cli/man/aitbc.1 (hand-maintained — the generator only
    refreshes COMMANDS and the group count)."""
    man_text = (REPO / "cli" / "man" / "aitbc.1").read_text()
    section = man_text.split("\n.SH EXAMPLES\n", 1)[1].split("\n.SH ", 1)[0]
    return [line.strip() for line in section.splitlines() if line.strip().startswith("aitbc ")]


def _remaining_args(ctx):
    """Unconsumed args after a group's parse. ``Context.protected_args``
    holds the subcommand name on click 8.x and is deprecated/removed on
    click 9.x, where ``ctx.args`` carries the full remainder."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        protected = list(getattr(ctx, "protected_args", []) or [])
    return protected + list(ctx.args)


def _resolve_and_parse(argv):
    """Walk ``argv`` (tokens after ``aitbc``) through the live command tree,
    parsing options at each level and validating the leaf command's params —
    without invoking any callback."""
    ctx = cli.make_context("aitbc", list(argv))
    node = cli
    while isinstance(node, click.Group):
        rest = _remaining_args(ctx)
        if not rest:
            raise AssertionError("resolves to a group, not a runnable command")
        name, node, rest = node.resolve_command(ctx, rest)
        if node is None:
            raise AssertionError(f"no such command: {name}")
        ctx = node.make_context(name, rest, parent=ctx)


def test_man_page_examples_parse():
    """Every example line in aitbc.1 EXAMPLES must resolve and parse against
    the live CLI tree — catches stale group names, removed subcommands,
    missing required options, and misplaced global flags (GAP-CLI-MAN-EXAMPLES-1)."""
    examples = _man_examples()
    assert examples, "no `aitbc ...` lines found in the aitbc.1 EXAMPLES section"
    failures = []
    for example in examples:
        try:
            _resolve_and_parse(shlex.split(example)[1:])
        except click.ClickException as exc:
            failures.append(f"  {example!r} -> {exc.format_message()}")
        except AssertionError as exc:
            failures.append(f"  {example!r} -> {exc}")
    assert not failures, "man-page examples that no longer parse:\n" + "\n".join(failures)
