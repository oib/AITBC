"""Property tests for ``aitbc_chain.rpc.utils.clamp_limit`` (#1057/#1622 form).

``clamp_limit`` is the shared bound every public list route funnels its
client-supplied ``limit`` through: ``None`` falls back to ``default``,
``0``/negatives clamp to 1 (never "unbounded"), and anything above
``maximum`` clamps down. The per-route tests pin representative values;
these properties pin the shape of the whole input space.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from aitbc_chain.rpc.utils import clamp_limit


@given(
    value=st.one_of(st.none(), st.integers(min_value=-(10**6), max_value=10**6)),
    default=st.integers(min_value=1, max_value=10_000),
    maximum=st.integers(min_value=1, max_value=10_000),
)
@settings(max_examples=300)
def test_clamp_limit_never_leaves_the_window(value, default, maximum):
    """A non-None limit always lands in [1, maximum]; None yields default."""
    result = clamp_limit(value, default, maximum)
    if value is None:
        assert result == default
    else:
        assert 1 <= result <= maximum
        assert isinstance(result, int)


@given(
    value=st.integers(min_value=1, max_value=10_000),
    maximum=st.integers(min_value=1, max_value=10_000),
)
@settings(max_examples=300)
def test_clamp_limit_is_identity_inside_the_window(value, maximum):
    """A limit already inside [1, maximum] passes through unchanged."""
    if value <= maximum:
        assert clamp_limit(value, default=1, maximum=maximum) == value


@given(
    value=st.integers(min_value=-(10**6), max_value=0),
    maximum=st.integers(min_value=1, max_value=10_000),
)
@settings(max_examples=300)
def test_clamp_limit_floors_at_one(value, maximum):
    """Zero and negative limits clamp to 1 — they can never mean unbounded."""
    assert clamp_limit(value, default=1, maximum=maximum) == 1


@given(
    value=st.integers(min_value=1, max_value=10**6),
    maximum=st.integers(min_value=1, max_value=10_000),
)
@settings(max_examples=300)
def test_clamp_limit_is_monotone(value, maximum):
    """clamp_limit is non-decreasing in the requested limit."""
    a = clamp_limit(value, default=1, maximum=maximum)
    b = clamp_limit(value + 1, default=1, maximum=maximum)
    assert a <= b
