"""A Click parameter type that parses money as ``Decimal``.

``@click.option("--amount", type=float)`` was the pattern everywhere in this CLI, and it is
the reason annotating the handler ``amount: Decimal`` would have been a lie: Click converts
the argument *before* the function is called, so the parameter holds a float no matter what
the annotation says. ``--amount 0.1`` reached ``send()`` as ``0.1000000000000000055511...``.

``type=DECIMAL`` parses the user's own digits instead:

    >>> DecimalParamType().convert("0.1", None, None) == Decimal("0.1")
    True

``float`` is never constructed, so there is nothing to round. Rejecting bad input is Click's
job and stays Click's job -- ``convert`` raises ``BadParameter`` the same way ``type=float``
does, so ``--amount abc`` still fails with a usage error rather than a traceback.

NaN and the infinities parse fine as ``Decimal`` and are rejected explicitly: they are valid
literals for the type but never a valid quantity of money, and ``Decimal("NaN") > 0`` is
False, so a downstream positivity check would pass them through.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import click


class DecimalParamType(click.ParamType):
    """Click parameter type converting to ``Decimal`` without going through ``float``."""

    name = "decimal"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> Decimal:
        if isinstance(value, Decimal):
            return value
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, ArithmeticError):
            self.fail(f"{value!r} is not a valid decimal number", param, ctx)
        if not parsed.is_finite():
            self.fail(f"{value!r} is not a finite decimal number", param, ctx)
        return parsed


DECIMAL = DecimalParamType()


def wallet_amount(value: Any) -> Decimal:
    """Read a money value out of a local JSON file as ``Decimal``.

    The CLI's wallet, multisig and exchange files store money as decimal **strings** --
    ``json.dump`` cannot serialise a ``Decimal``, and writing ``float(amount)`` instead
    would put back exactly the rounding the ``Decimal`` was for. Files written by older
    builds hold JSON numbers, so both have to read.

    ``str()`` first is what makes that work: it is a no-op for a string, and for a float it
    parses the shortest repr rather than the full binary expansion, so ``0.1`` on disk reads
    back as ``Decimal("0.1")`` and not ``Decimal("0.1000000000000000055511151231257827")``.
    """
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, ArithmeticError):
        return Decimal("0")
