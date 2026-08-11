#!/usr/bin/env python3
"""Guard against float money in source that handles amounts.

CLAUDE.md states the rule plainly: wallet, trading, marketplace and pool-hub use
``Decimal`` for money, never ``float``. This checks it.

It used to check a hand-maintained list of thirteen files with ``re.search(r"float\\(")``.
That was narrow in both directions, and the two failures compounded:

* **Where it looked.** Thirteen files, none of them in wallet, marketplace or pool-hub —
  three of the four services the rule names. Any money code written outside those
  thirteen paths was unguarded, and nothing made the list grow with the repo.
* **What it looked for.** Only the string ``float(``. A field *declared* ``price: float``
  never matches, so the guard could not have caught the defect that prompted this rewrite:
  ``MatchCandidate.price`` in pool-hub was typed ``float | None`` while the column feeding
  it is ``Numeric(20, 8)``, narrowing Decimal to binary floating point at the API boundary.

Now: every tracked Python file is walked, and violations are found by AST rather than by
substring, so a ``float(`` inside a comment or a docstring is not a hit and an annotation
is.

**The baseline.** Applying this to the tree as it stands reports ~200 pre-existing
violations, mostly in coordinator-api. Converting them is a real migration -- the last one
spanned several releases -- not something to bundle into a lint fix. So known violations
are recorded in ``no_float_money_baseline.json`` and the guard fails only on **new** ones.
The baseline can shrink and never grow: that is the whole point, and ``--update-baseline``
is how you record a reduction after fixing something.

A baselined violation is not an accepted one. It is a debt with a number attached.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess  # nosec B404 - used only to list tracked files via git
import sys

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).resolve().parent / "no_float_money_baseline.json"

# Identifiers naming a quantity of money. Matched on underscore-separated tokens, not as
# substrings: "wei" must not match "weight", which it did in an early draft of this list.
MONEY_TOKENS = frozenset(
    {
        "amount",
        "amounts",
        "balance",
        "balances",
        "price",
        "prices",
        "fee",
        "fees",
        "cost",
        "costs",
        "earnings",
        "reward",
        "rewards",
        "payout",
        "payouts",
        "payment",
        "payments",
        "funds",
        "revenue",
        "subtotal",
        "deposit",
        "deposits",
        "withdrawal",
        "withdrawals",
        "wei",
        "satoshi",
    }
)

# Quantities *derived* from money that are legitimately float: ratios, rates, scores,
# percentages, and statistical measures. `fee_percentage` is a proportion; `fee_amount`
# is money. Without this split the guard reports 62 false positives and gets ignored.
DERIVED_TOKENS = frozenset(
    {
        "rate",
        "rates",
        "percentage",
        "percent",
        "ratio",
        "score",
        "scores",
        "volatility",
        "impact",
        "efficiency",
        "compatibility",
        "growth",
        "stability",
        "momentum",
        "threshold",
        "weight",
        "factor",
        "multiplier",
        "index",
        "trend",
        "trends",
        "history",
        "target",
        "margin",
        "change",
        "discount",
        "savings",
        "estimate",
        "per",
        "data",
        "distribution",
    }
)

SKIP_PARTS = (
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "site-packages",
    "build",
    "dist",
    ".mypy_cache",
    "graphify-out",
)
SKIP_DIR_NAMES = ("tests", "test", "examples")

# The thirteen files the guard used to cover. There, *any* float() conversion is a
# violation regardless of what it is bound to, which is the guarantee the old version
# provided and this one would otherwise have dropped: the name-driven rules below would
# permit a non-money float() in a price oracle. All thirteen are clean today, so keeping
# them strict costs nothing and preserves a property already paid for.
STRICT_FILES = frozenset(
    {
        "aitbc/ethereum_rpc.py",
        "aitbc/oracles/price_oracle.py",
        "aitbc/network/web3_utils.py",
        "aitbc/blockchain/rpc_client.py",
        "aitbc/security/validators.py",
        "aitbc/trading/offer_types.py",
        "apps/trading/src/trading_service/routers/exchange_compat.py",
        "apps/trading/src/trading_service/services/offer_sync_service.py",
        "apps/coordinator-api/src/coordinator_api/contexts/payments/services/payments.py",
        "apps/coordinator-api/src/coordinator_api/contexts/payments/routers/payments.py",
        "apps/coordinator-api/src/coordinator_api/schemas/__init__.py",
        "apps/coordinator-api/src/coordinator_api/contexts/blockchain/services/blockchain.py",
        "apps/coordinator-api/src/coordinator_api/contexts/developer_platform/services/developer_platform_service.py",
    }
)


def _is_money_name(name: str) -> bool:
    """True when ``name`` denotes an amount of money rather than something derived from one."""
    tokens = set(name.lower().split("_"))
    if not tokens & MONEY_TOKENS:
        return False
    return not (tokens & DERIVED_TOKENS)


def _tracked_python_files() -> list[Path]:
    """Every tracked ``.py`` file, minus vendored trees, tests and examples.

    Uses ``git ls-files`` so the walk respects ``.gitignore`` -- ``apps/coordinator-api``
    carries its own ``.venv``, and walking it added 255 hits from pip's vendored packages.
    """
    result = subprocess.run(  # nosec B603 B607 - fixed argv, no shell
        ["git", "ls-files", "-z", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    files = []
    for rel in result.stdout.split("\0"):
        if not rel:
            continue
        parts = Path(rel).parts
        if any(p in SKIP_PARTS for p in parts) or any(p in SKIP_DIR_NAMES for p in parts):
            continue
        files.append(Path(rel))
    return sorted(files)


def _target_names(node: ast.AST) -> list[str]:
    """Names a value is being bound to: ``x``, ``self.x``, ``d["x"]``, ``f(x=...)``."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return [str(node.slice.value)]
    if isinstance(node, ast.Tuple | ast.List):
        return [name for element in node.elts for name in _target_names(element)]
    return []


