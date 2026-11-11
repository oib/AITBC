"""#1717 pins: keyset (cursor) pagination on the explorer list endpoints.

OFFSET pages skip/dup rows when the table mutates between fetches; the
``cursor``/``next_cursor`` pair pages by the ORDER BY key instead. These
tests prove: full coverage with no skips or duplicates, immunity to a row
inserted mid-pagination (the exact OFFSET failure mode), NULL/edge cursor
handling, and 400s on malformed cursors.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chain_db_fixture import create_chain_db, insert_blocks, patch_chain_db
from main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def chain_db(tmp_path, monkeypatch):
    db_file = create_chain_db(tmp_path)
    patch_chain_db(monkeypatch, db_file)
    return db_file


def _insert_block(db_file: Path, height: int, *, with_tx: bool = True) -> None:
    conn = sqlite3.connect(db_file)
    conn.execute(
        "INSERT INTO block VALUES (?,?,?,?,?,?)",
        (height, f"0x{height:064x}", "0xproposer", f"2026-02-01 00:{height // 60:02d}:{height % 60:02d}", 1, "0xroot"),
    )
    if with_tx:
        conn.execute(
            """INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"0x{height:064x}",
                "0xsender",
                "0xrecipient",
                "{}",
                height,
                f"2026-02-01 00:{height // 60:02d}:{height % 60:02d}",
                "TRANSFER",
                "confirmed",
                100,
                1,
                0,
            ),
        )
    conn.commit()
    conn.close()


def _page_all(client, path: str, limit: int, extra: dict | None = None) -> tuple[list, list]:
    """Follow next_cursor until exhausted; return (items, cursors_seen)."""
    items: list = []
    cursors: list = []
    cursor = None
    for _ in range(50):  # bound the loop — a wedged cursor fails the test
        params: dict = {"limit": limit, **(extra or {})}
        if cursor is not None:
            params["cursor"] = cursor
        resp = client.get(path, params=params)
        assert resp.status_code == 200
        body = resp.json()
        key = "blocks" if "blocks" in body else "transactions"
        items.extend(body[key])
        cursor = body.get("next_cursor")
        if cursor is not None:
            cursors.append(cursor)
        if cursor is None:
            break
    return items, cursors


# --- /api/blocks/latest -----------------------------------------------------


def test_latest_blocks_cursor_covers_all_no_dups(client, chain_db):
    insert_blocks(chain_db, 7)
    blocks, _ = _page_all(client, "/api/blocks/latest", 3)
    heights = [b["height"] for b in blocks]
    assert heights == [7, 6, 5, 4, 3, 2, 1]


def test_latest_blocks_cursor_survives_mid_pagination_insert(client, chain_db):
    """The OFFSET failure mode: a new tip between page fetches must not
    shift the window — the cursor resumes strictly below the last height."""
    insert_blocks(chain_db, 6)
    resp = client.get("/api/blocks/latest", params={"limit": 3})
    assert [b["height"] for b in resp.json()["blocks"]] == [6, 5, 4]
    cursor = resp.json()["next_cursor"]
    assert cursor == "4"

    _insert_block(chain_db, 7)  # new tip arrives between pages
    resp2 = client.get("/api/blocks/latest", params={"limit": 3, "cursor": cursor})
    assert [b["height"] for b in resp2.json()["blocks"]] == [3, 2, 1]
    assert resp2.json()["next_cursor"] is None


def test_latest_blocks_next_cursor_null_on_exact_fit(client, chain_db):
    insert_blocks(chain_db, 4)
    resp = client.get("/api/blocks/latest", params={"limit": 4})
    assert len(resp.json()["blocks"]) == 4
    assert resp.json()["next_cursor"] is None


def test_latest_blocks_offset_still_works(client, chain_db):
    insert_blocks(chain_db, 5)
    resp = client.get("/api/blocks/latest", params={"limit": 2, "offset": 2})
    assert [b["height"] for b in resp.json()["blocks"]] == [3, 2]


