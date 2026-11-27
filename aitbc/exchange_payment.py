"""Canonical configuration for the ETH -> AITBC exchange-payment endpoints.

``coordinator-api`` (``/v1/exchange/*``) and ``trading``
(``/v1/exchange/*`` compat router) serve the same logical operation —
create an ETH-denominated payment request for an AITBC amount. Both were
migrated from one original Bitcoin-denominated implementation, and their
copies drifted: the coordinator copy was deliberately re-pegged at
1 ETH = 1,000 AITBC with 12 confirmations during the BTC->ETH migration,
while the trading copy was migrated by renaming symbols only and kept the
BTC-era 1 BTC = 100,000 AITBC peg and 1 confirmation — a 100x divergence
on the required ETH amount, plus divergent fee reporting and amount-match
strictness (#3051, AUDIT-EXCHANGE-PEG-DRIFT-1).

The peg, confirmation policy, payment timeout, reported fee, and the
amount-match tolerance are therefore defined once here and imported by
both routers. Do not re-declare them per service.
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

# Configured peg, not a traded price — there is no rate discovery yet, so
# the honest 24h change stays 0 until a real rate feed exists.
EXCHANGE_RATE_ETH_TO_AITBC = Decimal("1000")  # 1 ETH = 1,000 AITBC

# Finality policy for the ETH leg. 12 confirmations matches the
# coordinator's deliberate ETH choice (the BTC-era value of 1 was a
# different chain's policy).
EXCHANGE_MIN_CONFIRMATIONS = 12

EXCHANGE_PAYMENT_TIMEOUT_SECONDS = 3600  # 1 hour

# Client-facing tolerance on the ETH amount check. Clients may compute
# ``aitbc_amount / rate`` in binary floating point, so exact Decimal
# equality rejects legitimate rounded submissions; 1e-8 ETH is far below
# any meaningful payment granularity.
EXCHANGE_ETH_AMOUNT_TOLERANCE = Decimal("0.00000001")

# Failure surface for the env-var parse below: env Decimal conversion
# (ValueError/InvalidOperation/TypeError) and OS-level getenv errors.
_ENV_ERRORS = (OSError, ValueError, InvalidOperation, TypeError)


def expected_eth_amount(aitbc_amount: Decimal) -> Decimal:
    """ETH a client must send for ``aitbc_amount`` AITBC at the peg."""
    return aitbc_amount / EXCHANGE_RATE_ETH_TO_AITBC


def eth_amount_matches(aitbc_amount: Decimal, eth_amount: Decimal) -> bool:
    """True when ``eth_amount`` equals the peg price of ``aitbc_amount`` within tolerance."""
    return abs(eth_amount - expected_eth_amount(aitbc_amount)) <= EXCHANGE_ETH_AMOUNT_TOLERANCE


def exchange_fee_percent() -> Decimal:
    """Configured exchange fee percent.

    Mirrors the exchange service's ``EXCHANGE_FEE_PCT`` (the fraction the
    order-book fee applies to the gross AIT leg), replacing the stale
    hardcoded 0.5 both compat routers used to report. Unset or unparsable
    config reports 0 — the exchange's own default is no fee.
    """
    try:
        fee_pct = Decimal(os.getenv("EXCHANGE_FEE_PCT", "0"))
        if not fee_pct.is_finite() or fee_pct < 0:
            return Decimal("0")
        return fee_pct
    except _ENV_ERRORS:
        return Decimal("0")
