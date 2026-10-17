"""Pin the deposit-lookup fetch URLs in ``website/exchange.js``.

WEB-PAGES-1 regression guard: ``lookupDeposit`` has two branches —
- 0x + 64 hex (tx hash)      -> GET /v1/bridge/deposit/<hash>
- 0x + 40 hex (AIT address)  -> GET /v1/bridge/deposit/by-recipient/<addr>

The /v1/bridge/deposit/<x> endpoint is the tx-hash detail endpoint; for an
address it answers 404, which the UI renders as "No deposit found" — a
wrong answer that reads as an empty one. The by-recipient index is the
only address lookup.
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / "website" / "exchange.js").read_text(encoding="utf-8")


def _branch(start_marker: str) -> str:
    """Return the source slice of the lookupDeposit branch starting at marker."""
    start = SRC.index(start_marker)
    # The tx-hash (66) branch is followed by the address (42) branch; the
    # address branch ends at the final '} else {' (invalid input).
    end = SRC.index("} else {", start)
    return SRC[start:end]


class TestExchangeFetchUrls(unittest.TestCase):
    def test_tx_hash_branch_queries_deposit_detail(self) -> None:
        branch = _branch("input.length === 66")
        self.assertIn("fetch(`/v1/bridge/deposit/${encodeURIComponent(input)}`)", branch)
        self.assertNotIn("by-recipient", branch)

    def test_address_branch_queries_by_recipient(self) -> None:
        branch = _branch("input.length === 42")
        self.assertIn("fetch(`/v1/bridge/deposit/by-recipient/${encodeURIComponent(input)}`)", branch)
        # The tx-hash detail endpoint 404s for addresses — it must not be
        # used in this branch.
        self.assertNotIn("fetch(`/v1/bridge/deposit/${encodeURIComponent(input)}`)", branch)

    def test_stale_note_renders_from_recorded_good_text(self) -> None:
        # markStale must write from a recorded good value, not append to
        # textContent — otherwise each failed poll adds another "(stale …)".
        m = re.search(r"function markStale\([^)]*\)\s*\{(?P<body>.*?)\n\}", SRC, re.S)
        self.assertIsNotNone(m, "markStale not found")
        self.assertIn("dataset.lastGood", m.group("body"), "markStale must render from el.dataset.lastGood")
        self.assertNotIn(
            "${el.textContent} (stale", m.group("body"), "markStale must not append the stale note to its own output"
        )


if __name__ == "__main__":
    unittest.main()
