"""Property tests for ``bridge_monitor.storage`` tx-hash key helpers.

``canon_tx_hash`` normalizes ``0x``-prefixed/lowercase hex spellings while
passing non-hex synthetic ids (``manual-…`` rows) through unchanged;
``_tx_hash_keys`` derives the stored-spelling pair every ``tx_hash``
lookup must cover (#652/#668). The WHERE clause compares ``lower(tx_hash)``,
so both returned keys must already be lowercase or the UPDATE silently
misses its own row.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from bridge_monitor.storage import _HEX_CHARS, _tx_hash_keys, canon_tx_hash

_HEX_STRATEGY = st.text(alphabet="0123456789abcdefABCDEF", min_size=1, max_size=64)
_ANY_STRATEGY = st.text(min_size=1, max_size=80).filter(lambda s: s.strip() != "")


@given(raw=_ANY_STRATEGY)
@settings(max_examples=300)
def test_canon_tx_hash_output_shape(raw):
    """Output is either the input verbatim, or ``0x`` + lowercase hex."""
    canon = canon_tx_hash(raw)
    if canon == raw:
        return  # passthrough of a non-hex synthetic id
    assert canon.startswith("0x")
    body = canon[2:]
    assert body == body.lower()
    assert all(c in _HEX_CHARS for c in body)


@given(raw=_ANY_STRATEGY)
@settings(max_examples=300)
def test_canon_tx_hash_is_idempotent(raw):
    """Normalizing an already-canonical value changes nothing."""
    once = canon_tx_hash(raw)
    assert canon_tx_hash(once) == once


@given(raw=_HEX_STRATEGY)
@settings(max_examples=300)
def test_canon_tx_hash_lowercases_hex_bodies(raw):
    """Any all-hex body canonicalizes to ``0x`` + lowercase, with or without
    the prefix and in either case."""
    for variant in (raw, "0x" + raw, "0X" + raw.upper(), raw.upper()):
        canon = canon_tx_hash(variant)
        assert canon == "0x" + raw.lower()


@given(raw=_ANY_STRATEGY)
@settings(max_examples=300)
def test_tx_hash_keys_are_lowercase_and_cover_canonical(raw):
    """Both lookup keys are lowercase and the first is the canonical form —
    the WHERE clause compares lower(tx_hash), so a mixed-case key would
    orphan the row's own updates."""
    canon_key, bare_key = _tx_hash_keys(raw)
    assert canon_key == canon_key.lower()
    assert bare_key == bare_key.lower()
    assert canon_key == canon_tx_hash(raw).lower()
    if canon_key.startswith("0x"):
        assert bare_key == canon_key[2:]
    else:
        assert bare_key == canon_key


@given(raw=_HEX_STRATEGY)
@settings(max_examples=200)
def test_tx_hash_keys_prefixed_and_bare_spellings(raw):
    """For hex input the pair is exactly {0x-lower, bare-lower} — the two
    spellings legacy and canonical rows were written under."""
    canon_key, bare_key = _tx_hash_keys("0x" + raw)
    assert canon_key == "0x" + raw.lower()
    assert bare_key == raw.lower()
