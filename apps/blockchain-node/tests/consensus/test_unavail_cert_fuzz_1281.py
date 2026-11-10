"""#1281 batch item 25: fuzz ``verify_unavailability_cert`` / ``UnavailabilityCertificate.from_dict``.

Deterministic (seeded) corruption of every certificate field. Contract pinned:

* the verifier never raises and always returns ``(bool, str)``;
* a corrupted certificate is rejected with a non-empty reason unless the
  corruption leaves the signed content semantically unchanged;
* the untouched certificate still verifies (the fuzzer is not rejecting everything);
* ``from_dict`` on arbitrary JSON-ish values returns a certificate or ``None``, never raises.
"""

from __future__ import annotations

import copy
import json
import random
import time

import pytest
from aitbc_chain.config import settings
from aitbc_chain.consensus import unavail
from aitbc_chain.consensus.unavail import UnavailabilityCertificate, verify_unavailability_cert

CHAIN = "fuzz-chain"
BLOCK = "0xvoted"
HEIGHT = 100


def _key(byte: str) -> tuple[str, str]:
    from eth_keys import keys

    priv = "0x" + byte * 32
    return keys.PrivateKey(bytes.fromhex(priv[2:])).public_key.to_checksum_address(), priv


ADDR1, KEY1 = _key("11")
ADDR2, KEY2 = _key("22")
ADDR3, KEY3 = _key("33")
from aitbc.crypto.signature_recovery import canonical_address  # noqa: E402

VSET = {canonical_address(a) for a in (ADDR1, ADDR2, ADDR3)}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(settings, "unavail_cert_max_age_seconds", 120.0)
    monkeypatch.setattr(settings, "multi_validator_min_attestations", 2)
    monkeypatch.setattr(settings, "unavail_min_responses", 0)


def _valid(epoch: int | None = None, signers=((ADDR1, KEY1), (ADDR2, KEY2))) -> dict:
    epoch = int(time.time()) if epoch is None else epoch
    cert = UnavailabilityCertificate(
        chain_id=CHAIN,
        height=HEIGHT,
        hash=BLOCK,
        epoch=epoch,
        responses=tuple(
            {"validator": a, "signature": unavail.build_unavail_response(CHAIN, HEIGHT, BLOCK, epoch, a, k)["signature"]}
            for a, k in signers
        ),
    )
    return cert.to_dict()


def _verify(raw, **overrides):
    kwargs = {"chain_id": CHAIN, "height": HEIGHT, "block_hash": BLOCK, "validator_set": set(VSET)}
    kwargs.update(overrides)
    return verify_unavailability_cert(raw, **kwargs)


def _assert_clean(result) -> None:
    assert isinstance(result, tuple) and len(result) == 2
    ok, reason = result
    assert isinstance(ok, bool) and isinstance(reason, str)
    assert ok == (reason == "")


def _flip_hex(sig: str, rng: random.Random) -> str:
    body = sig[2:] if sig.startswith("0x") else sig
    if not body:
        return sig
    i = rng.randrange(len(body))
    repl = rng.choice([c for c in "0123456789abcdef" if c != body[i].lower()])
    return ("0x" if sig.startswith("0x") else "") + body[:i] + repl + body[i + 1 :]


JUNK = [
    None,
    True,
    False,
    0,
    -1,
    2**70,
    1.5,
    float("nan"),
    float("inf"),
    "",
    " ",
    "0x",
    "0xzz",
    "x" * 5000,
    [],
    {},
    [1],
    {"a": 1},
]


def test_untouched_cert_verifies():
    ok, reason = _verify(_valid())
    assert ok, reason


def test_all_three_signers_verify():
    ok, reason = _verify(_valid(signers=((ADDR1, KEY1), (ADDR2, KEY2), (ADDR3, KEY3))))
    assert ok, reason


@pytest.mark.parametrize("field", ["version", "kind", "chain_id", "height", "hash", "epoch", "responses", "index_verdict"])
def test_top_level_field_junk_never_raises_and_never_verifies_bound_fields(field):
    for junk in JUNK:
        raw = _valid()
        raw[field] = junk
        result = _verify(raw)
        _assert_clean(result)
        if field in {"kind", "chain_id", "height", "hash", "epoch", "responses"}:
            assert not result[0], (field, junk, result)


def test_missing_every_key_rejected_cleanly():
    for field in ("kind", "chain_id", "height", "hash", "epoch", "responses"):
        raw = _valid()
        del raw[field]
        result = _verify(raw)
        _assert_clean(result)
        assert not result[0], field


def test_signature_bit_flips_rejected():
    rng = random.Random(1281)
    for _ in range(60):
        raw = _valid()
        idx = rng.randrange(len(raw["responses"]))
        raw["responses"][idx]["signature"] = _flip_hex(raw["responses"][idx]["signature"], rng)
        result = _verify(raw)
        _assert_clean(result)
        assert not result[0] and result[1] in {"bad_signature", "signer_not_validator", "below_threshold"}


def test_signature_truncation_and_junk_rejected():
    for sig in ["", "0x", "0x00", "0x" + "00" * 65, "0x" + "ff" * 65, "not-hex", "0x" + "ab" * 64, "0x" + "ab" * 66]:
        raw = _valid()
        raw["responses"][0]["signature"] = sig
        result = _verify(raw)
        _assert_clean(result)
        assert not result[0], sig


