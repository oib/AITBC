"""Test-only helpers shared across suites (PG-TARGET-1 stream 3).

Nothing in this package is imported by production code; it exists so that
several app test suites can spin up the same disposable PostgreSQL cluster
instead of each growing its own copy.
"""
