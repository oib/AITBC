"""Pin: 18-wedge-replay.sh's live-run parameters (#1130).

The play's poison and recovery legs target the operator's test wallet
with a zero-value poison claim — the exact parameters carried by the
uncommitted hub1 edit this row landed. Drifting back to the burn
address or a nonzero poison amount fails here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PLAY = Path(__file__).resolve().parents[2] / "scripts" / "stress" / "plays" / "18-wedge-replay.sh"


def test_wedge_replay_uses_operator_wallet_and_zero_poison() -> None:
    text = PLAY.read_text(encoding="utf-8")
    assert "addr=0x0bE3b183Eb31e545b1832fF16080358C6d04Ed5f" in text
    poison = next(ln for ln in text.splitlines() if "--type RECEIPT_CLAIM" in ln)
    assert "--amount 0 " in poison


def test_wedge_replay_parses() -> None:
    subprocess.run(["bash", "-n", str(PLAY)], check=True)
