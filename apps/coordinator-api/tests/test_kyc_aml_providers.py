"""Tests for the KYC/AML provider integration.

V23-44. This module decides whether a user passes compliance screening and had **no tests
anywhere in the repo**. What coverage existed tested `cli/utils/kyc_aml_providers.py`, an
older copy whose `SimpleKYCProvider`/`SimpleAMLProvider` were superseded here by
`RealKYCProvider`/`RealAMLProvider` — a different API the old suite could not be pointed at.
Both were removed in V23-43.

The first thing these tests establish is that "Real" is a misnomer: no provider is contacted.
Every `_*_kyc` method builds a headers dict as a bare expression statement, discards it,
sleeps, and returns a hardcoded response; `check_kyc_status` and `screen_user` derive their
verdict from `sha256(input) % n`. The tests are written against that behaviour deliberately
and say so, so that wiring in a real provider fails them rather than passing quietly.
"""

from __future__ import annotations

import asyncio
import hashlib

import pytest
from coordinator_api.contexts.security.services import kyc_aml_providers as kyc_module
from coordinator_api.contexts.security.services.kyc_aml_providers import (
    AMLCheck,
    AMLRiskLevel,
    KYCProvider,
    KYCRequest,
    KYCResponse,
    KYCStatus,
    RealAMLProvider,
    RealKYCProvider,
    check_kyc_status,
    perform_aml_screening,
    submit_kyc_verification,
)

CUSTOMER = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "date_of_birth": "1990-01-01",
}

# Inputs chosen by searching for one that lands in each branch of the modulus. They are
# hardcoded rather than derived from the implementation: deriving them would make the
# assertions tautological, and a request id whose verdict changes IS a behaviour change worth
# failing on. `check_kyc_status` reads user_id from `request_id.split("_")[1]`, so the ids
# below keep the provider_user_timestamp shape the submit path produces.
KYC_STATUS_CASES = [
    ("chainalysis_user1_1700000000", KYCStatus.APPROVED, 0.05, None),
    ("chainalysis_user0_1700000000", KYCStatus.PENDING, 0.15, None),
    ("chainalysis_user4_1700000000", KYCStatus.REJECTED, 0.85, "Document verification failed"),
    ("chainalysis_user2_1700000000", KYCStatus.FAILED, 0.95, "Technical error during verification"),
]

# Same idea for `screen_user`, which hashes f"{user_id}_{email}". Note residues 3 and 4 both
# fall through to LOW -- the `else` covers two of the five.
AML_SCREENING_CASES = [
    ("user1", AMLRiskLevel.CRITICAL, 0.95, 1),
    ("user13", AMLRiskLevel.HIGH, 0.75, 0),
    ("user6", AMLRiskLevel.MEDIUM, 0.45, 0),
    ("user4", AMLRiskLevel.LOW, 0.15, 0),
    ("user0", AMLRiskLevel.LOW, 0.15, 0),
]
AML_EMAIL = "a@example.com"


@pytest.fixture
def no_sleep(monkeypatch):
    """Skip the simulated provider latency.

    The module sleeps 0.5-2.0s per call to imitate a network round trip. Left in, this file
    would take ~25 seconds to assert on arithmetic. `test_the_providers_sleep_instead_of_
    calling_anyone` covers the fact that the sleeps exist.
    """

    async def _instant(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant)


# --------------------------------------------------------------------------------------
# What these providers actually are
# --------------------------------------------------------------------------------------


async def test_the_providers_sleep_instead_of_calling_anyone():
    """`Real*` is a misnomer, and this is the test that will fail when it stops being one.

    A submission succeeds with `session is None`. If any provider branch made an HTTP request
    it would raise on the missing session, so this passing is proof no request is attempted.
    """
    provider = RealKYCProvider()
    provider.set_api_key(KYCProvider.CHAINALYSIS, "k")
    assert provider.session is None, "no session was opened; the context manager was not used"

    slept: list[float] = []

    async def _record(delay):
        slept.append(delay)

    original = asyncio.sleep
    asyncio.sleep = _record
    try:
        response = await provider.submit_kyc_verification(
            KYCRequest(user_id="u", provider=KYCProvider.CHAINALYSIS, customer_data=CUSTOMER)
        )
    finally:
        asyncio.sleep = original

    assert slept == [1], "the chainalysis branch is a one-second sleep, not a request"
    assert response.verification_data == {"provider": "chainalysis", "submitted": True}
    assert provider.session is None, "still no session — nothing was sent"


