from __future__ import annotations

from pathlib import Path

from app.ledger_mock import SQLiteLedgerAdapter


def test_upsert_and_get_wallet(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    adapter = SQLiteLedgerAdapter(db_path)

    adapter.upsert_wallet("wallet-1", "pubkey", {"label": "primary"})

    record = adapter.get_wallet("wallet-1")
    assert record is not None
    assert record.wallet_id == "wallet-1"
    assert record.public_key == "pubkey"
    assert record.metadata["label"] == "primary"

    # Update metadata and ensure persistence
    adapter.upsert_wallet("wallet-1", "pubkey", {"label": "updated"})
    updated = adapter.get_wallet("wallet-1")
    assert updated is not None
    assert updated.metadata["label"] == "updated"


def test_event_ordering(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    adapter = SQLiteLedgerAdapter(db_path)

    adapter.upsert_wallet("wallet-1", "pubkey", {})
    adapter.record_event("wallet-1", "created", {"step": 1})
    adapter.record_event("wallet-1", "unlock", {"step": 2})
    adapter.record_event("wallet-1", "sign", {"step": 3})

    events = list(adapter.list_events("wallet-1"))
    assert [event.event_type for event in events] == ["created", "unlock", "sign"]
    assert [event.payload["step"] for event in events] == [1, 2, 3]
