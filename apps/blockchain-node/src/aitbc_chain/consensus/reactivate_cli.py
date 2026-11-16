"""Operator re-activation of a locally deactivated validator (#2158).

Run on the node's host with the node service STOPPED (a running node keeps
its own in-memory validator set and would overwrite the change on its next
``save_state``)::

    /opt/aitbc/venv/bin/python -m aitbc_chain.consensus.reactivate_cli \\
        --chain bc-2 --address 0x... --reason "false-positive, see #NNNN" --confirm

Legacy (node-local) regime only; refuses while chain slashing is armed. The
change is local to this node: repeat on every host that deactivated the
validator, then start the services one at a time.
"""

from __future__ import annotations

import argparse
import sys
from typing import TextIO

from .multi_validator_poa import get_consensus


def _say(message: str, stream: TextIO | None = None) -> None:
    (stream or sys.stdout).write(message + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--address", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--confirm", action="store_true", help="actually write; without it only report")
    args = parser.parse_args(argv)

    consensus = get_consensus(args.chain)
    consensus.load_state()
    health = consensus.quorum_health()
    _say(f"before: active={health['active']} configured={health['configured']} required={health['required']}")
    if not args.confirm:
        _say("dry run: pass --confirm to re-activate")
        return 0
    try:
        changed = consensus.reactivate_validator(args.address, args.reason)
    except ValueError as exc:
        _say(f"refused: {exc}", sys.stderr)
        return 2
    if not changed:
        _say("no change: validator unknown or already active")
        return 1
    health = consensus.quorum_health()
    _say(f"after: active={health['active']} configured={health['configured']} required={health['required']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
