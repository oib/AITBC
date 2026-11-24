"""Pin wallet_amount() refusing non-numeric input instead of coercing to 0.

CLI-AMOUNT-COERCE-1 (issue #491): ``market escrow create --amount notanumber``
passed ``Decimal("0")`` downstream because ``wallet_amount`` swallowed
``InvalidOperation`` and returned zero. A silent zero is a wrong amount, not a
missing one — the parse must refuse with a named error.
"""

import warnings
from decimal import Decimal

import click
import pytest

from aitbc_cli.utils.money import wallet_amount, wallet_ledger_balance


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


def test_wallet_ledger_balance_reads_canonical_ait_untouched():
    """AIT-denominated stored balances pass through unchanged (#2730)."""
    assert wallet_ledger_balance("100.0") == Decimal("100.0")
    assert wallet_ledger_balance("0.0309830555") == Decimal("0.0309830555")
    assert wallet_ledger_balance(0) == Decimal("0")
    assert wallet_ledger_balance(999999) == Decimal("999999")


def test_wallet_ledger_balance_unwraps_legacy_units():
    """Unit-scale stored balances (pre-#2196 writers) convert to AIT once (#2730)."""
    from aitbc.utils.units import units_to_ait

    # the observed node0 default.json value: 1115390 units ≈ 0.031 AIT
    with pytest.warns(UserWarning, match="balance_unit"):
        assert wallet_ledger_balance(1115390) == units_to_ait(1115390)
    with pytest.warns(UserWarning, match="balance_unit"):
        assert wallet_ledger_balance("36000000") == Decimal("1")
    # exactly at the floor is units; one below stays AIT
    with pytest.warns(UserWarning, match="balance_unit"):
        assert wallet_ledger_balance(1000000) == units_to_ait(1000000)
    assert wallet_ledger_balance(999999) == Decimal("999999")


def test_wallet_ledger_balance_honours_explicit_balance_unit_marker():
    """An explicit ``balance_unit`` marker settles the units-vs-AIT ambiguity (#2887)."""
    from aitbc.utils.units import units_to_ait

    # "ait" disables the heuristic: a real balance at/above the floor is never
    # silently reinterpreted as units — this is the #2887 corruption case.
    assert wallet_ledger_balance(2000000, balance_unit="ait") == Decimal("2000000")
    assert wallet_ledger_balance("2000000.5", balance_unit="ait") == Decimal("2000000.5")
    # "units" forces conversion even below the floor.
    assert wallet_ledger_balance(36000000, balance_unit="units") == Decimal("1")
    assert wallet_ledger_balance(500, balance_unit="units") == units_to_ait(500)
    # Marked files never warn.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        wallet_ledger_balance(2000000, balance_unit="ait")
        wallet_ledger_balance(2000000, balance_unit="units")


def test_save_wallet_stamps_balance_unit_ait(tmp_path):
    """Every ``_save_wallet`` write marks ``balance`` as canonical AIT (#2887)."""
    from aitbc_cli.commands.wallet import _save_wallet

    wallet_file = tmp_path / "w.json"
    _save_wallet(wallet_file, {"name": "w", "address": "0xabc", "balance": "2.5"})
    import json

    assert json.loads(wallet_file.read_text())["balance_unit"] == "ait"
