"""ALERT-LABELS-1: one target spelling per scrape endpoint.

`localhost:PORT` and `127.0.0.1:PORT` are the same target scraped
twice — duplicate `up`/ServiceDown series per host.
"""

import re
from pathlib import Path

CFG = Path(__file__).parents[1] / "scripts/monitoring/prometheus.yml"


def _targets() -> list[str]:
    return re.findall(r"targets?:\s*\[?'([^']+)'", CFG.read_text())


def test_no_localhost_spelling():
    assert not [t for t in _targets() if t.startswith("localhost")]


def test_no_duplicate_target():
    """Same host:port must not appear under two spellings."""
    seen: dict[str, int] = {}
    for t in _targets():
        norm = t.replace("localhost", "127.0.0.1")
        seen[norm] = seen.get(norm, 0) + 1
    assert not [k for k, v in seen.items() if v > 1]
