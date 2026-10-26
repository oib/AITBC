"""CLI-REINVEST-LOAD-1: _load_miner_app must import miner_app from the src layout."""

import sys


def test_load_miner_app_imports(monkeypatch):
    """With miner paths scrubbed, the loader must still resolve miner_app
    (itself adds apps/miner/src). Mutation (apps/miner without /src)
    cannot import -> test fails."""
    for m in [m for m in sys.modules if m.startswith("miner_app")]:
        monkeypatch.delitem(sys.modules, m)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if "miner" not in p.lower()])
    from aitbc_cli.commands.reinvest import _load_miner_app

    engine, policy, budget = _load_miner_app()
    assert engine.__name__ and policy.__name__ and budget.__name__
