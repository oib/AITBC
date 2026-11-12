"""
MarketService — composed facade over the domain mixins.

Pure-move split of the former monolithic module (#1867): behaviour is
unchanged; methods live in core/offers/ratings/jobs mixins and shared
module-level helpers live in shared.py. All public names remain
importable from ``market_service.services.market_service`` via __init__.
"""

from .jobs import _JobsMixin
from .offers import _OffersMixin
from .ratings import _RatingsMixin


class MarketService(_OffersMixin, _RatingsMixin, _JobsMixin):
    """Market service for managing market operations"""
