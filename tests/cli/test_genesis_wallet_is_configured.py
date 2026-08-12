"""The genesis wallet is configuration, and it is not the block proposer.

Two addresses were being conflated across this repo and its deployments:

* ``ait1db5247d0…`` — the wallet holding the genesis allocation. AIT transfers are sent
  *from* it, and it is funded (3.6e12 milli-AIT on the hub at the time of writing).
* ``ait1fe2d63fe…`` — the proposer identity blocks are signed *as*. It holds nothing; the
  hub RPC returns "Account not found" for it.

``exchange.py`` hardcoded the first one mid-function while reading every other endpoint and
identifier from config, and a deployed ``blockchain.env`` set ``GENESIS_WALLET_ADDRESS`` to
the second. Neither fails loudly: the hardcode disagrees silently with what bridge-monitor
and blockchain-node escrow read from the environment, and the misconfigured env produces
transfers from an account that does not exist while block production looks healthy.

These tests pin the shape of the fix rather than the address itself — the value is allowed
to change per deployment, which is the entire point.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from aitbc_cli.config import CLIConfig

CLI_ROOT = Path(__file__).resolve().parents[2] / "cli"

# ait1/aitbc1 followed by exactly 40 hex characters, quoted — a chain address written as a
# literal. The 40-hex bound is the same one `canonical_address` uses.
ADDRESS_LITERAL = re.compile(r"""['"](?:ait1|aitbc1)[0-9a-f]{40}['"]""")


def test_the_genesis_wallet_comes_from_config() -> None:
    assert CLIConfig().genesis_wallet_address


def test_the_environment_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployments set GENESIS_WALLET_ADDRESS; the CLI must agree with bridge-monitor."""
    monkeypatch.setenv("GENESIS_WALLET_ADDRESS", "ait1" + "ab" * 20)
    assert CLIConfig().genesis_wallet_address == "ait1" + "ab" * 20


def test_no_command_module_hardcodes_a_chain_address() -> None:
    """config.py may carry the default. A command module carrying one is the old bug."""
    offenders = []
    files = subprocess.run(
        ["git", "ls-files", "--", "cli/**/*.py"],
        cwd=CLI_ROOT.parent,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    for name in files:
        path = CLI_ROOT.parent / name
        if path.name == "config.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ADDRESS_LITERAL.search(line):
                offenders.append(f"{name}:{number}: {line.strip()}")

    assert not offenders, "hardcoded chain address outside config.py:\n" + "\n".join(offenders)