# --------------------------------------------------------------------------------------
# set_api_key
# --------------------------------------------------------------------------------------


def test_kyc_set_api_key_is_per_provider():
    provider = RealKYCProvider()
    assert provider.api_keys == {}

    provider.set_api_key(KYCProvider.SUMSUB, "sumsub-key")
    provider.set_api_key(KYCProvider.ONFIDO, "onfido-key")

    assert provider.api_keys == {KYCProvider.SUMSUB: "sumsub-key", KYCProvider.ONFIDO: "onfido-key"}


def test_kyc_set_api_key_overwrites():
    provider = RealKYCProvider()
    provider.set_api_key(KYCProvider.JUMIO, "first")
    provider.set_api_key(KYCProvider.JUMIO, "second")
    assert provider.api_keys[KYCProvider.JUMIO] == "second"


def test_aml_set_api_key_takes_a_plain_string():
    """`RealAMLProvider` keys by `str`, not by the `KYCProvider` enum — a real asymmetry."""
    provider = RealAMLProvider()
    provider.set_api_key("chainalysis_aml", "aml-key")
    assert provider.api_keys == {"chainalysis_aml": "aml-key"}


def test_every_kyc_provider_has_a_base_url():
    """A provider added to the enum without a URL would submit against a KeyError."""
    provider = RealKYCProvider()
    assert set(provider.base_urls) == set(KYCProvider)


# --------------------------------------------------------------------------------------
# submit_kyc_verification
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider_enum", "risk_score", "expiry_days"),
    [
        (KYCProvider.CHAINALYSIS, 0.15, 30),
        (KYCProvider.SUMSUB, 0.12, 90),
        (KYCProvider.ONFIDO, 0.08, 60),
        (KYCProvider.JUMIO, 0.1, 45),
        (KYCProvider.VERIFF, 0.07, 30),
    ],
)
async def test_submit_routes_to_each_provider(no_sleep, provider_enum, risk_score, expiry_days):
    provider = RealKYCProvider()
    provider.set_api_key(provider_enum, "key")

    response = await provider.submit_kyc_verification(
        KYCRequest(user_id="user123", provider=provider_enum, customer_data=CUSTOMER)
    )

    assert isinstance(response, KYCResponse)
    assert response.provider is provider_enum
    assert response.user_id == "user123"
    assert response.status is KYCStatus.PENDING, "every provider returns PENDING on submission"
    assert response.risk_score == risk_score
    assert response.verification_data == {"provider": provider_enum.value, "submitted": True}
    assert response.request_id.startswith(f"{provider_enum.value}_user123_")
    assert response.expires_at is not None
    # Each provider carries its own validity window; a single shared default would hide that.
    assert round((response.expires_at - response.created_at).total_seconds() / 86400) == expiry_days


async def test_submit_without_an_api_key_is_refused(no_sleep):
    """The key check happens before dispatch, so an unconfigured provider never reaches a branch."""
    provider = RealKYCProvider()

    with pytest.raises(ValueError, match="No API key configured for"):
        await provider.submit_kyc_verification(KYCRequest(user_id="u", provider=KYCProvider.VERIFF, customer_data=CUSTOMER))


async def test_submit_only_needs_the_key_for_the_provider_being_used(no_sleep):
    provider = RealKYCProvider()
    provider.set_api_key(KYCProvider.ONFIDO, "key")

    with pytest.raises(ValueError, match="No API key configured for"):
        await provider.submit_kyc_verification(KYCRequest(user_id="u", provider=KYCProvider.JUMIO, customer_data=CUSTOMER))


