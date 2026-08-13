#!/usr/bin/env python3
"""Inventory stale markers in the AITBC docs/ tree.

Outputs JSON to stdout with two sections:
- by_directory
- by_file

Markers include:
- old ports not in the current single-source-of-truth set
- deleted feature_flags artifacts
- old service/app names
- fictional CLI commands
- designed/placeholder/aspirational language
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path("/opt/aitbc")
DOCS = REPO / "docs"

PATTERNS = {
    "old_port": re.compile(r"\b(8000|8001|8003|8006|8015|9001|8103)\b"),
    "deleted_feature_flags": re.compile(r"feature_flags\.json|aitbc/feature_flags\.py"),
    "old_app_name": re.compile(
        r"(?:marketplace-service|gpu-service|trading-service|plugin-service|coordinator-api-service|agent-coordinator-service)\b",
        re.I,
    ),
    "fictional_cli": re.compile(
        r"aitbc (?:coordinator-api|agent-coordinator|gpu-service|marketplace-service|trading-service|services) (?:start|stop|restart|status)"
    ),
    "designed_phrase": re.compile(
        r"\b(designed|planned|not implemented|placeholder|mock|fake|simulated|aspirational)\b",
        re.I,
    ),
}

# Dirs that are historical and intentionally allowed to keep old markers.
EXCLUDED_PREFIXES = ("docs/releases/", "docs/archive/", "docs/audit/")


def is_excluded(rel_path: Path) -> bool:
    rel_str = str(rel_path).replace("\\", "/")
    return any(rel_str.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def main() -> int:
    dir_counts: dict[Path, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    file_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for p in sorted(DOCS.rglob("*.md")):
        rel = p.relative_to(REPO)
        if is_excluded(rel):
            continue
        text = p.read_text(errors="ignore")
        for label, pat in PATTERNS.items():
            count = len(pat.findall(text))
            if count:
                dir_counts[p.parent.relative_to(DOCS)][label] += count
                file_counts[str(rel)][label] += count

    result = {
        "total_files_with_markers": len(file_counts),
        "total_marker_hits": sum(sum(v.values()) for v in file_counts.values()),
        "by_directory": [
            {
                "directory": f"docs/{d}",
                "total": sum(dir_counts[d].values()),
                "counts": dict(dir_counts[d]),
            }
            for d in sorted(dir_counts, key=lambda x: sum(dir_counts[x].values()), reverse=True)
        ],
        "by_file": [
            {
                "file": f,
                "total": sum(file_counts[f].values()),
                "counts": dict(file_counts[f]),
            }
            for f in sorted(file_counts, key=lambda x: sum(file_counts[x].values()), reverse=True)
        ],
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
