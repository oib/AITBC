"""Every ``--fee`` option in the CLI defaults to ``DEFAULT_TX_FEE_AIT``.

REPO-2 moved send/subscribe/batch onto the shared constant; CLI-6 swept
the remaining ``"0.01"`` literals (``wallet send``, top-level ``staking``,
``wallet staking``). This walk keeps any future literal from drifting
apart again — the batch/send mismatch this file's neighbour test caught
was exactly that drift.

The walk resolves the lazy command proxies in ``core/main.py``; a group
that fails to import degrades to an empty command instead of erroring,
so the assertions below also pin that the walk reached the known
fee-bearing commands.
"""

from decimal import Decimal

import click

from aitbc.utils.units import DEFAULT_TX_FEE_AIT


def _fee_defaults(group: click.Group, prefix: str):
    """Yield ``(command_path, --fee default)`` for every command under
    ``group`` whose ``--fee`` option sets a non-None default."""
    for name, command in sorted(group.commands.items()):
        path = f"{prefix} {name}".strip()
        if isinstance(command, click.Group):
            yield from _fee_defaults(command, path)
        for param in getattr(command, "params", []):
            if (
                isinstance(param, click.Option)
                and "--fee" in param.opts
                and param.default is not None
            ):
                yield path, param.default


def test_every_fee_option_defaults_to_shared_constant():
    from aitbc_cli.core.main import cli

    found = list(_fee_defaults(cli, "aitbc"))
    assert found, "walk found no --fee options — the CLI tree failed to load"
    offenders = [
        (path, repr(default))
        for path, default in found
        if Decimal(str(default)) != DEFAULT_TX_FEE_AIT
    ]
    assert offenders == [], (
        f"--fee defaults not on DEFAULT_TX_FEE_AIT ({DEFAULT_TX_FEE_AIT}): {offenders}"
    )


def test_walk_reaches_known_fee_commands():
    """Guard against the walk silently skipping the fee-bearing surface."""
    from aitbc_cli.core.main import cli

    paths = {path for path, _ in _fee_defaults(cli, "aitbc")}
    for expected in (
        "aitbc transactions send",
        "aitbc wallet send",
        "aitbc liquidity-stake",
        "aitbc messaging send",
    ):
        assert expected in paths, f"{expected} missing from --fee walk"
