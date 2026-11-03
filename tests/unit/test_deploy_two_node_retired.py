"""#889: the two-nodes-on-one-host scripts are retired.

deploy-first-node.sh, deploy-second-node.sh and setup-gossip-relay.sh
bound two RPC units to the same port, cloned a live tree including its
database, and wrote a .env the node never read. setup.sh covers node
setup; these are gone, and staying gone is pinned.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "scripts" / "deployment" / "deploy"


def test_two_node_scripts_are_gone():
    for name in ("deploy-first-node.sh", "deploy-second-node.sh", "setup-gossip-relay.sh"):
        assert not (DEPLOY / name).exists(), f"{name} is back"


def test_nothing_references_the_retired_scripts():
    hits = []
    for p in DEPLOY.rglob("*.sh"):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            for name in ("deploy-first-node", "deploy-second-node", "setup-gossip-relay"):
                if name in line:
                    hits.append(f"{p.name}:{i}")
    assert hits == [], f"dangling references: {hits}"
