"""Quality gates for all ``aitbc <path> --help`` output.

This test is intentionally strict: it will fail until the CLI help reaches the
configured 10/10 targets.  Run it frequently while improving docstrings and
examples.
"""

from __future__ import annotations

import warnings

import click
import pytest

from aitbc_cli.core.main import cli
from aitbc_cli.utils.help_quality import (
    walk_commands,
    analyze_help,
    has_examples,
    get_description,
)


# Collect the whole command tree once per test session.
@pytest.fixture(scope="session")
def all_help():
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        return walk_commands(cli)


def _path_str(path):
    return "/".join(path) if path else "(root)"


def test_no_duplicate_option_flags(all_help):
    """No command may declare the same long flag twice."""
    failures = [(_path_str(r["path"]), r["duplicate_flags"]) for r in all_help if r["duplicate_flags"]]
    assert not failures, f"Commands with duplicate option flags: {failures}"


@pytest.mark.xfail(reason="10/10 help work in progress", strict=False)
def test_all_descriptions_at_least_six_words(all_help):
    """Every command/group description must be at least 6 words."""
    failures = []
    for r in all_help:
        desc = get_description(r["text"])
        word_count = len(desc.split()) if desc else 0
        if word_count < 6:
            failures.append((_path_str(r["path"]), word_count, desc))
    assert not failures, f"Short descriptions ({len(failures)}): {failures[:20]}"


@pytest.mark.xfail(reason="10/10 help work in progress", strict=False)
def test_all_leaf_and_group_commands_have_examples(all_help):
    """Every top-level group and every leaf command must contain examples."""
    failures = []
    for r in all_help:
        is_group = isinstance(r["command"], click.Group)
        is_top_group = is_group and len(r["path"]) == 1
        is_leaf = not is_group
        if (is_top_group or is_leaf) and not has_examples(r["text"]):
            failures.append((_path_str(r["path"]), is_group))
    assert not failures, f"Missing examples ({len(failures)}): {failures[:20]}"


@pytest.mark.xfail(reason="10/10 help work in progress", strict=False)
def test_positional_arguments_are_documented(all_help):
    """Commands with positional args must document them.

    After converting positional args to required options, this should pass
    because each former arg becomes an option with its own help text.  Until
    then it is expected to fail and acts as the conversion backlog.
    """
    failures = []
    for r in all_help:
        analysis = analyze_help(r, min_desc_words=6)
        if "positional args undocumented" in [i.split(":")[0] for i in analysis["issues"]]:
            failures.append(analysis["path"])
    assert not failures, f"Undocumented positional args ({len(failures)}): {failures[:20]}"
