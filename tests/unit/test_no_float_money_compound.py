"""#1033: the guard must see float money inside compound expressions, not just whole RHS.

``_is_float_call`` asked whether the *top* node of a bound value was the
``float()`` call, so ``float(x) * 2``, ``round(float(a), 8)``, ``balance +=
float(x)``, float literals and dict/keyword-nested conversions all walked
past it. ``_contains_float_call`` / ``_contains_float_literal`` walk the
subtree instead. Fixture mirrors scratch/audit3/docs38/lint.py.
"""

import importlib.util
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _lint():
    spec = importlib.util.spec_from_file_location("no_float_money", REPO_ROOT / "scripts" / "lint" / "no_float_money.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["no_float_money"] = module
    spec.loader.exec_module(module)
    return module


def _keys(m, source: str, tmp_path) -> list[str]:
    f = tmp_path / "fixture_compound.py"
    f.write_text(source, encoding="utf-8")
    return m._violations_in(f)


FIXTURE = """
fee = float(x) * 2
subtotal = round(float(x), 2)
balance += float(x)
price = 1.5
cost = amount * 0.05
payload = {"amount": round(float(a), 8)}
send(amount=float(q) + tax)
cost_total: float = 0.0
reward = float(x) if ok else 0.0
"""


def test_all_nine_compound_forms_flagged(tmp_path) -> None:
    m = _lint()
    keys = _keys(m, FIXTURE, tmp_path)
    for name in ("fee", "subtotal", "balance", "price", "cost", "amount", "cost_total", "reward"):
        assert any(k.endswith(f":{name}") for k in keys), (name, keys)


def test_kinds(tmp_path) -> None:
    m = _lint()
    keys = set(_keys(m, "price = 1.5\nfee = float(x) + 1\n", tmp_path))
    assert "float-literal:price" in keys
    assert "float-call:fee" in keys


def test_non_money_still_ignored(tmp_path) -> None:
    m = _lint()
    assert _keys(m, "ratio = 1.5\nscore = float(x) * 2\n", tmp_path) == []
    # not-money marker still works on the compound form
    src = "fee = float(x) * 2  # not-money: ratio of ratios\n"
    assert _keys(m, src, tmp_path) == []
