"""Unit tests for the shared JSON encoder (aitbc.utils.json_utils).

#1585/#1635: one convention for Decimal/datetime/UUID serialization —
Decimal as str (exact, no binary float for money), temporal types as
ISO 8601, UUID/Enum as their string/value forms.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from aitbc.utils.json_utils import json_default, to_jsonable


class _Flavor(StrEnum):
    VANILLA = "vanilla"


def test_json_default_decimal_is_str() -> None:
    assert json_default(Decimal("0.01000000")) == "0.01000000"
    assert json.dumps({"price": Decimal("1.5")}, default=json_default) == '{"price": "1.5"}'


def test_json_default_datetime_is_iso() -> None:
    dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert json_default(dt) == dt.isoformat()
    assert "T" in json_default(dt)


def test_json_default_uuid_and_enum() -> None:
    uid = uuid4()
    assert json_default(uid) == str(uid)
    assert json_default(_Flavor.VANILLA) == "vanilla"


def test_json_default_fallback_str() -> None:
    class Odd:
        def __str__(self) -> str:
            return "odd!"

    assert json_default(Odd()) == "odd!"


def test_to_jsonable_nested() -> None:
    uid = uuid4()
    value = {
        "price": Decimal("2.50"),
        "when": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "id": uid,
        "items": [Decimal("0.1"), {"nested": datetime(2026, 1, 1, tzinfo=UTC)}],
        "tags": {"a", "b"},
    }
    out = to_jsonable(value)
    # Round-trips through json.dumps with no default hook needed.
    encoded = json.dumps(out)
    assert '"price": "2.50"' in encoded
    assert f'"id": "{uid}"' in encoded
    assert isinstance(out["items"][0], str)
    assert isinstance(out["items"][1]["nested"], str)
    assert sorted(out["tags"]) == ["a", "b"]
