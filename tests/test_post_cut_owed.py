"""The post-cut owed-items sheet may only name paths and units that the
host inventory knows — a name that exists nowhere else is a typo that
would slip the deletion reads.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SHEET = REPO / "docs" / "deployment" / "bc2-post-cut-owed.md"
INVENTORY = REPO / "docs" / "deployment" / "bc2-host-inventory.md"

PATTERNS = (
    r"aitbc-[\w-]+\.(?:service|timer)",  # unit names with suffix
    r"`aitbc-[a-z][\w-]*`",  # bare aitbc-* unit names in code spans
    r"[\w.-]+\.db",  # database files
    r"/var/lib/aitbc/[\w./<>-]+",  # absolute paths (may carry <…> templates)
    r"\.pre-reset-<YYYY-MM-DD>",
)


def _named_tokens() -> set[str]:
    text = SHEET.read_text()
    tokens: set[str] = set()
    for pat in PATTERNS:
        tokens.update(re.findall(pat, text))
    tokens = {t.strip("`") for t in tokens}
    # a token that is only a path suffix of another token is redundant
    return {t for t in tokens if not any(t != o and t in o for o in tokens)}


def test_every_named_path_or_unit_is_in_the_inventory():
    inv = INVENTORY.read_text()
    missing = [t for t in sorted(_named_tokens()) if t not in inv]
    assert not missing, f"sheet names not found in bc2-host-inventory.md: {missing}"


def test_sheet_has_the_gate_sections_in_order():
    text = SHEET.read_text()
    heads = [
        "## 1. Cut-day items",
        "## 2. Soak-end gate",
        "## 3. F4",
        "## 4. Per-item deletions",
        "## 5. Register-row pointers",
    ]
    positions = [text.index(h) for h in heads]
    assert positions == sorted(positions)


def test_f4_amounts_are_not_invented():
    f4 = SHEET.read_text().split("## 3. F4")[1].split("## 4.")[0]
    assert f4.count("operator card, not decided") == 2
    assert not re.search(r"\b\d+(\.\d+)?\s*(AIT|units)\b", f4)
