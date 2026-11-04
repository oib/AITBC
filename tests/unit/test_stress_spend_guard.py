"""#991 pins: spend_guard tracks REAL unit amounts in a daily-window file,
reports headroom, and the cap binds (1000x100 ok, 1001st exceeds)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parents[2] / "scripts/stress/lib.sh"


def _env(tmp_path):
    return {
        **os.environ,
        "STRESS_STATE_DIR": str(tmp_path),
        "STRESS_WALLET": "pinwallet",
        "AMOUNT": "100",
        "CHAIN": "pin",
        "AITBC_BIN": "/bin/true",
        "STRESS_SPEND_CAP": "100000",
    }


def _bash(tmp_path, script):
    return subprocess.run(
        ["bash", "-c", f'. "{LIB}"; {script}'],
        env=_env(tmp_path),
        capture_output=True,
        text=True,
    )


def test_real_amount_recorded(tmp_path):
    """36000 units guarded -> the file says 36000, not the --amount default 100."""
    r = _bash(tmp_path, "spend_guard 36000")
    assert r.returncode == 0, r.stderr
    f = next(tmp_path.glob("spent-pinwallet-*.units"))
    assert f.read_text().strip() == "36000"
    assert "64000/100000" in r.stdout  # headroom reported


def test_cap_binds_and_window_resets(tmp_path):
    """1000 x 100 pass; the 1001st refuses; a new daily window starts clean."""
    r = _bash(tmp_path, "for i in $(seq 1 1000); do spend_guard 100 >/dev/null || exit 1; done")
    assert r.returncode == 0, r.stderr
    r = _bash(tmp_path, "spend_guard 100")
    assert r.returncode != 0
    assert "cap exceeded" in r.stdout + r.stderr
    # daily window: a state dir carrying ONLY yesterday's capped file still
    # spends freely — the window reset, the cap did not carry over
    import datetime as dt

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    yesterday = (dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).strftime("%Y%m%d")
    (fresh / f"spent-pinwallet-{yesterday}.units").write_text("99999")
    r = _bash(fresh, "spend_guard 100 >/dev/null")
    assert r.returncode == 0


def test_play07_guards_the_stake_not_the_default(tmp_path):
    """The play-07 line must read $STAKE_AMT, not $AMOUNT."""
    play = Path(LIB).parent.joinpath("plays/07-agent-staking.sh").read_text()
    assert 'spend_guard "$STAKE_AMT"' in play
    assert 'spend_guard "$AMOUNT"' not in play


def test_play06_guards_the_offer_price_units(tmp_path):
    """Play-06 must guard the offer's real spend (price x 36M units)."""
    play = Path(LIB).parent.joinpath("plays/06-market.sh").read_text()
    assert 'spend_guard "$AMOUNT"' not in play
    assert "STRESS_PRICE" in play.split("spend_guard", 1)[1].splitlines()[0]


def test_play08_guards_the_bounty_reward(tmp_path):
    """Play-08 must guard the deployed reward amount, not the --amount default."""
    play = Path(LIB).parent.joinpath("plays/08-bounty.sh").read_text()
    assert 'spend_guard "${STRESS_REWARD:-360000}"' in play
    assert 'spend_guard "$AMOUNT"' not in play
