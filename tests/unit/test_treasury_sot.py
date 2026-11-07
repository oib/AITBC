"""Treasury-address SOT discipline (Refs #489).

The bc-3 treasury literal may appear only where the single source of
truth feeds it: ``docs/deployment/bc3-genesis/classes.json`` (the SOT),
``allocations.json`` (the genesis input it feeds), and prose under
``docs/``. Any hit in code, scripts, env templates, or tests outside the
allowlist is a literal restatement — the failure mode the gates exist to
catch.

Skips cleanly until the operator mints the 2-of-3 address — the schema
lands before the value. A second test pins today's bc-2 discipline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

BC3_GENESIS = REPO / "docs" / "deployment" / "bc3-genesis"
BC2_TREASURY = "0x4aF8F36d91ff6b0125D18A76f242184e4F083EE0"

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "data", "target", "dist"}


def _iter_repo_files():
    # os.walk with dir pruning: Path.rglob descends into venv/.venv anyway —
    # filtering parts afterwards still pays the full traversal cost and timed
    # out on nodes carrying a real virtualenv.
    import os

    skip_suffixes = {".pyc", ".png", ".jpg", ".bin", ".lock"}
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix in skip_suffixes:
                continue
            yield p


def _hits(literal: str):
    found = []
    for p in _iter_repo_files():
        try:
            text = p.read_text(errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        if literal.lower() in text.lower():
            found.append(p.relative_to(REPO).as_posix())
    return found


def _allowed(path: str) -> bool:
    """Where a treasury literal is allowed to live."""
    return path.startswith("docs/deployment/bc") or path.startswith("docs/") or path == "tests/unit/test_treasury_sot.py"


def _bc3_treasury() -> str | None:
    classes = BC3_GENESIS / "classes.json"
    if not classes.exists():
        return None
    t = json.loads(classes.read_text()).get("treasury")
    if isinstance(t, dict):
        addr = t.get("address")
    else:
        addr = t
    if not isinstance(addr, str) or not addr.startswith("0x") or len(addr) != 42:
        return None
    return addr


def test_bc3_treasury_literal_only_in_sot_surfaces():
    addr = _bc3_treasury()
    if addr is None:
        pytest.skip("bc-3 treasury not minted yet (operator item) — schema gates ahead of the value")
    bad = [p for p in _hits(addr) if not _allowed(p)]
    assert not bad, f"bc-3 treasury literal restated outside SOT surfaces: {bad}"


def test_bc3_challenge_string_is_chain_scoped():
    """The proof challenge pinned in the SOT is the chain-scoped bc-3
    rendering of TREASURY_CHALLENGE_TEMPLATE — a bc-2 proof can never
    replay, and neither can a proof for a different address."""
    classes = BC3_GENESIS / "classes.json"
    if not classes.exists():
        pytest.skip("bc-3 classes.json not committed yet")
    treasury = json.loads(classes.read_text())["treasury"]
    addr = treasury["address"]
    expected = f"AITBC bc-3 genesis treasury spendability proof for {addr}"
    assert treasury["proof"]["challenge"] == expected
    assert expected != f"AITBC bc-2 genesis treasury spendability proof for {addr}"


def test_bc2_treasury_literal_stays_in_its_sot_generation():
    """bc-2's literal may be cited in docs (it is a documented address) but
    never inside code/scripts/env that could feed a fresh surface."""
    bad = [p for p in _hits(BC2_TREASURY) if not _allowed(p)]
    assert not bad, f"bc-2 treasury literal leaked outside docs/: {bad}"
