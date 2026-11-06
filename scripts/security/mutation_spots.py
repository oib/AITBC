#!/usr/bin/env python3
"""Mutation spot-checks for the security-pin suite (#1213, layout: #1196 c16932).

Each registered spot applies a small, surgical revert of a security fix in
place, runs the pin that is supposed to catch it, and requires the pin to
FAIL. A pin that still passes means the regression coverage is decorative —
the nightly run reports it.

Safety contract:

* Mutates exactly one file at a time, restores original bytes in ``finally``
  and verifies the SHA-256 matches afterwards.
* Refuses to run if the ``old`` string is absent or ambiguous — a drifted
  source file is reported as SKIP, not silently patched around.
* Never runs against anything but the checkout this script lives in.

Run from anywhere inside the repo checkout::

    python3 scripts/security/mutation_spots.py            # all spots
    python3 scripts/security/mutation_spots.py client_ip  # substring filter

Exit 0 = every executed spot produced the expected pin failure (or SKIP).
Exit 1 = a pin passed under mutation (coverage hole) or infra error.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MutationSpot:
    name: str
    file: str  # repo-relative
    old: str
    new: str
    pin: str  # pytest target that must FAIL under the mutation
    why: str


SPOTS: tuple[MutationSpot, ...] = (
    MutationSpot(
        name="client_ip_leftmost_xff",
        file="apps/coordinator-api/src/coordinator_api/utils/security.py",
        old='last = forwarded.split(",")[-1].strip()',
        new='last = forwarded.split(",")[0].strip()',
        pin="tests/security/unit/test_client_ip_trust.py",
        why="#1177 — leftmost XFF is client-spoofable; reverts the trust fix",
    ),
    MutationSpot(
        name="gossip_unbounded_send",
        file="apps/blockchain-node/src/aitbc_chain/rpc/websocket.py",
        old="await asyncio.wait_for(websocket.send_json(payload), timeout=_GOSSIP_WS_OP_TIMEOUT)",
        new="await websocket.send_json(payload)",
        pin="apps/blockchain-node/tests/test_websocket.py::test_gossip_websocket_hung_send_still_releases_ip_count",
        why="#1165 — unbounded send_json wedges the handler + IP slot",
    ),
    MutationSpot(
        name="hop_by_hop_te_forwarded",
        file="apps/api-gateway/src/api_gateway/main.py",
        old='        "te",\n',
        new="",
        pin="tests/security/unit/test_gateway_hop_by_hop.py",
        why="#1192 — TE is RFC 7230 hop-by-hop; forwarding it caused the TE+CL conflict",
    ),
    MutationSpot(
        name="config_guard_selftest",
        file="examples/blockchain.env.example",
        old="CHAIN_ID=ait-testnet",
        new="CHAIN_ID=ait-testnet\nJWT_NO_EXPIRATION=1",
        pin="tests/security/config/test_repo_config_guards.py::test_no_repo_config_enables_jwt_no_expiration",
        why="self-check — proves the config guard actually scans env examples",
    ),
)


def _python() -> str:
    for candidate in (
        os.environ.get("PYTHON"),
        str(REPO_ROOT / "venv" / "bin" / "python"),
        sys.executable,
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return sys.executable


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_spot(spot: MutationSpot, python: str) -> str:
    """Returns PASS (pin failed as required), FAIL (pin passed = hole), or SKIP."""
    target = REPO_ROOT / spot.file
    original = target.read_bytes()
    text = original.decode()
    count = text.count(spot.old)
    if count != 1:
        return f"SKIP ({spot.file}: pattern occurs {count}x — source drifted, update the spot)"

    mutated = text.replace(spot.old, spot.new, 1).encode()
    target.write_bytes(mutated)
    try:
        proc = subprocess.run(
            [python, "-m", "pytest", spot.pin, "-x", "-q", "--no-header"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return "FAIL (pin timed out under mutation — inconclusive)"
    finally:
        target.write_bytes(original)
        if _sha(target.read_bytes()) != _sha(original):
            print(f"FATAL: failed to restore {spot.file}", file=sys.stderr)
            sys.exit(2)

    if proc.returncode == 0:
        tail = "\n".join(proc.stdout.splitlines()[-5:])
        return f"FAIL — pin passed under mutation ({spot.why})\n{tail}"
    return "PASS"


def main() -> int:
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    python = _python()
    print(f"mutation spots against {REPO_ROOT} (pytest via {python})")
    failures = 0
    ran = 0
    for spot in SPOTS:
        if flt and flt not in spot.name:
            continue
        ran += 1
        result = run_spot(spot, python)
        status = result.split(" ", 1)[0] if result.startswith(("PASS", "FAIL", "SKIP")) else "FAIL"
        print(f"  [{status:4}] {spot.name}: {result}")
        if status == "FAIL":
            failures += 1
    if ran == 0:
        print(f"  no spots matched filter {flt!r}")
        return 2
    print(f"{ran - failures} pass, {failures} fail")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
