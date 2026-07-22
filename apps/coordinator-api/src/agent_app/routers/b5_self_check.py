"""Self-check for B5 migration authority."""


def test_create_all_removed():
    # Minimal assertion: trading storage no longer calls create_all
    with open("/opt/aitbc/apps/trading/src/trading_service/storage.py") as f:
        content = f.read()
    assert "await conn.run_sync(SQLModel.metadata.create_all)" not in content
    print("B5 self-check: create_all removed from trading storage.")


if __name__ == "__main__":
    test_create_all_removed()
