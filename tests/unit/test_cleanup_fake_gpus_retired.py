"""#947: scripts/utils/cleanup_fake_gpus.py is retired.

It DELETEs /v1/market/gpu/<id> with no Authorization against a hard-coded
id list — the registry sweep tooling (scripts/ops/gpu-registry-sweep.py)
covers stale offers. Gone, and staying gone is pinned.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RETIRED = "scripts/utils/cleanup_fake_gpus.py"


def test_cleanup_fake_gpus_is_gone():
    assert not (REPO / RETIRED).exists(), f"{RETIRED} is back"


def test_nothing_references_the_retired_cleanup():
    hits = []
    for p in (REPO / "scripts").rglob("*"):
        if not p.is_file() or p.suffix not in (".py", ".sh"):
            continue
        for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if "cleanup_fake_gpus" in line:
                hits.append(f"{p.relative_to(REPO)}:{i}")
    assert hits == [], f"dangling references: {hits}"
