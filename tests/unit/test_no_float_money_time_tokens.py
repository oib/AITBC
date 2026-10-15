"""``no_float_money`` must not flag monotonic bookkeeping that sits next to money.

CLEAN-1/5b: a ``dict[int, float]`` of ``time.monotonic()`` deadlines keyed by
payout id — ``payout_deadlines`` — was reported as ``annotation:payout_deadlines``
because ``payout`` is a money token and the guard could not see that the float
is a time. ``TIME_TOKENS`` names the quantities (deadlines, timestamps, retry
counters, durations) that are never money even when a money token shares the
identifier, mirroring how ``DERIVED_TOKENS`` names ratios and rates.

The boundary is the point of the set: ``at`` and ``last`` are deliberately NOT
time tokens because ``balance_at`` / ``last_payment`` are amounts. Those cases
keep flagging, and a genuinely non-money float that nothing here covers still
has the ``# not-money:`` marker.
"""

import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _lint():
    spec = importlib.util.spec_from_file_location("no_float_money", REPO_ROOT / "scripts" / "lint" / "no_float_money.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["no_float_money"] = module
    spec.loader.exec_module(module)
    return module


def _violations_for(tmp_path: pathlib.Path, source: str) -> list[str]:
    lint = _lint()
    probe = tmp_path / "probe.py"
    probe.write_text(source)
    real_root = lint.REPO_ROOT
    lint.REPO_ROOT = tmp_path
    try:
        return lint._violations_in(pathlib.Path("probe.py"))
    finally:
        lint.REPO_ROOT = real_root


class TestTimeTokenExemption:
    @pytest.mark.parametrize(
        "name",
        [
            "payout_deadlines",
            "payment_retry_at",
            "deposit_seen",
            "refund_backoff_until",
            "fee_attempts",
            "withdrawal_cooldown",
            "cost_delay",
        ],
    )
    def test_monotonic_dict_is_not_money(self, tmp_path, name):
        source = f"{name}: dict[int, float] = {{}}\n"
        assert _violations_for(tmp_path, source) == [], source

    def test_plain_money_annotation_still_flags(self, tmp_path):
        assert _violations_for(tmp_path, "payout_amount: float = 0.0\n") == ["annotation:payout_amount"]

    def test_snapshot_name_is_still_money(self, tmp_path):
        """``at``/``last`` stay money: they name amount snapshots, not times."""
        assert _violations_for(tmp_path, "balance_at: float = 0.0\n") == ["annotation:balance_at"]
        assert _violations_for(tmp_path, "last_payment: float = 0.0\n") == ["annotation:last_payment"]

    def test_marker_escape_hatch_unchanged(self, tmp_path):
        source = "# not-money: a ratio kept as float for the wire format\nreward_share: float = 0.0\n"
        assert _violations_for(tmp_path, source) == []
