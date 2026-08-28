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

**That debt is now paid.** 210 -> 60 -> 48 -> 24 -> 13 -> 0 over five passes, so the
baseline is empty and this is an ordinary gate: anything it reports is a regression.

Worth reading before adding a rule, because the pattern held every single time: each of
the six widenings found real defects in code the previous pass had reported as clean.
``per`` and ``target`` in ``DERIVED_TOKENS`` were hiding ``price_per_hour`` and
``target_amount``; ``ast.IfExp`` was hiding four coordinator-api violations one pass after
that app reached zero; reading only ``ast.Name`` annotation targets was hiding
``self.earnings`` and ``self.total_spent`` in the agent SDK; and parameter annotations were
hiding ``ait_to_units(ait: float)``, which is the function that turns a user's
``--amount`` into the integer the chain settles. **"Zero violations" only ever means zero of
what the checker can currently see.**
"""

from __future__ import annotations

import argparse
import ast
import json
import re
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
        "budget",
        "budgets",
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
        "funding",
        "funds",
        "revenue",
        "spend",
        "spending",
        "spent",
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
#
# The test for membership here is **dimensionless or non-numeric**, not "sounds
# adjacent to money". Two entries failed that test and were removed after the
# coordinator-api migration ran into what they were hiding:
#
# * ``per`` excluded ``price_per_hour`` -- the single most common money field name in this
#   repo, and already ``Numeric(20, 8)`` on the ``marketplaceoffer`` table. The API view
#   that re-declared it ``float`` narrowed a Decimal column back to binary floating point,
#   which is the exact defect this guard exists to catch.
# * ``target`` excluded ``target_amount``, which sat beside a flagged ``source_amount`` in
#   the same ``AtomicSwapOrder`` row -- one side of a swap guarded, the other not.
#
# ``margin``, ``change``, ``savings`` and ``discount`` are the same shape of risk
# (``cost_savings`` and ``discount_amount`` are money) and are kept only because nothing in
# this tree currently proves them wrong. Prefer naming a proportion ``_percentage``.
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
        "margin",
        "change",
        "discount",
        "savings",
        "estimate",
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


def _tokenize(name: str) -> set[str]:
    """Split an identifier into lowercase word tokens.

    Both conventions, because this tree uses both: ``total_amount`` is snake_case and
    ``averagePrice`` (in ``schemas/__init__.py``) is camelCase. Splitting on ``_`` alone
    made every camelCase money field invisible.

    Tokens, never substrings -- an early draft matched ``wei`` inside ``weight``.
    """
    return set(re.findall(r"[a-z]+|[0-9]+", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()))


def _is_money_name(name: str) -> bool:
    """True when ``name`` denotes an amount of money rather than something derived from one."""
    tokens = _tokenize(name)
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


def _is_narrowed_float(annotation: ast.AST) -> bool:
    """True when an annotation says float *without* also admitting Decimal.

    ``amount: float`` narrows -- the caller cannot hand this function an exact value at all.
    ``amount: Decimal | float | str`` does not: it is a coercion boundary, and this repo has
    a dozen of them on purpose (``money.to_atomic_units``, ``grant_service.create_grant``,
    ``capacity_publisher.publish_capacity``), each normalising to Decimal on the first line.
    Reporting those would be telling the code to stop accepting the type it exists to accept.

    Whether such a boundary then *keeps* the value exact is a separate question, and one the
    body rules already answer: a ``float(amount)`` inside it is still ``float-call:amount``.
    """
    rendered = ast.unparse(annotation)
    return "float" in rendered and "Decimal" not in rendered


def _annotated_name(target: ast.AST) -> str | None:
    """The name being declared by an annotated assignment, or None.

    ``x: float`` is an ``ast.Name``, but ``self.x: float = 0.0`` is an ``ast.Attribute``.
    Both are declarations of the same thing, and this rule read only the first for four
    PRs -- which is how ``ComputeProvider.earnings`` and ``ComputeConsumer.total_spent``
    stayed float in a tree the guard reported as clean.
    """
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _is_float_call(node: ast.AST) -> bool:
    """True for ``float(x)``, including inside a conditional expression.

    ``{"amount": float(amount) if amount else 0}`` is an ``IfExp``, not a ``Call``, so
    checking the node type alone walked straight past it. That exact line was sending a
    narrowed escrow amount to a node that parses it back with ``Decimal(str(amount))`` --
    a rounding step whose result the receiver then preserved faithfully.
    """
    if isinstance(node, ast.IfExp):
        return _is_float_call(node.body) or _is_float_call(node.orelse)
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float"


SUPPRESSION = "# not-money:"


def _suppressed_lines(source: str) -> frozenset[int]:
    """Line numbers carrying a ``# not-money: <reason>`` marker.

    A name-driven guard has false positives, and there is exactly one honest place to
    record them: the declaration itself. ``price_difference`` on ``arbitrage_opportunity``
    is a percentage whose name says "price"; parking it in the baseline would file it as
    debt to be repaid, which is the wrong claim about it, and would leave the next reader
    of that line no wiser. The reason is mandatory -- a bare marker is not accepted.
    """
    return frozenset(
        number
        for number, line in enumerate(source.splitlines(), start=1)
        if (index := line.find(SUPPRESSION)) != -1 and line[index + len(SUPPRESSION) :].strip()
    )


def _is_suppressed(node: ast.AST, skip: frozenset[int], comment_lines: frozenset[int]) -> bool:
    """True when a marker sits in the node's line span or in the comment block above it.

    Three things forced this shape, each found by the marker silently not working:

    * The **span**, not just ``lineno``: appending the marker to a long declaration pushes
      it past the line limit, and ruff-format then wraps the call so the comment lands on
      the last line while the node still starts on the first.
    * The line **above**: putting it on its own line avoids that wrapping entirely, and
      reads better than trailing a declaration.
    * The whole **comment block** above, not just one line: the cases that most need a
      marker are the ones that need a paragraph to justify -- ``payment`` in
      ``rpc/ai_services.py`` needs four lines to say why converting it is a hard fork.
      Requiring the marker to be the last of those lines is a trap that springs quietly.

    What it deliberately does **not** do is cover a run of statements. A comment block
    suppresses the statement directly beneath it and nothing further, so a stanza of three
    float conversions under one paragraph needs a short marker on each of the other two.
    That is noisier, and it is the right trade: the alternative silently exempts whatever
    someone appends to the stanza later.
    """
    start = getattr(node, "lineno", None)
    if start is None:
        return False
    end = getattr(node, "end_lineno", None) or start
    if any(line in skip for line in range(start, end + 1)):
        return True
    line = start - 1
    while line in comment_lines:
        if line in skip:
            return True
        line -= 1
    return False


def _violations_in(path: Path) -> list[str]:
    """Return violation keys for one file.

    Two rules, both driven by the name the value carries rather than by the file it sits
    in. Name-driven is what lets this run over the whole repo instead of a curated list:
    a ``float()`` in a metrics module is fine, the same call bound to ``fee_amount`` is not.

    * ``annotation:<name>`` -- a money field declared ``float``.
    * ``float-call:<name>`` -- a ``float()`` conversion bound to a money name, whether by
      assignment, attribute, dict key or keyword argument.

    Keys are identifier-based, not line-based, so moving code does not churn the baseline.

    * ``param:<name>`` -- a money parameter declared ``float``. Measured at 131 sites when
      the rule was added; ``_is_narrowed_float`` took that to 119 by exempting unions that
      also admit ``Decimal``, and the rest were converted or marked in one pass.

    Keys are per **name**, not per site, so one entry can cover several declarations of the
    same field in a file. That keeps the baseline stable when code moves, at the cost of the
    entry count understating the work -- ``aitbc/trading/types.py`` was one entry and four
    dataclasses.
    """
    try:
        source = (REPO_ROOT / path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []
    except FileNotFoundError:
        # ``git ls-files`` reads the index, so a file deleted in the working tree but not
        # yet staged is still listed. Without this the hook dies with a traceback partway
        # through the run -- which is what deleting one .py file did in V23-102, turning a
        # routine deletion into an unrelated-looking lint crash. A file that is not there
        # holds no violations.
        return []

    keys: list[str] = []
    strict = path.as_posix() in STRICT_FILES
    skip = _suppressed_lines(source)
    comments = frozenset(number for number, line in enumerate(source.splitlines(), start=1) if line.lstrip().startswith("#"))

    for node in ast.walk(tree):
        if _is_suppressed(node, skip, comments):
            continue

        if isinstance(node, ast.AnnAssign) and (declared := _annotated_name(node.target)):
            if "float" in ast.unparse(node.annotation) and _is_money_name(declared):
                keys.append(f"annotation:{declared}")
            if node.value is not None and _is_float_call(node.value) and _is_money_name(declared):
                keys.append(f"float-call:{declared}")

        elif isinstance(node, ast.arg) and node.annotation is not None:
            # ``def pay(amount: float)``. Every parameter kind -- positional, keyword-only,
            # ``*args``, ``**kwargs`` -- is an ``ast.arg``, so one branch covers them all.
            if _is_narrowed_float(node.annotation) and _is_money_name(node.arg):
                keys.append(f"param:{node.arg}")

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
            if _is_float_call(node) and not _is_suppressed(node, skip, comments):
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
            "with: python scripts/lint/no_float_money.py --update-baseline. "
            "It started at 210 and is now empty, so the guard is a plain gate again -- "
            "any entry appearing here is a regression, not inherited debt."
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
