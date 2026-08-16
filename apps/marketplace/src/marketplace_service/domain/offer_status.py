"""The status words this service stores, and the FSM states they mean.

`OfferStatus` in `aitbc.marketplace.offer_fsm` is the vocabulary the state machine validates
against. It is not the vocabulary in the database. Four other words have been written into
`marketplaceoffer.status` by code in this repo, and `OfferFSM.from_string` rejects every one of
them -- which is why `POST /offers/{id}/cancel` answered 500 for every offer that existed
(V23-83). The two vocabularies are reconciled here rather than by rewriting either one:

* the stored word is what the API has always returned and what clients filter on, and
* this service has no Alembic directory, so there is nowhere to put a migration that would
  rename the rows already on disk.

So the words stay, and this module says what each of them means to the FSM. Adding a word here
is the supported way to introduce one; anything not listed is rejected on the way in, so the
invariant "every stored status parses" holds going forward.

`apps/gpu` has a map of the same shape for `GPURegistry.status`. They are deliberately not
shared: that one is about a GPU's availability ("online", "offline") and this one is about an
offer's lifecycle, and the overlap ("available", "booked", "in_use") is coincidence rather than
a common vocabulary.

Not in the map on purpose: "active" and "inactive". Those are `SoftwareService.status`, a
different table with a different lifecycle, and the CLI's `market offers --status` help text
already confuses the two.
"""

from __future__ import annotations

from aitbc.marketplace import OfferStatus

# Where each spelling comes from, so that removing one is an informed decision:
#
#   available  MarketplaceOffer's default, MatchingService, the /offers?status= filter
#   open       1 of the 4 offers in the deployed database; coordinator-api's vocabulary
#   reserved   MatchingService writes it when an offer is matched
#   booked     MarketplaceService.book_offer writes it; also coordinator-api and apps/gpu
#   cancelled  what cancel_offer asks for -- never actually written, because the FSM
#              rejected it before the assignment, which was the bug
#   closed     coordinator-api's word for the same end state
#   in_use, delisted, expired  OfferStatus itself, stored by anything that goes through
#              update_offer_status
_ALIASES: dict[str, OfferStatus] = {
    "available": OfferStatus.AVAILABLE,
    "open": OfferStatus.AVAILABLE,
    "reserved": OfferStatus.RESERVED,
    "booked": OfferStatus.RESERVED,
    "in_use": OfferStatus.IN_USE,
    "delisted": OfferStatus.DELISTED,
    "cancelled": OfferStatus.DELISTED,
    "closed": OfferStatus.DELISTED,
    "expired": OfferStatus.EXPIRED,
}

# The inverse, for filtering: asking for one spelling has to find the offers stored under the
# others, or `?status=available` hides the offers stored as "open" -- which it did.
_SPELLINGS: dict[OfferStatus, tuple[str, ...]] = {
    state: tuple(word for word, mapped in _ALIASES.items() if mapped is state) for state in OfferStatus
}


def to_offer_status(value: str) -> OfferStatus:
    """Map a stored or requested status word onto its FSM state.

    Raises `ValueError` for anything not listed above. Callers on a write path let that
    surface as a 400: an unknown status is the caller naming a state that does not exist,
    not the service failing.
    """
    try:
        return _ALIASES[value.strip().lower()]
    except (AttributeError, KeyError):
        known = ", ".join(sorted(_ALIASES))
        raise ValueError(f"Unknown offer status: '{value}' (known: {known})") from None


def try_to_offer_status(value: str) -> OfferStatus | None:
    """`to_offer_status` for read paths, which answer `None` instead of raising.

    A listing or a count should not fail outright because one row holds a word nobody
    recognises; it should leave that row out of the tally and keep serving the rest.
    """
    try:
        return to_offer_status(value)
    except ValueError:
        return None


def spellings_of(state: OfferStatus) -> tuple[str, ...]:
    """Every word that means `state`, for matching against what is stored."""
    return _SPELLINGS[state]
