"""#2929: the ESCROW_LOCK amount must never be silently substituted.

``_build_escrow_lock_tx`` used to upgrade any ``ait_to_units(amount) <= 0``
to a full 1-AIT lock — a sub-unit, zero, or negative ``payment.amount``
(the Numeric(20,8) column has no CHECK > 0) locked ~1 AIT from the buyer
while the row recorded the tiny amount. Non-positive amounts now fail the
escrow; positive sub-unit amounts round up to 1 compute-unit per the
units.py convention. The protected-energy path's
``energy_buyer_charge_units`` is likewise validated: JSON meta could carry
a bool, string, float, zero, or negative — all now rejected instead of
being coerced by ``int()``.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pytest
from sqlmodel import Session

from aitbc_shared import JobPayment

from coordinator_api.contexts.payments.services.payments import PaymentService

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
NODE_WALLET = "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01"

UNITS_PER_AIT = 36_000_000


@pytest.fixture
def payment_session(db_engine, monkeypatch) -> Session:
    monkeypatch.setenv("NODE_WALLET_ADDRESS", NODE_WALLET)
    with Session(db_engine) as session:
        yield session


def _payment(amount: Decimal, meta_data: dict | None = None) -> JobPayment:
    return JobPayment(
        job_id="job-amt",
        amount=amount,
        currency="AITBC",
        payment_method="aitbc_token",
        meta_data=meta_data,
    )


# --- non-protected path: payment.amount → compute-units ---


def test_zero_amount_rejected_not_upgraded(payment_session):
    """The old code locked 1 AIT for amount=0 — now it fails."""
    service = PaymentService(payment_session)
    with pytest.raises(ValueError, match="must be positive"):
        service._build_escrow_lock_tx(_payment(Decimal("0")), BUYER, PROVIDER, 3)


def test_negative_amount_rejected(payment_session):
    service = PaymentService(payment_session)
    with pytest.raises(ValueError, match="must be positive"):
        service._build_escrow_lock_tx(_payment(Decimal("-5")), BUYER, PROVIDER, 3)


def test_nan_amount_fails_closed(payment_session):
    """Decimal('NaN') <= 0 raises InvalidOperation — still a fail-closed
    error upstream (_OPS_ERRORS), never a lock."""
    service = PaymentService(payment_session)
    with pytest.raises(InvalidOperation):
        service._build_escrow_lock_tx(_payment(Decimal("NaN")), BUYER, PROVIDER, 3)


def test_sub_unit_amount_rounds_to_one_unit(payment_session):
    """1e-8 AIT is the smallest storable positive (Numeric(20,8)) and is
    0.36 compute-units → rounds to 0 → clamped to 1 unit (units.py
    'minimum positive value' convention), NOT 1 AIT."""
    service = PaymentService(payment_session)
    lock_tx, amount_units = service._build_escrow_lock_tx(_payment(Decimal("0.00000001")), BUYER, PROVIDER, 3)
    assert amount_units == 1
    assert lock_tx["amount"] == 1


def test_normal_amount_unchanged(payment_session):
    service = PaymentService(payment_session)
    lock_tx, amount_units = service._build_escrow_lock_tx(_payment(Decimal("0.1")), BUYER, PROVIDER, 3)
    assert amount_units == int(Decimal("0.1") * UNITS_PER_AIT)
    assert lock_tx["amount"] == amount_units


# --- protected path: meta['energy_buyer_charge_units'] ---


@pytest.mark.parametrize("raw", [True, "12345", 1.5, None, 0, -5, Decimal("10")])
def test_protected_charge_units_rejects_non_positive_int(raw):
    with pytest.raises(ValueError, match="energy_buyer_charge_units"):
        PaymentService._protected_buyer_charge_units({"energy_buyer_charge_units": raw})


def test_protected_charge_units_accepts_positive_int():
    assert PaymentService._protected_buyer_charge_units({"energy_buyer_charge_units": 12_345}) == 12_345