@pytest.mark.parametrize("bad", ["abc", "-1", "1.5", "0x10", "9" * 25])
def test_latest_blocks_bad_cursor_400(client, chain_db, bad):
    insert_blocks(chain_db, 3)
    resp = client.get("/api/blocks/latest", params={"cursor": bad})
    assert resp.status_code == 400


# --- /api/blocks/non-empty --------------------------------------------------


def test_non_empty_blocks_cursor_covers_all(client, chain_db):
    insert_blocks(chain_db, 6, with_txs=True)
    blocks, _ = _page_all(client, "/api/blocks/non-empty", 2)
    heights = [b["height"] for b in blocks]
    assert heights == [6, 5, 4, 3, 2, 1]


def test_non_empty_blocks_cursor_survives_insert(client, chain_db):
    insert_blocks(chain_db, 5, with_txs=True)
    resp = client.get("/api/blocks/non-empty", params={"limit": 2})
    assert [b["height"] for b in resp.json()["blocks"]] == [5, 4]
    cursor = resp.json()["next_cursor"]
    assert cursor == "4"

    _insert_block(chain_db, 6)  # with_tx=True default
    resp2 = client.get("/api/blocks/non-empty", params={"limit": 2, "cursor": cursor})
    assert [b["height"] for b in resp2.json()["blocks"]] == [3, 2]


def test_non_empty_blocks_bad_cursor_400(client, chain_db):
    insert_blocks(chain_db, 3, with_txs=True)
    resp = client.get("/api/blocks/non-empty", params={"cursor": "not-a-height"})
    assert resp.status_code == 400


# --- /api/transactions/search ----------------------------------------------


def test_tx_search_cursor_covers_all_no_dups(client, chain_db):
    insert_blocks(chain_db, 7, with_txs=True)
    txs, _ = _page_all(client, "/api/transactions/search", 3, {"address": "0xsender"})
    hashes = [t["tx_hash"] for t in txs]
    assert len(hashes) == 7
    assert len(set(hashes)) == 7


def test_tx_search_cursor_survives_mid_pagination_insert(client, chain_db):
    insert_blocks(chain_db, 5, with_txs=True)
    resp = client.get("/api/transactions/search", params={"address": "0xsender", "limit": 2})
    page1 = resp.json()["transactions"]
    assert [t["tx_hash"] for t in page1] == ["0x" + f"{5:064x}", "0x" + f"{4:064x}"]
    cursor = resp.json()["next_cursor"]
    assert cursor is not None

    _insert_block(chain_db, 6)  # newer tx lands between pages
    resp2 = client.get(
        "/api/transactions/search",
        params={"address": "0xsender", "limit": 2, "cursor": cursor},
    )
    page2 = resp2.json()["transactions"]
    # OFFSET would have re-shown tx5/tx4 shifted by the insert; keyset resumes
    # strictly after the cursor row: tx3, tx2.
    assert [t["tx_hash"] for t in page2] == ["0x" + f"{3:064x}", "0x" + f"{2:064x}"]


def test_tx_search_cursor_null_at_end(client, chain_db):
    insert_blocks(chain_db, 3, with_txs=True)
    resp = client.get("/api/transactions/search", params={"address": "0xsender", "limit": 5})
    assert len(resp.json()["transactions"]) == 3
    assert resp.json()["next_cursor"] is None


# "x|y" is well-formed (two non-empty parts) — it just matches nothing, so
# it is not in the reject list.
@pytest.mark.parametrize("bad", ["abc", "a|b|c", "|onlyhash", "ts|", "x" * 300 + "|h"])
def test_tx_search_bad_cursor_400(client, chain_db, bad):
    insert_blocks(chain_db, 2, with_txs=True)
    resp = client.get("/api/transactions/search", params={"address": "0xsender", "cursor": bad})
    assert resp.status_code == 400
