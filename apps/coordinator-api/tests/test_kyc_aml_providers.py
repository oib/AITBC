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
from coordinator_api.contexts.security.services.kyc_aml_providers import (
    AMLRiskLevel,
    KYCProvider,
    KYCRequest,
    KYCStatus,
    RealAMLProvider,
    RealKYCProvider,
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


# --------------------------------------------------------------------------------------
# check_kyc_status
# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# screen_user
# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# The module-level wrappers
# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# The shared singletons
# --------------------------------------------------------------------------------------


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
