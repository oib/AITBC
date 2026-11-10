"""Property-based tests for pure helpers hardened in the recent sweep waves.

Three targets, all pure functions with no I/O:

* ``poolhub.app.routers.parameters._validate_parameter_value`` (#1500) —
  governance parameter type/bounds gate.
* ``trading_service.services.gossip_client._decode_payload`` — Redis
  pub/sub payload decoder (plain JSON, raw passthrough, ``GZ:`` gzip).
* ``coordinator_api.contexts.payments.acceptance.window_seconds_for`` —
  acceptance-window clamp to the operator ceiling.

hypothesis is already a dev dependency (pyproject.toml / requirements-dev.txt).
"""

import base64
import json

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from aitbc.network import compress_json
from coordinator_api.contexts.payments import acceptance
from poolhub.app.routers.parameters import GOVERNANCE_PARAMETERS, _validate_parameter_value
from trading_service.services.gossip_client import _decode_payload


# A JSON-shaped value strategy: ints, bools, strings, null, lists, dicts.
# Floats are excluded on purpose -- json round-trips of finite floats are exact,
# but integral floats and -0.0 make equality assertions noisy for no coverage gain.
_json_value = st.recursive(
    st.one_of(
        st.integers(min_value=-(2**31), max_value=2**31 - 1),
        st.booleans(),
        st.none(),
        st.text(max_size=40),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=10), children, max_size=5),
    ),
    max_leaves=30,
)


def _utf8_encodable(text: str) -> bool:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


# Arbitrary Python values for the type-gate property.
_any_value = st.one_of(
    st.integers(min_value=-(2**63), max_value=2**63 - 1),
    st.booleans(),
    st.none(),
    st.text(max_size=40),
    st.floats(allow_nan=False, allow_infinity=False),
    st.lists(st.integers(), max_size=4),
    st.dictionaries(st.text(max_size=8), st.integers(), max_size=4),
)


class TestValidateParameterValue:
    """_validate_parameter_value accepts iff the value matches the declared type."""

    @given(parameter_name=st.sampled_from(sorted(GOVERNANCE_PARAMETERS)), value=_any_value)
    @settings(max_examples=200, deadline=None)
    def test_accepts_exactly_matching_values(self, parameter_name, value):
        expected = GOVERNANCE_PARAMETERS[parameter_name]
        value_ok = isinstance(value, expected)
        if expected is int and (isinstance(value, bool) or (isinstance(value, int) and value < 0)):
            value_ok = False

        if value_ok:
            # Must not raise.
            _validate_parameter_value(parameter_name, value)
        else:
            with pytest.raises(HTTPException) as exc_info:
                _validate_parameter_value(parameter_name, value)
            assert exc_info.value.status_code == 400
            assert parameter_name in exc_info.value.detail

    @given(value=st.integers(min_value=0, max_value=2**31))
    @settings(max_examples=50, deadline=None)
    def test_max_concurrent_accepts_nonnegative_ints(self, value):
        _validate_parameter_value("max_concurrent", value)

    @given(value=st.one_of(st.integers(max_value=-1), st.just(True), st.just(False)))
    @settings(max_examples=50, deadline=None)
    def test_max_concurrent_rejects_negative_and_bool(self, value):
        with pytest.raises(HTTPException) as exc_info:
            _validate_parameter_value("max_concurrent", value)
        assert exc_info.value.status_code == 400

    @given(value=st.booleans())
    @settings(max_examples=50, deadline=None)
    def test_enabled_accepts_bools(self, value):
        _validate_parameter_value("enabled", value)

    @given(value=st.one_of(st.integers(), st.text(), st.lists(st.integers()), st.none()))
    @settings(max_examples=50, deadline=None)
    def test_enabled_rejects_non_bools(self, value):
        # bool is not int here: `enabled` expects bool, so ints must be rejected.
        with pytest.raises(HTTPException) as exc_info:
            _validate_parameter_value("enabled", value)
        assert exc_info.value.status_code == 400


