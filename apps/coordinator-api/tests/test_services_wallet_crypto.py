"""Coverage for wallet_crypto service (#1289 residual).

Pure-crypto module: Ethereum keypair generation, key consistency checks,
PBKDF2+Fernet private-key encryption, and wallet create/recover roundtrips.
No infrastructure required.
"""

import base64

import pytest

from coordinator_api.contexts.wallet.services.wallet_crypto import (
    create_secure_wallet,
    decrypt_private_key,
    derive_secure_key,
    encrypt_private_key,
    generate_ethereum_keypair,
    recover_wallet,
    validate_private_key_format,
    verify_keypair_consistency,
)

PASSWORD = "correct horse battery staple"


@pytest.mark.unit
def test_generate_ethereum_keypair_shape():
    private_key, public_key, address = generate_ethereum_keypair()
    assert validate_private_key_format(private_key)
    assert public_key
    assert address.startswith("0x") and len(address) == 42
    assert verify_keypair_consistency(private_key, address)


@pytest.mark.unit
def test_generate_keypair_unique():
    first = generate_ethereum_keypair()
    second = generate_ethereum_keypair()
    assert first[0] != second[0]
    assert first[2] != second[2]


@pytest.mark.unit
def test_verify_keypair_consistency_accepts_checksum_and_lowercase():
    private_key, _, address = generate_ethereum_keypair()
    assert verify_keypair_consistency(private_key, address)
    assert verify_keypair_consistency(private_key, address.lower())


@pytest.mark.unit
def test_verify_keypair_consistency_rejects_wrong_address():
    private_key, _, _ = generate_ethereum_keypair()
    _, _, other_address = generate_ethereum_keypair()
    assert not verify_keypair_consistency(private_key, other_address)


@pytest.mark.unit
def test_verify_keypair_consistency_rejects_garbage():
    assert not verify_keypair_consistency("not-a-key", "0x" + "0" * 40)


@pytest.mark.unit
def test_derive_secure_key_deterministic_with_salt():
    key1, salt = derive_secure_key(PASSWORD)
    key2, salt2 = derive_secure_key(PASSWORD, salt)
    assert key1 == key2
    assert salt2 == salt


@pytest.mark.unit
def test_derive_secure_key_random_salt_differs():
    key1, _ = derive_secure_key(PASSWORD)
    key2, _ = derive_secure_key(PASSWORD)
    assert key1 != key2


@pytest.mark.unit
def test_encrypt_decrypt_roundtrip():
    private_key, _, _ = generate_ethereum_keypair()
    encrypted = encrypt_private_key(private_key, PASSWORD)
    assert encrypted["algorithm"] == "PBKDF2-SHA256-Fernet"
    assert decrypt_private_key(encrypted, PASSWORD) == private_key


@pytest.mark.unit
def test_decrypt_wrong_password_fails():
    private_key, _, _ = generate_ethereum_keypair()
    encrypted = encrypt_private_key(private_key, PASSWORD)
    with pytest.raises(ValueError):
        decrypt_private_key(encrypted, "wrong password")


@pytest.mark.unit
def test_decrypt_tampered_ciphertext_fails():
    private_key, _, _ = generate_ethereum_keypair()
    encrypted = encrypt_private_key(private_key, PASSWORD)
    encrypted["encrypted_key"] = base64.urlsafe_b64encode(b"tampered").decode()
    with pytest.raises(ValueError):
        decrypt_private_key(encrypted, PASSWORD)


@pytest.mark.unit
def test_validate_private_key_format():
    private_key, _, _ = generate_ethereum_keypair()
    bare = private_key[2:] if private_key.startswith("0x") else private_key
    assert validate_private_key_format(private_key)
    assert validate_private_key_format("0x" + bare)
    assert validate_private_key_format(bare)
    assert not validate_private_key_format("0x" + "0" * 64)  # invalid curve scalar
    assert not validate_private_key_format("zz" * 32)
    assert not validate_private_key_format("0x" + "ab" * 16)  # too short
    assert not validate_private_key_format("")


@pytest.mark.unit
def test_create_secure_wallet_consistent():
    wallet = create_secure_wallet("agent-1", PASSWORD)
    assert wallet["agent_id"] == "agent-1"
    assert wallet["address"].startswith("0x")
    assert verify_keypair_consistency(decrypt_private_key(wallet["encrypted_private_key"], PASSWORD), wallet["address"])


@pytest.mark.unit
def test_recover_wallet_roundtrip():
    private_key, _, _ = generate_ethereum_keypair()
    encrypted = encrypt_private_key(private_key, PASSWORD)
    recovered = recover_wallet(encrypted, PASSWORD)
    assert recovered["private_key"] == private_key.lstrip("0x") or recovered["private_key"] == private_key
    assert recovered["address"].startswith("0x")


@pytest.mark.unit
def test_recover_wallet_wrong_password_fails():
    private_key, _, _ = generate_ethereum_keypair()
    encrypted = encrypt_private_key(private_key, PASSWORD)
    with pytest.raises(ValueError):
        recover_wallet(encrypted, "wrong password")
