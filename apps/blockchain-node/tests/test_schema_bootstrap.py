"""What `init_db` does to a database that is not brand new (V23-77).

Node startup calls `chain_metadata.create_all` and then `_migrate_existing_columns`, and
neither had a test. Both cases below are real: the hub's chain database predates several
columns that shipped later, and `create_all` used to be wrapped in an `except Exception`
that re-raised only when the message did not contain "already exists".
"""

from __future__ import annotations

import pytest
from aitbc_chain.database import _default_clause, _migrate_existing_columns
from aitbc_chain.metadata import chain_metadata
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    yield engine
    engine.dispose()


def _bootstrap(engine) -> None:
    """The startup path, in order."""
    chain_metadata.create_all(engine)
    _migrate_existing_columns(engine)


def test_create_all_does_not_raise_on_an_existing_schema(engine):
    """Startup is idempotent, so `create_all` needs no exception handling.

    `create_all` defaults to `checkfirst=True`: it skips what is already there rather than
    failing on it. `init_db` nevertheless swallowed anything whose message contained "already
    exists" — which meant a genuinely broken schema was indistinguishable from a second
    start. Three runs, no handler.
    """
    for _ in range(3):
        _bootstrap(engine)

    assert set(inspect(engine).get_table_names()) == set(chain_metadata.tables)


def test_missing_column_is_added_to_a_reserved_word_table(engine):
    """A column added to `transaction` — which is a SQLite keyword.

    `_migrate_existing_columns` interpolated identifiers into the DDL unquoted, so this
    raised `near "transaction": syntax error` and took node startup down with it. Any chain
    database old enough to be missing a column on this table hit it, and `transaction` is the
    table most likely to gain one. It is the only identifier in the whole chain schema that
    needs quoting, which is why nothing else ever tripped over it.
    """
    _bootstrap(engine)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "transaction" DROP COLUMN nonce'))
    assert "nonce" not in {c["name"] for c in inspect(engine).get_columns("transaction")}

    _migrate_existing_columns(engine)

    assert "nonce" in {c["name"] for c in inspect(engine).get_columns("transaction")}


def test_every_back_fillable_column_survives_a_bootstrap_over_a_partial_schema(engine):
    """Drop every column the function claims it can restore, from every table, then bootstrap.

    The narrow version of this test would only cover `transaction`. This covers the claim the
    function actually makes — that it reconciles columns across the whole metadata — against a
    database in the state the hub's was in: tables present, columns behind the models.

    "Back-fillable" means nullable, or carrying a default the dialect can render; those are the
    columns an `ALTER TABLE ... ADD COLUMN` can legally add to a table with rows in it. The ones
    that are neither are the subject of the test below.

    The staging drops what SQLite will let it drop and skips the rest, rather than trying to
    predict which those are: primary keys, indexed columns and anything named in a foreign key
    are all refused, by rules that would have to be restated here to filter for them. As the
    schema stands that removes 103 columns across 20 of the 21 tables.
    """
    _bootstrap(engine)
    dropped: list[tuple[str, str]] = []
    for table in chain_metadata.sorted_tables:
        for col in table.columns:
            if not col.nullable and not _default_clause(col, engine):
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" DROP COLUMN "{col.name}"'))
            except OperationalError:
                continue  # SQLite will not remove this one; it cannot be staged
            dropped.append((table.name, col.name))

    # Guards against this passing vacuously if the models are refactored out from under it.
    assert len(dropped) > 80, f"expected most of the schema's back-fillable columns, staged {len(dropped)}"
    assert len({t for t, _ in dropped}) > 15, "expected coverage across the schema, not one table"

    _migrate_existing_columns(engine)

    inspector = inspect(engine)
    missing = [f"{t}.{c}" for t, c in dropped if c not in {x["name"] for x in inspector.get_columns(t)}]
    assert not missing, f"not restored: {missing}"


def test_a_not_null_column_with_no_default_names_itself_instead_of_guessing(engine):
    """The case that cannot be back-filled is refused, and the message says which column.

    This used to emit `DEFAULT ''` for any NOT NULL column it could not find a default for, on
    a comment about text columns. 91 columns here are in that state and only 68 of them are
    textual: the branch wrote `escrow.amount INTEGER DEFAULT ''`, `block.height INTEGER
    DEFAULT ''`, `transaction.payload JSON DEFAULT ''`, `governance_proposal.voting_ends
    DATETIME DEFAULT ''`. None of that raises. It writes a schema whose declared default is
    nonsense for the column's type, and the next insert that omits the column stores it.

    `escrow.amount` is the one staged here because it is the clearest: an escrow balance is
    not an empty string, and a node that starts with that schema is one bad insert away from a
    row it cannot read back.
    """
    _bootstrap(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE escrow DROP COLUMN amount"))

    with pytest.raises(RuntimeError, match=r"escrow\.amount is NOT NULL with no default"):
        _migrate_existing_columns(engine)


def test_reserved_word_is_the_only_identifier_needing_quotes():
    """Pins why the bug was invisible, and fails loudly if that stops being true.

    One identifier out of 164 in this schema is a SQL keyword. If someone adds a table or
    column named `order`, `group`, `index` or similar, this test names it — and the quoting
    in `_migrate_existing_columns` is what keeps that from becoming a startup crash.
    """
    quote = create_engine("sqlite://").dialect.identifier_preparer.quote
    needs_quoting = {
        name
        for table in chain_metadata.sorted_tables
        for name in (table.name, *(c.name for c in table.columns))
        if quote(name) != name
    }
    assert needs_quoting == {"transaction"}
