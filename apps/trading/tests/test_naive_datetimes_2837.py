"""#2837: every trading DateTime default must be timezone-NAIVE UTC.

Aware values serialize on SQLite with a ``+00:00`` suffix, which sorts
after every naive ``' '``-separated timestamp — expiry sweeps
(``expires_at < now``) and ``ORDER BY`` clauses then misjudge rows near
the boundary; on PostgreSQL binding an aware value into a naive column
errors outright. All writers go through ``domain.base.utcnow_naive``;
this test fails if any model default_factory reintroduces tzinfo.
"""

from __future__ import annotations

import datetime as _dt

from sqlmodel import SQLModel

import trading_service.domain.inter_chain as inter_chain_domain
import trading_service.domain.trading as trading_domain


def _datetime_defaults(module) -> list[tuple[str, object]]:
    out = []
    for name in dir(module):
        cls = getattr(module, name)
        if not (isinstance(cls, type) and issubclass(cls, SQLModel) and cls.__module__ == module.__name__):
            continue
        for field_name, field in cls.model_fields.items():
            factory = field.default_factory
            if factory is None:
                continue
            try:
                value = factory()
            except TypeError:
                continue
            if isinstance(value, _dt.datetime):
                out.append((f"{cls.__name__}.{field_name}", value))
    return out


def test_all_domain_datetime_defaults_are_naive():
    defaults = _datetime_defaults(inter_chain_domain) + _datetime_defaults(trading_domain)
    assert defaults, "expected datetime defaults to inspect"
    for label, value in defaults:
        assert value.tzinfo is None, f"{label} produced aware datetime {value!r}"
        assert value.utcoffset() is None


def test_utcnow_naive_helper():
    from trading_service.domain.base import utcnow_naive

    value = utcnow_naive()
    assert isinstance(value, _dt.datetime)
    assert value.tzinfo is None