async def test_submit_ignores_documents_and_verification_level(no_sleep):
    """Both `KYCRequest` fields are accepted and then never read — pinned so it is visible."""
    provider = RealKYCProvider()
    provider.set_api_key(KYCProvider.SUMSUB, "key")

    plain = await provider.submit_kyc_verification(
        KYCRequest(user_id="u", provider=KYCProvider.SUMSUB, customer_data=CUSTOMER)
    )
    with_extras = await provider.submit_kyc_verification(
        KYCRequest(
            user_id="u",
            provider=KYCProvider.SUMSUB,
            customer_data=CUSTOMER,
            documents=[{"type": "passport", "front": "..."}],
            verification_level="enhanced",
        )
    )

    assert plain.risk_score == with_extras.risk_score
    assert plain.verification_data == with_extras.verification_data
    assert plain.status is with_extras.status


async def test_submit_does_not_require_any_customer_data(no_sleep):
    """`customer_data` is read only by the sumsub branch, into a dict it discards."""
    provider = RealKYCProvider()
    provider.set_api_key(KYCProvider.SUMSUB, "key")

    response = await provider.submit_kyc_verification(KYCRequest(user_id="u", provider=KYCProvider.SUMSUB, customer_data={}))

    assert response.status is KYCStatus.PENDING


# --------------------------------------------------------------------------------------
# check_kyc_status
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("request_id", "status", "risk_score", "reason"), KYC_STATUS_CASES)
async def test_check_status_covers_every_branch(no_sleep, request_id, status, risk_score, reason):
    provider = RealKYCProvider()

    response = await provider.check_kyc_status(request_id, KYCProvider.CHAINALYSIS)

    assert response.status is status
    assert response.risk_score == risk_score
    assert response.rejection_reason == reason
    assert response.request_id == request_id
    assert response.user_id == request_id.split("_")[1]


async def test_check_status_does_not_raise_on_the_branches_that_set_no_reason(no_sleep):
    """`rejection_reason` is assigned in only two of the four branches.

    The return builds `rejection_reason if status in [REJECTED, FAILED] else None`, and the
    conditional expression evaluates its test first, so APPROVED and PENDING short-circuit to
    None without ever reading the unbound name. It works, but by evaluation order rather than
    by construction — one refactor to `x = rejection_reason` above the return turns it into an
    `UnboundLocalError` on the two most common outcomes. This is the test that would catch it.
    """
    provider = RealKYCProvider()

    for request_id, expected, _score, _reason in KYC_STATUS_CASES[:2]:
        response = await provider.check_kyc_status(request_id, KYCProvider.CHAINALYSIS)
        assert response.status is expected
        assert response.rejection_reason is None


async def test_check_status_is_a_pure_function_of_the_request_id(no_sleep):
    """No state is consulted, so the same id yields the same verdict forever."""
    provider = RealKYCProvider()
    request_id = KYC_STATUS_CASES[2][0]

    first = await provider.check_kyc_status(request_id, KYCProvider.CHAINALYSIS)
    second = await RealKYCProvider().check_kyc_status(request_id, KYCProvider.SUMSUB)

    assert first.status is second.status is KYCStatus.REJECTED
    assert first.risk_score == second.risk_score


async def test_check_status_reports_the_provider_it_was_asked_about(no_sleep):
    """The provider is echoed from the argument, not parsed from the id — they can disagree."""
    provider = RealKYCProvider()

    response = await provider.check_kyc_status("chainalysis_user1_1700000000", KYCProvider.VERIFF)

    assert response.provider is KYCProvider.VERIFF
    assert response.verification_data == {"provider": "veriff", "checked": True}


async def test_check_status_needs_no_api_key(no_sleep):
    """Unlike submission, the status path has no key check at all."""
    provider = RealKYCProvider()
    assert provider.api_keys == {}

    response = await provider.check_kyc_status("chainalysis_user1_1700000000", KYCProvider.CHAINALYSIS)

    assert response.status is KYCStatus.APPROVED


