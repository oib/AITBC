"""#946: scripts/utils/run_production_node.py is retired.

The launcher hard-coded ``ait-mainnet``, ``/var/lib/aitbc/data`` and port
8006 — wrong for every node it ran on. The systemd units start the node
and own chain/data/port config via /etc/aitbc env files. Gone, and
staying gone is pinned.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RETIRED = "scripts/utils/run_production_node.py"


def test_run_production_node_is_gone():
    assert not (REPO / RETIRED).exists(), f"{RETIRED} is back"


def test_nothing_references_the_retired_launcher():
    hits = []
    for p in (REPO / "scripts").rglob("*"):
        if not p.is_file() or p.suffix not in (".py", ".sh"):
            continue
        for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if "run_production_node" in line:
                hits.append(f"{p.relative_to(REPO)}:{i}")
    assert hits == [], f"dangling references: {hits}"
