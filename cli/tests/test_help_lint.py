"""CLI-HELP-LINT-1: every leaf --help exits 0 with non-empty option help."""

import click
import aitbc_cli.core.main as main


def _leaves(node, path):
    kids = getattr(node, "commands", {})
    if not kids:
        yield node, path
        return
    for name, child in sorted(kids.items()):
        if getattr(child, "deprecated", False):
            continue
        yield from _leaves(child, path + (name,))


def test_all_leaves_help_nonempty():
    from click.testing import CliRunner

    r = CliRunner()
    bad = []
    for leaf, path in _leaves(main.cli, ()):
        res = r.invoke(leaf, ["--help"])
        assert res.exit_code == 0, " ".join(path)
        for p in getattr(leaf, "params", []):
            if isinstance(p, click.Option) and p.name not in ("help",):
                if not (p.help or "").strip():
                    bad.append((" ".join(path), "/".join(p.opts)))
    assert bad == [], f"options missing help text: {bad}"


def test_no_empty_help_strings():
    bad = []
    for leaf, path in _leaves(main.cli, ()):
        for p in getattr(leaf, "params", []):
            if isinstance(p, click.Option) and p.name != "help" and p.help is not None and not p.help.strip():
                bad.append((" ".join(path), "/".join(p.opts)))
    assert bad == []