class TestDecodePayload:
    """_decode_payload round-trips the encodings the gossip broker emits."""

    @given(obj=_json_value)
    @settings(max_examples=100, deadline=None)
    def test_plain_json_round_trip(self, obj):
        encoded = json.dumps(obj)
        assert _decode_payload(encoded) == obj

    @given(obj=_json_value)
    @settings(max_examples=100, deadline=None)
    def test_gz_compressed_round_trip(self, obj):
        compressed = compress_json(obj)
        encoded = "GZ:" + base64.b64encode(compressed).decode("ascii")
        assert _decode_payload(encoded) == obj

    @given(obj=_json_value)
    @settings(max_examples=50, deadline=None)
    def test_bytes_input_matches_str_input(self, obj):
        encoded = json.dumps(obj)
        assert _decode_payload(encoded.encode("utf-8")) == _decode_payload(encoded)

    @given(text=st.text(min_size=1, max_size=200).filter(_utf8_encodable))
    @settings(max_examples=100, deadline=None)
    def test_arbitrary_utf8_bytes_never_raise(self, text):
        # _decode_payload decodes bytes as UTF-8 before anything else, so the
        # contract under test is "valid-UTF-8 bytes never crash the decoder".
        # The result may legitimately be None — the text "null" is valid JSON
        # and json.loads("null") is None — so only the no-raise contract holds.
        _decode_payload(text.encode("utf-8"))

    @given(text=st.text(min_size=1, max_size=60).filter(lambda s: not s.startswith("GZ:")))
    @settings(max_examples=100, deadline=None)
    def test_non_json_non_gz_string_returned_unchanged(self, text):
        # Filter out strings that happen to be valid JSON (e.g. "123", "true").
        try:
            json.loads(text)
            return  # valid JSON decodes to the parsed value -- not this property
        except (json.JSONDecodeError, ValueError):
            pass
        assert _decode_payload(text) == text

    @given(garbage=st.text(min_size=3, max_size=80).map(lambda s: "GZ:" + s))
    @settings(max_examples=100, deadline=None)
    def test_malformed_gz_falls_back_without_raising(self, garbage):
        result = _decode_payload(garbage)
        # Either it decodes (vanishingly unlikely for random text) or the raw
        # string comes back -- the contract is "never raise".
        assert result is not None


class TestWindowSecondsFor:
    """window_seconds_for is bounded by the operator ceiling and idempotent."""

    @pytest.fixture(autouse=True)
    def _fixed_env(self, monkeypatch):
        monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_SECONDS", "100")
        monkeypatch.setenv("COORDINATOR_ACCEPTANCE_WINDOW_MAX_SECONDS", "1000")

    _raw_window = st.one_of(
        st.integers(min_value=-1000, max_value=5000),
        st.text(max_size=12),
        st.none(),
        st.booleans(),
        st.floats(allow_nan=False, allow_infinity=False),
    )

    @given(raw=_raw_window)
    @settings(max_examples=200, deadline=None)
    def test_result_within_bounds(self, raw):
        constraints = {} if raw is None else {"acceptance_window_seconds": raw}
        result = acceptance.window_seconds_for(constraints)
        assert isinstance(result, int)
        assert 0 <= result <= acceptance.max_window_seconds()
        # Idempotent: same input -> same output.
        assert acceptance.window_seconds_for(constraints) == result

    @given(window=st.integers(min_value=0, max_value=1000))
    @settings(max_examples=50, deadline=None)
    def test_within_ceiling_returns_requested(self, window):
        result = acceptance.window_seconds_for({"acceptance_window_seconds": window})
        assert result == window

    @given(window=st.integers(min_value=1001, max_value=10_000_000))
    @settings(max_examples=30, deadline=None)
    def test_above_ceiling_clamps_to_max(self, window):
        result = acceptance.window_seconds_for({"acceptance_window_seconds": window})
        assert result == acceptance.max_window_seconds() == 1000

    @given(window=st.integers(max_value=-1))
    @settings(max_examples=30, deadline=None)
    def test_negative_clamps_to_zero(self, window):
        result = acceptance.window_seconds_for({"acceptance_window_seconds": window})
        assert result == 0

    def test_none_constraints_uses_default(self):
        assert acceptance.window_seconds_for(None) == 100

    def test_missing_key_uses_default(self):
        assert acceptance.window_seconds_for({}) == 100

    def test_unparseable_uses_default(self):
        assert acceptance.window_seconds_for({"acceptance_window_seconds": "not-a-number"}) == 100
