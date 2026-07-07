"""Payments context database schema."""

from __future__ import annotations

# Table name prefixes for payments context
PAYMENTS_TABLE_PREFIX = "payments_"

# Payments context table names
JOB_PAYMENT_TABLE = f"{PAYMENTS_TABLE_PREFIX}job_payment"
PAYMENT_ESCROW_TABLE = f"{PAYMENTS_TABLE_PREFIX}escrow"
PAYMENT_RECEIPT_TABLE = f"{PAYMENTS_TABLE_PREFIX}receipt"
