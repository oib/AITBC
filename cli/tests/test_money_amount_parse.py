"""Pin wallet_amount() refusing non-numeric input instead of coercing to 0.

CLI-AMOUNT-COERCE-1 (issue #491): ``market escrow create --amount notanumber``
passed ``Decimal("0")`` downstream because ``wallet_amount`` swallowed
``InvalidOperation`` and returned zero. A silent zero is a wrong amount, not a
missing one — the parse must refuse with a named error.
"""

from decimal import Decimal

import click
import pytest

from aitbc_cli.utils.money import wallet_amount


def test_wallet_amount_rejects_non_numeric_string():
    with pytest.raises(click.ClickException):
        wallet_amount("notanumber")


def test_wallet_amount_rejects_garbage_that_is_not_a_number():
    for bad in ("abc", "1.2.3", "", "0x10", "1e", "--", "10 AIT"):
        with pytest.raises(click.ClickException):
            wallet_amount(bad)


def test_wallet_amount_rejects_non_finite():
    for bad in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(click.ClickException):
            wallet_amount(bad)


def test_wallet_amount_parses_valid_integer_and_decimal():
    assert wallet_amount("100") == Decimal("100")
    assert wallet_amount("0.1") == Decimal("0.1")
    assert wallet_amount("1.234567890123456789") == Decimal("1.234567890123456789")
    assert wallet_amount(0) == Decimal("0")
    assert wallet_amount(2.5) == Decimal("2.5")
    assert wallet_amount(Decimal("7")) == Decimal("7")


def test_wallet_amount_none_still_defaults_to_zero():
    # Absent optional value is a legitimate zero; garbage is not.
    assert wallet_amount(None) == Decimal("0")


def test_escrow_create_rejects_non_numeric_amount_at_parse_time():
    """`market escrow create --amount notanumber` is a usage error, not a 0 escrow."""
    from click.testing import CliRunner

    from aitbc_cli.commands.market import escrow as esc_mod

    runner = CliRunner()
    result = runner.invoke(
        esc_mod.escrow,
        ["create", "--job-id", "j1", "--buyer", "0xb", "--provider", "0xp", "--amount", "notanumber"],
        obj={"output_format": "json"},
    )
    assert result.exit_code != 0
    assert "not a valid" in result.output or "notanumber" in result.output