def _is_float_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float"


def _violations_in(path: Path) -> list[str]:
    """Return violation keys for one file.

    Two rules, both driven by the name the value carries rather than by the file it sits
    in. Name-driven is what lets this run over the whole repo instead of a curated list:
    a ``float()`` in a metrics module is fine, the same call bound to ``fee_amount`` is not.

    * ``annotation:<name>`` -- a money field declared ``float``.
    * ``float-call:<name>`` -- a ``float()`` conversion bound to a money name, whether by
      assignment, attribute, dict key or keyword argument.

    Keys are identifier-based, not line-based, so moving code does not churn the baseline.
    """
    try:
        tree = ast.parse((REPO_ROOT / path).read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    keys: list[str] = []
    strict = path.as_posix() in STRICT_FILES

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if "float" in ast.unparse(node.annotation) and _is_money_name(node.target.id):
                keys.append(f"annotation:{node.target.id}")
            if node.value is not None and _is_float_call(node.value) and _is_money_name(node.target.id):
                keys.append(f"float-call:{node.target.id}")

        elif isinstance(node, ast.Assign) and _is_float_call(node.value):
            for target in node.targets:
                for name in _target_names(target):
                    if _is_money_name(name):
                        keys.append(f"float-call:{name}")

        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg and _is_float_call(keyword.value) and _is_money_name(keyword.arg):
                    keys.append(f"float-call:{keyword.arg}")
            # dict(...) literals and Pydantic-style payloads: {"amount": float(x)}
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=False):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and _is_float_call(value)
                    and _is_money_name(key.value)
                ):
                    keys.append(f"float-call:{key.value}")

    if strict:
        # Any float() at all, bound to a money name or not.
        for node in ast.walk(tree):
            if _is_float_call(node):
                keys.append(f"float-call:<strict-file>:{getattr(node, 'lineno', 0)}")

    # A name can legitimately appear more than once in a file; keep one key per distinct
    # (kind, name) so the baseline does not churn when a line is duplicated or moved.
    return sorted(set(keys))


def _scan() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in _tracked_python_files():
        keys = _violations_in(path)
        if keys:
            found[path.as_posix()] = keys
    return found


def _load_baseline() -> dict[str, list[str]]:
    if not BASELINE_PATH.exists():
        return {}
    with BASELINE_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {k: sorted(v) for k, v in data.get("violations", {}).items()}


def _write_baseline(found: dict[str, list[str]]) -> None:
    payload = {
        "_comment": (
            "Known float-money violations, recorded so the guard fails only on new ones. "
            "This list may shrink and must never grow. Regenerate after fixing something "
            "with: python scripts/lint/no_float_money.py --update-baseline"
        ),
        "total": sum(len(v) for v in found.values()),
        "violations": {k: sorted(v) for k, v in sorted(found.items())},
    }
    with BASELINE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to match the tree. Use after fixing violations.",
    )
    args = parser.parse_args()

    found = _scan()

    if args.update_baseline:
        _write_baseline(found)
        total = sum(len(v) for v in found.values())
        print(f"baseline updated: {total} known violations across {len(found)} files")
        return 0

    baseline = _load_baseline()
    new: list[str] = []
    fixed: list[str] = []

    for path, keys in sorted(found.items()):
        known = set(baseline.get(path, []))
        for key in keys:
            if key not in known:
                new.append(f"{path}: {key}")

    for path, keys in sorted(baseline.items()):
        current = set(found.get(path, []))
        for key in keys:
            if key not in current:
                fixed.append(f"{path}: {key}")

    if new:
        print("float money introduced in code that must use Decimal:\n", file=sys.stderr)
        for item in new:
            print(f"  {item}", file=sys.stderr)
        print(
            "\nMoney is Decimal in this repo (CLAUDE.md). If the value is a ratio, a rate or a "
            "score rather than an amount, name it so -- `fee_percentage` is excluded, "
            "`fee_amount` is not.",
            file=sys.stderr,
        )
        return 1

    if fixed:
        # Not a failure: fixing something must never turn CI red. But the baseline is now
        # loose, and a loose baseline is how this kind of guard rots back into uselessness.
        print(f"{len(fixed)} baselined violation(s) no longer present. Tighten the baseline:")
        print("  python scripts/lint/no_float_money.py --update-baseline")
        for item in fixed[:10]:
            print(f"  fixed: {item}")

    total = sum(len(v) for v in found.values())
    print(f"no new float money. {total} known violation(s) remain, see {BASELINE_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
