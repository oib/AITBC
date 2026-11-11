"""Client-side transaction-fee sanity guard (#1714, extended fleet-wide #1744).

The fee is burned on seal and the node only enforces ``fee >= 0`` plus
balance cover — an absurd ``--fee`` is a signed loss, not a rejected
transaction, and a negative fee is a guaranteed node reject after signing.
Every ``--fee``-taking signing path runs ``validate_tx_fee`` before
anything is signed; ``--allow-high-fee`` is the deliberate override.
"""

from __future__ import annotations

from decimal import Decimal

import click

from aitbc.utils.units import DEFAULT_TX_FEE_AIT

from .error_handling import abort

# Sanity ceiling for ``--fee``: 1000x the standard fee is far above any
# priority bump this chain's min_fee=0 mempool needs.
MAX_TX_FEE_AIT = DEFAULT_TX_FEE_AIT * 1000  # 10 AIT

ALLOW_HIGH_FEE_OPTION = click.option(
    "--allow-high-fee",
    is_flag=True,
    help=f"Override the {MAX_TX_FEE_AIT} AIT sanity ceiling on --fee",
)


def validate_tx_fee(ctx: click.Context | None, fee: Decimal, *, allow_high_fee: bool = False) -> None:
    """Refuse negative fees and absurd burns before signing (#1744).

    Raises ``click.Abort`` via ``abort()`` on violation.
    """
    if fee < 0:
        abort(ctx, f"Invalid fee: {fee} AIT (must be >= 0)")
        raise click.Abort()
    if fee > MAX_TX_FEE_AIT and not allow_high_fee:
        abort(
            ctx,
            f"Refusing fee {fee} AIT: above the {MAX_TX_FEE_AIT} AIT sanity ceiling "
            f"({DEFAULT_TX_FEE_AIT} AIT standard). The fee is burned on seal — "
            "pass --allow-high-fee if this is deliberate.",
        )
        raise click.Abort()
