"""The alias map that reconciles the offer status vocabularies.

`marketplace_service.domain.offer_status` is the only thing standing between a status word
somebody wrote into the database and `OfferFSM.from_string` refusing to parse it, which is what
made `POST /offers/{id}/cancel` a 500 for every offer that existed (V23-83). The behaviour it
enables is tested against the endpoints in `test_main.py`; what is tested here are the
properties of the map itself, because they are the ones that rot quietly.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aitbc.marketplace import OfferStatus
from marketplace_service.domain.offer_status import spellings_of, to_offer_status, try_to_offer_status


@pytest.mark.parametrize("state", list(OfferStatus))
def test_every_fsm_state_has_at_least_one_spelling(state):
    """A state with no spellings makes the `?status=` filter match nothing, silently.

    The filter builds `status IN (spellings_of(state))`, and `IN ()` is a valid query that
    returns no rows — so a new `OfferStatus` member added without a line in the alias map
    would not fail anywhere, it would just make every offer in that state unfindable.
    """
    assert spellings_of(state), f"{state.value} has no spelling in the alias map"


@pytest.mark.parametrize("state", list(OfferStatus))
def test_the_fsm_vocabulary_is_itself_accepted(state):
    """The canonical word for a state has to map back to that state.

    Cheap, and it is the one direction a hand-written map gets wrong: it is easy to add
    "cancelled" and forget that "delisted" is also a thing that appears in rows, because
    anything that goes through `update_offer_status` with an `OfferStatus` value stores one.
    """
    assert to_offer_status(state.value) is state


@pytest.mark.parametrize(
    ("word", "state"),
    [
        # Every spelling this repo has actually written into marketplaceoffer.status, with
        # the code that writes it. If one of these stops parsing, an offer somewhere becomes
        # uncancellable and unbookable rather than anything failing loudly.
        ("available", OfferStatus.AVAILABLE),  # the model default, and MatchingService
        ("open", OfferStatus.AVAILABLE),  # 1 of the 4 offers in the deployed database
        ("reserved", OfferStatus.RESERVED),  # MatchingService, on a match
        ("booked", OfferStatus.RESERVED),  # MarketplaceService.book_offer
        ("cancelled", OfferStatus.DELISTED),  # what cancel_offer asks for
        ("closed", OfferStatus.DELISTED),  # coordinator-api's word for the same end state
    ],
)
def test_the_words_in_use_all_parse(word, state):
    assert to_offer_status(word) is state


def test_parsing_is_case_and_whitespace_insensitive():
    """A status arriving from a query string should not turn on presentation."""
    assert to_offer_status("  Available ") is OfferStatus.AVAILABLE


def test_an_unknown_word_is_rejected_and_says_what_is_known():
    """The message is the whole value of failing here rather than deeper in the FSM.

    `OfferFSM.from_string` raises "Unknown offer status: 'cancelled'" — true, and useless to
    the caller, who has no way to discover which words are not unknown.
    """
    with pytest.raises(ValueError, match="Unknown offer status"):
        to_offer_status("mostly available")

    try:
        to_offer_status("mostly available")
    except ValueError as e:
        assert "available" in str(e) and "booked" in str(e)


def test_the_read_path_variant_answers_none_instead_of_raising():
    """Listings and counts degrade rather than fail.

    A row holding a word nobody recognises should drop out of a tally, not take the whole
    response down with it — which is the shape of failure this finding was.
    """
    assert try_to_offer_status("mostly available") is None
    assert try_to_offer_status("open") is OfferStatus.AVAILABLE


def test_no_word_means_two_different_states():
    """`spellings_of` partitions the map, so a filter cannot match across states.

    Guards against the obvious mistake of listing a word under two states to make some case
    work: `?status=available` would then return booked offers.
    """
    seen: dict[str, OfferStatus] = {}
    for state in OfferStatus:
        for word in spellings_of(state):
            assert word not in seen, f"'{word}' means both {seen.get(word)} and {state}"
            seen[word] = state
