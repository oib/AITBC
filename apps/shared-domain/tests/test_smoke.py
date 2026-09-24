"""Smoke tests for shared-domain: the re-export surface must stay in sync with aitbc."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def test_domain_reexports_match_aitbc() -> None:
    import shared_domain
    from aitbc.agent_economics import Budget, OnChainAction, OnChainActionType, RevenueRoute

    assert shared_domain.Budget is Budget
    assert shared_domain.OnChainAction is OnChainAction
    assert shared_domain.OnChainActionType is OnChainActionType
    assert shared_domain.RevenueRoute is RevenueRoute


def test_all_lists_only_exports() -> None:
    import shared_domain

    for name in shared_domain.__all__:
        assert hasattr(shared_domain, name), name
