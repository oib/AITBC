"""There is one CLI tree, and `cli.utils` is not it.

V23-43. `cli/utils/` was a parallel copy of `cli/aitbc_cli/utils/` that shipped nothing —
`setup.py` packages only `aitbc_cli`, and every production import is `aitbc_cli.utils.*`. It
was still importable, because `cli/__init__.py` made `cli` a package and the repo root is on
`sys.path` under pytest. So `from cli.utils.crypto_utils import sign_challenge` worked and
picked up wallet-signing code 158 lines diverged from the copy the CLI actually runs, and
`cli.utils.encrypt_value` was a different implementation from the shipped one.

Nothing imported it but its own three test files. It is gone; this stops it coming back,
which a deleted directory on its own does not.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_cli_is_not_a_real_package():
    """`cli/` is a source directory on the path, not a package to import through.

    It still resolves as a *namespace* package, because any directory on `sys.path` does and
    there is nothing to be done about that. What matters is that it has no `__init__.py` and
    therefore no module of its own — a namespace package with no submodules imports nothing.
    """
    assert not (REPO_ROOT / "cli" / "__init__.py").exists(), (
        "cli/__init__.py is back. It makes `cli.*` a real package importable from the repo "
        "root, which is how a second copy of the CLI's utilities stayed reachable — V23-43."
    )
    spec = importlib.util.find_spec("cli")
    assert spec is None or spec.loader is None, f"`cli` is a real package again: {spec}"


def test_there_is_no_second_utils_tree():
    assert not (REPO_ROOT / "cli" / "utils").is_dir(), (
        "cli/utils/ is back. The CLI's utilities live in cli/aitbc_cli/utils/, which is the "
        "only tree setup.py packages and the only one production code imports."
    )
    assert importlib.util.find_spec("cli.utils") is None, "`cli.utils` is importable again"


def test_the_relocated_audit_logger_is_where_it_was_moved_to():
    """`secure_audit` was the one module in that tree with no equivalent anywhere else."""
    assert (REPO_ROOT / "cli" / "aitbc_cli" / "utils" / "secure_audit.py").is_file()

    from aitbc_cli.utils.secure_audit import SecureAuditLogger

    assert hasattr(SecureAuditLogger, "verify_integrity"), "the tamper-evident chain is the point"
