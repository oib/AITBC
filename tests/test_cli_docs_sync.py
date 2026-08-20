"""Sync test for CLI documentation and actual command tree.

This test parses the generated ``cli/README.md`` and
``cli/CLI_USAGE_GUIDE.md`` and asserts that every top-level group and
explicitly listed subcommand exists in the live CLI, and that every
implemented top-level group is documented.
"""

import os
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
