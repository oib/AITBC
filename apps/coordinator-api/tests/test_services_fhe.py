"""Coverage for fhe_service (#1289 residual).

MockFHEProvider is the deterministic, always-available provider (real
TenSEAL/OpenFHE/ConcreteML availability is environment-dependent and is
never assumed here). FHEService provider-resolution logic is covered
with explicit provider names so results don't depend on which real
backends happen to be installed.
"""

from __future__ import annotations

import numpy as np
import pytest

from coordinator_api.contexts.zk_applications.services.fhe_service import (
    EncryptedData,
    FHEService,
    FHEContext,
    MockFHEProvider,
)


@pytest.fixture
def provider() -> MockFHEProvider:
    return MockFHEProvider()


@pytest.fixture
def context(provider) -> FHEContext:
    return provider.generate_context("ckks")


# ---------------------------------------------------------------------------
# MockFHEProvider — context
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_generate_context_defaults(provider):
    ctx = provider.generate_context("ckks")
    assert ctx.scheme == "mock"
    assert ctx.poly_modulus_degree == 8192
    assert ctx.private_key is not None
    assert ctx.provider_specific == {"mock": True}


@pytest.mark.unit
def test_generate_context_kwargs_override(provider):
    ctx = provider.generate_context("bfv", poly_modulus_degree=4096, scale=2**20)
    assert ctx.poly_modulus_degree == 4096
    assert ctx.scale == 2**20


@pytest.mark.unit
def test_generate_context_keys_are_random(provider):
    a = provider.generate_context("ckks")
    b = provider.generate_context("ckks")
    assert a.public_key != b.public_key
    assert a.private_key != b.private_key


# ---------------------------------------------------------------------------
# encrypt / decrypt roundtrip (documented plaintext-JSON mock)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_encrypt_decrypt_roundtrip(provider, context):
    data = np.array([1.0, 2.0, 3.0])
    enc = provider.encrypt(data, context)
    assert isinstance(enc, EncryptedData)
    assert enc.shape == data.shape
    out = provider.decrypt(enc)
    np.testing.assert_array_equal(out, data)


@pytest.mark.unit
def test_encrypt_preserves_dtype(provider, context):
    data = np.array([1, 2, 3], dtype=np.int64)
    enc = provider.encrypt(data, context)
    out = provider.decrypt(enc)
    assert out.dtype == np.int64


@pytest.mark.unit
def test_decrypt_tampered_ciphertext_fails(provider, context):
    provider.encrypt(np.array([1.0]), context)
    bad = EncryptedData(ciphertext=b"not-json", context=context, shape=(1,), dtype="float64")
    with pytest.raises(ValueError):
        provider.decrypt(bad)


# ---------------------------------------------------------------------------
# inference / homomorphic ops
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_encrypted_inference_linear_model(provider, context):
    data = np.array([2.0, 3.0])
    enc = provider.encrypt(data, context)
    model = {"weights": [1.0, 1.0], "biases": [1.0]}
    out = provider.decrypt(provider.encrypted_inference(model, enc))
    # dot([2,3],[1,1]) + 1 = 6
    np.testing.assert_allclose(out, [6.0])


@pytest.mark.unit
def test_encrypted_inference_requires_weights_and_biases(provider, context):
    enc = provider.encrypt(np.array([1.0]), context)
    with pytest.raises(ValueError, match="weights and biases"):
        provider.encrypted_inference({}, enc)


@pytest.mark.unit
def test_add_and_multiply_scalar(provider, context):
    a = provider.encrypt(np.array([1.0, 2.0]), context)
    b = provider.encrypt(np.array([10.0, 20.0]), context)
    np.testing.assert_allclose(provider.decrypt(provider.add(a, b)), [11.0, 22.0])
    np.testing.assert_allclose(provider.decrypt(provider.multiply_scalar(a, 3.0)), [3.0, 6.0])


# ---------------------------------------------------------------------------
# FHEService resolution
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_service_lists_mock_when_allowed():
    svc = FHEService(allow_mock=True)
    assert "mock" in svc.providers
    assert svc.list_providers()["mock"] is True


@pytest.mark.unit
def test_get_provider_explicit_mock():
    svc = FHEService(allow_mock=True)
    assert isinstance(svc.get_provider("mock"), MockFHEProvider)


@pytest.mark.unit
def test_get_provider_unknown_raises():
    svc = FHEService(allow_mock=True)
    with pytest.raises(ValueError, match="Unknown FHE provider"):
        svc.get_provider("nonexistent")


@pytest.mark.unit
def test_service_encrypt_decrypt_via_mock_provider():
    svc = FHEService(allow_mock=True)
    ctx = svc.generate_fhe_context(provider="mock")
    data = np.array([4.0, 5.0])
    enc = svc.encrypt_ml_data(data, ctx, provider="mock")
    out = svc.decrypt_ml_data(enc, provider="mock")
    np.testing.assert_array_equal(out, data)


@pytest.mark.unit
def test_get_provider_no_default_raises():
    # allow_mock=False with no real backend installed -> no default.
    # If a real provider IS installed on this host the default exists and
    # this test is skipped rather than failing spuriously.
    svc = FHEService(allow_mock=False)
    if svc.default_provider is not None:
        pytest.skip("real FHE provider installed on this host")
    with pytest.raises(RuntimeError, match="No FHE provider"):
        svc.get_provider()
