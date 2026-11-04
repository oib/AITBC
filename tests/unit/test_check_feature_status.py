"""#1029 pins: evidence tokens must hit as whole identifiers in non-test
code — a common word embedded in real identifiers is not evidence."""

from __future__ import annotations

import importlib.util
import os

SPEC = importlib.util.spec_from_file_location(
    "check_feature_status",
    os.path.join(os.path.dirname(__file__), "../../scripts/docs/check_feature_status.py"),
)


def _load():
    mod = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(mod)
    return mod


def test_common_word_not_evidence():
    mod = _load()
    haystack = "const BRIDGE_CONFIRMATIONS = 3; const AIT_USD_FIXED_PRICE = 1"
    assert not mod.identifier_in("USD", haystack)  # substring inside identifiers only
    assert mod.identifier_in("BRIDGE_CONFIRMATIONS", haystack)


def test_word_boundary_tokens():
    mod = _load()
    assert mod.identifier_in("AIT_USD_FIXED_PRICE", "AIT_USD_FIXED_PRICE=1")
    assert not mod.identifier_in("AIT_USD_FIXED_PRICE", "AIT_USD_FIXED_PRICE_MAX=1")
    assert mod.identifier_in("fee", "fee=36")