def test_response_entry_junk_rejected_cleanly():
    for junk in [
        None,
        0,
        "x",
        [],
        [1, 2],
        {"validator": None},
        {"validator": ADDR1},
        {"signature": "0x1"},
        {"validator": "", "signature": ""},
    ]:
        raw = _valid()
        raw["responses"][0] = junk
        result = _verify(raw)
        _assert_clean(result)
        if not isinstance(junk, dict):
            # non-dict responses are dropped by from_dict, leaving one valid response -> below threshold
            assert not result[0]
        else:
            assert not result[0]


def test_signer_address_corruptions_rejected():
    for signer in [ADDR3, ADDR1.lower(), "0x" + "00" * 20, "0x1234", "", "nonsense", ADDR1 + "00", None]:
        raw = _valid()
        raw["responses"][0]["validator"] = signer
        result = _verify(raw)
        _assert_clean(result)
        if signer == ADDR1.lower():
            assert result[0], result  # canonicalisation: same signer, still valid
        else:
            assert not result[0], (signer, result)


def test_swapped_signatures_between_signers_rejected():
    raw = _valid()
    s0, s1 = raw["responses"][0]["signature"], raw["responses"][1]["signature"]
    raw["responses"][0]["signature"], raw["responses"][1]["signature"] = s1, s0
    result = _verify(raw)
    _assert_clean(result)
    assert not result[0] and result[1] == "bad_signature"


def test_duplicate_and_padded_responses():
    base = _valid()
    dup = copy.deepcopy(base)
    dup["responses"].append(copy.deepcopy(base["responses"][0]))
    ok, reason = _verify(dup)
    assert not ok and reason == "duplicate_signer"
    big = copy.deepcopy(base)
    big["responses"] = big["responses"] * 200
    ok, reason = _verify(big)
    assert not ok and reason == "duplicate_signer"
    empty = copy.deepcopy(base)
    empty["responses"] = []
    ok, reason = _verify(empty)
    assert not ok and reason == "below_threshold"


def test_epoch_boundaries():
    now = time.time()
    fresh = _valid(epoch=int(now))
    assert _verify(fresh, now=now)[0]
    max_age = settings.unavail_cert_max_age_seconds
    at_edge = _valid(epoch=int(now - max_age + 2))
    assert _verify(at_edge, now=now)[0]
    for delta in (max_age + 5, 10 * max_age, 10**9):
        stale = _valid(epoch=int(now - delta))
        result = _verify(stale, now=now)
        _assert_clean(result)
        assert not result[0] and result[1] == "stale_epoch"
    future = _valid(epoch=int(now + max_age + 5))
    result = _verify(future, now=now)
    assert not result[0] and result[1] == "stale_epoch"  # abs(): far-future epochs are rejected too


def test_epoch_in_cert_must_match_signed_epoch():
    raw = _valid()
    raw["epoch"] += 1  # the signatures bind the original epoch
    result = _verify(raw)
    _assert_clean(result)
    assert not result[0] and result[1] == "bad_signature"


def test_binding_mismatches_report_their_reason():
    raw = _valid()
    assert _verify(raw, chain_id="other")[1] == "chain_mismatch"
    assert _verify(raw, height=HEIGHT + 1)[1] == "height_mismatch"
    assert _verify(raw, block_hash="0xother")[1] == "hash_mismatch"
    assert _verify(raw, validator_set=set())[1] == "no_validator_set"


def test_random_field_mutations_never_raise():
    rng = random.Random(0xAB1)
    fields = ["kind", "chain_id", "height", "hash", "epoch", "responses", "version", "index_verdict"]
    for _ in range(400):
        raw = _valid()
        for _ in range(rng.randint(1, 3)):
            f = rng.choice(fields)
            if rng.random() < 0.2:
                raw.pop(f, None)
            else:
                raw[f] = rng.choice(JUNK)
        result = _verify(raw)
        _assert_clean(result)
        if raw != _valid() and any(raw.get(f) != _valid().get(f) for f in ("kind", "chain_id", "height", "hash")):
            assert not result[0]


def test_non_dict_non_cert_inputs():
    for junk in [None, 0, "", "x", [], [1], True, 3.5]:
        result = verify_unavailability_cert(junk, chain_id=CHAIN, height=HEIGHT, block_hash=BLOCK, validator_set=set(VSET))
        _assert_clean(result)
        assert result == (False, "malformed")


def test_from_dict_arbitrary_json_never_raises():
    rng = random.Random(7)

    def rand_value(depth=0):
        if depth > 2 or rng.random() < 0.5:
            return rng.choice(JUNK)
        if rng.random() < 0.5:
            return [rand_value(depth + 1) for _ in range(rng.randint(0, 3))]
        return {
            rng.choice(["a", "validator", "signature", "kind", "responses"]): rand_value(depth + 1)
            for _ in range(rng.randint(0, 3))
        }

    for _ in range(500):
        raw = {k: rand_value() for k in ("kind", "chain_id", "height", "hash", "epoch", "responses", "index_verdict")}
        if rng.random() < 0.5:
            raw["kind"] = "unavailability_cert"
        cert = UnavailabilityCertificate.from_dict(raw)
        assert cert is None or isinstance(cert, UnavailabilityCertificate)
        _assert_clean(_verify(raw))
    json.dumps(_valid())  # serialisable round trip sanity
