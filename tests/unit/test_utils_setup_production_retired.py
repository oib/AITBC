"""#944: scripts/utils/setup_production.py is retired.

run() handed f-string commands to ``subprocess.run(shell=False)`` — every
call was a silent ``FileNotFoundError`` on a two-word "executable" — and it
wrote plain-text private-key files next to the keystores. The
workflow-driven copy (apps/blockchain-node/scripts/setup_production.py via
scripts/workflow/02_genesis_authority_setup.sh) is the only setup path.
Gone, and staying gone is pinned.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RETIRED = "scripts/utils/setup_production.py"


def test_utils_setup_production_is_gone():
    assert not (REPO / RETIRED).exists(), f"{RETIRED} is back"


def test_nothing_references_the_retired_copy():
    hits = []
    for p in (REPO / "scripts").rglob("*"):
        if not p.is_file() or p.suffix not in (".py", ".sh"):
            continue
        for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if "utils/setup_production" in line:
                hits.append(f"{p.relative_to(REPO)}:{i}")
    assert hits == [], f"dangling references: {hits}"