async def test_check_status_on_an_id_without_an_underscore_raises(no_sleep):
    """`request_id.split("_")[1]` indexes unguarded, so a bare id is an IndexError."""
    provider = RealKYCProvider()

    with pytest.raises(IndexError):
        await provider.check_kyc_status("no-underscores-here", KYCProvider.CHAINALYSIS)


# --------------------------------------------------------------------------------------
# screen_user
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("user_id", "risk_level", "risk_score", "sanction_count"), AML_SCREENING_CASES)
async def test_screen_user_covers_every_risk_branch(no_sleep, user_id, risk_level, risk_score, sanction_count):
    provider = RealAMLProvider()

    check = await provider.screen_user(user_id, {"email": AML_EMAIL})

    assert isinstance(check, AMLCheck)
    assert check.risk_level is risk_level
    assert check.risk_score == risk_score
    assert len(check.sanctions_hits) == sanction_count
    assert check.user_id == user_id
    assert check.check_id.startswith(f"aml_{user_id}_")
    assert check.provider == "chainalysis_aml", "the provider is hardcoded, not chosen"


async def test_only_the_critical_branch_produces_a_sanctions_hit(no_sleep):
    provider = RealAMLProvider()

    critical = await provider.screen_user("user1", {"email": AML_EMAIL})

    assert critical.risk_level is AMLRiskLevel.CRITICAL
    assert critical.sanctions_hits == [{"list": "OFAC", "name": "Test Sanction", "confidence": 0.9}]


async def test_pep_and_adverse_media_are_never_populated(no_sleep):
    """Both lists are on the dataclass and hardcoded empty — nothing screens for either."""
    provider = RealAMLProvider()

    for user_id, *_ in AML_SCREENING_CASES:
        check = await provider.screen_user(user_id, {"email": AML_EMAIL})
        assert check.pep_hits == []
        assert check.adverse_media == []


async def test_screen_user_keys_on_email_so_the_same_user_can_get_two_verdicts(no_sleep):
    """The hash is over f"{user_id}_{email}", so changing email changes the risk level."""
    provider = RealAMLProvider()

    critical = await provider.screen_user("user1", {"email": AML_EMAIL})
    other = await provider.screen_user("user1", {"email": "different@example.com"})

    assert critical.risk_level is AMLRiskLevel.CRITICAL
    assert other.risk_level is not AMLRiskLevel.CRITICAL, "one user, two risk levels, decided by which address was supplied"


async def test_screen_user_treats_a_missing_email_as_empty(no_sleep):
    """`user_data.get("email", "")` — no email is a valid screening input, not an error."""
    provider = RealAMLProvider()

    absent = await provider.screen_user("userX", {})
    empty = await provider.screen_user("userX", {"email": ""})

    assert absent.risk_level is empty.risk_level
    assert absent.risk_score == empty.risk_score


async def test_screen_user_needs_no_api_key(no_sleep):
    provider = RealAMLProvider()
    assert provider.api_keys == {}

    check = await provider.screen_user("user1", {"email": AML_EMAIL})

    assert check.risk_level is AMLRiskLevel.CRITICAL


# --------------------------------------------------------------------------------------
# The module-level wrappers
# --------------------------------------------------------------------------------------


async def test_submit_wrapper_returns_json_ready_values(no_sleep):
    """Enums come back as `.value` strings and the datetime as an ISO string."""
    result = await submit_kyc_verification("user123", "chainalysis", CUSTOMER)

    assert result["provider"] == "chainalysis"
    assert result["status"] == "pending"
    assert isinstance(result["status"], str) and not isinstance(result["status"], KYCStatus)
    assert result["user_id"] == "user123"
    assert result["risk_score"] == 0.15
    assert result["created_at"].startswith("20")
    assert "expires_at" not in result, "the wrapper drops the expiry the response carries"


async def test_submit_wrapper_supplies_its_own_demo_api_key(no_sleep):
    """It calls `set_api_key(..., "demo_api_key")`, so the key check can never fail here."""
    result = await submit_kyc_verification("user123", "veriff", CUSTOMER)

    assert result["status"] == "pending"
    assert kyc_module.kyc_provider.api_keys[KYCProvider.VERIFF] == "demo_api_key"


async def test_submit_wrapper_rejects_an_unknown_provider_name(no_sleep):
    with pytest.raises(ValueError, match="is not a valid KYCProvider"):
        await submit_kyc_verification("user123", "not-a-provider", CUSTOMER)


async def test_status_wrapper_includes_the_rejection_reason(no_sleep):
    result = await check_kyc_status("chainalysis_user4_1700000000", "chainalysis")

    assert result["status"] == "rejected"
    assert result["rejection_reason"] == "Document verification failed"
    assert result["risk_score"] == 0.85


async def test_aml_wrapper_returns_json_ready_values(no_sleep):
    result = await perform_aml_screening("user1", {"email": AML_EMAIL})

    assert result["risk_level"] == "critical"
    assert result["risk_score"] == 0.95
    assert result["sanctions_hits"] == [{"list": "OFAC", "name": "Test Sanction", "confidence": 0.9}]
    assert result["provider"] == "chainalysis_aml"
    assert result["checked_at"].startswith("20")
    assert "pep_hits" not in result, "the wrapper drops pep_hits and adverse_media"


# --------------------------------------------------------------------------------------
# The shared singletons
# --------------------------------------------------------------------------------------


async def test_the_wrappers_share_one_provider_instance_and_close_its_session():
    """`kyc_provider` and `aml_provider` are module-level singletons used with `async with`.

    `__aenter__` assigns `self.session` and `__aexit__` closes it, so two overlapping calls
    share one attribute: the second entry replaces the session the first is holding, and the
    first exit closes the session the second is still inside. Nothing reads `self.session`
    today — every branch is simulated — so this is latent rather than live. It becomes a live
    bug on the day a real HTTP call is added, which is the day this test should be read.
    """
    provider = RealKYCProvider()

    async with provider:
        first = provider.session
        assert first is not None
        async with provider:
            second = provider.session
        # the inner exit closed the session, and the outer block still points at it
        assert second is not None
        assert second is not first, "the second entry replaced the first entry's session"
        assert second.closed, "the inner exit closed the session the outer block is still in"
        assert provider.session is second

    await first.close()


async def test_aenter_returns_self_despite_its_annotation():
    """Annotated `-> None` with a `# type: ignore[return-value]` on `return self`.

    `async with kyc_provider:` never binds the result, so the lie is invisible in use — but
    `async with RealKYCProvider() as p:` gives a working provider, not None.
    """
    async with RealKYCProvider() as provider:
        assert isinstance(provider, RealKYCProvider)
        assert provider.session is not None

    async with RealAMLProvider() as provider:
        assert isinstance(provider, RealAMLProvider)


# --------------------------------------------------------------------------------------
# The enums and dataclasses
# --------------------------------------------------------------------------------------


def test_enums_are_str_valued():
    """They are `StrEnum`, so they serialise as their values without `.value` at the boundary."""
    assert KYCProvider.SUMSUB == "sumsub"
    assert KYCStatus.APPROVED == "approved"
    assert AMLRiskLevel.CRITICAL == "critical"
    assert sorted(AMLRiskLevel) == ["critical", "high", "low", "medium"]


def test_kyc_request_defaults():
    request = KYCRequest(user_id="u", provider=KYCProvider.ONFIDO, customer_data={})
    assert request.documents is None
    assert request.verification_level == "standard"


def test_the_documented_hash_inputs_still_map_where_the_tests_expect():
    """Guards the parametrised cases above.

    If this fails, the modulus or the hash changed and every expected status/risk level in
    this file moved with it — which is a behaviour change, not a broken fixture.
    """

    def bucket(text: str, modulus: int) -> int:
        return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) % modulus

    assert [bucket(rid, 4) for rid, *_ in KYC_STATUS_CASES] == [0, 1, 2, 3]
    assert [bucket(f"{uid}_{AML_EMAIL}", 5) for uid, *_ in AML_SCREENING_CASES] == [0, 1, 2, 3, 4]
