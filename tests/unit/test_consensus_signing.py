"""Unit tests for consensus signing utilities and shared types (v0.7.5 §A3).

Covers:
- sign_consensus_message() + verify_consensus_message() round-trip
- Verification fails with wrong sender, tampered message, empty signature
- sign_block_hash() + verify_block_signature() round-trip
- Block signature verification fails with wrong proposer, invalid format, empty sig
- PBFTMessageData serialization (to_dict / from_dict round-trip)
- ConsensusConfig defaults
- ValidatorInfo, SlashingEventData, ConsensusStatus serialization

Uses real secp256k1 keys generated via eth_account for end-to-end
cryptographic verification — no mocks.
"""

from __future__ import annotations

import time

import pytest

from aitbc.consensus import (
    ConsensusConfig,
    ConsensusStatus,
    PBFTMessageData,
    PBFTMessageType,
    SlashingCondition,
    SlashingEventData,
    ValidatorInfo,
    ValidatorRole,
)
from aitbc.crypto import (
    derive_ethereum_address,
    generate_ethereum_private_key,
    sign_block_hash,
    sign_consensus_message,
    verify_block_signature,
    verify_consensus_message,
)


# ---------------------------------------------------------------------------
# Fixtures — generate real secp256k1 key pairs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def key_pair_a() -> dict[str, str]:
    """Generate a real secp256k1 key pair for testing."""
    priv = generate_ethereum_private_key()
    addr = derive_ethereum_address(priv)
    return {"private_key": priv, "address": addr}


@pytest.fixture(scope="module")
def key_pair_b() -> dict[str, str]:
    """Generate a second key pair for testing wrong-sender scenarios."""
    priv = generate_ethereum_private_key()
    addr = derive_ethereum_address(priv)
    return {"private_key": priv, "address": addr}


# ---------------------------------------------------------------------------
# A1: sign_consensus_message / verify_consensus_message
# ---------------------------------------------------------------------------


class TestSignConsensusMessage:
    def test_round_trip_valid(self, key_pair_a: dict[str, str]) -> None:
        """Sign a message and verify it — should succeed."""
        message = {
            "message_type": "prepare",
            "sender": key_pair_a["address"],
            "view_number": 1,
            "sequence_number": 10,
            "digest": "0xabc123",
            "timestamp": time.time(),
        }
        signature = sign_consensus_message(message, key_pair_a["private_key"])
        assert signature.startswith("0x")
        assert len(signature) == 132  # 0x + 65 bytes hex (130 chars)
        assert verify_consensus_message(message, signature, key_pair_a["address"]) is True

    def test_verify_fails_wrong_sender(self, key_pair_a: dict[str, str], key_pair_b: dict[str, str]) -> None:
        """Signature from key A should not verify against address B."""
        message = {"type": "vote", "voter": key_pair_a["address"], "vote": "for"}
        signature = sign_consensus_message(message, key_pair_a["private_key"])
        assert verify_consensus_message(message, signature, key_pair_b["address"]) is False

    def test_verify_fails_tampered_message(self, key_pair_a: dict[str, str]) -> None:
        """Tampering with the message after signing should fail verification."""
        message = {"key": "value", "number": 42}
        signature = sign_consensus_message(message, key_pair_a["private_key"])
        tampered = {"key": "value", "number": 43}
        assert verify_consensus_message(tampered, signature, key_pair_a["address"]) is False

    def test_verify_fails_empty_signature(self, key_pair_a: dict[str, str]) -> None:
        """Empty signature should fail verification."""
        message = {"key": "value"}
        assert verify_consensus_message(message, "", key_pair_a["address"]) is False

    def test_verify_fails_invalid_signature(self, key_pair_a: dict[str, str]) -> None:
        """Invalid signature hex should fail verification, not raise."""
        message = {"key": "value"}
        assert verify_consensus_message(message, "deadbeef", key_pair_a["address"]) is False

    def test_sign_pbft_message(self, key_pair_a: dict[str, str]) -> None:
        """Sign a realistic PBFT prepare message."""
        msg_data = PBFTMessageData(
            message_type=PBFTMessageType.PREPARE,
            sender=key_pair_a["address"],
            view_number=1,
            sequence_number=5,
            digest="0xblockhash",
            signature="",
            timestamp=time.time(),
        )
        # Sign the message dict (excluding signature field)
        signed_dict = msg_data.to_dict()
        signature = sign_consensus_message(signed_dict, key_pair_a["private_key"])
        assert verify_consensus_message(signed_dict, signature, key_pair_a["address"]) is True

    def test_sign_with_0x_prefix_key(self, key_pair_a: dict[str, str]) -> None:
        """Private key with 0x prefix should work."""
        priv = "0x" + key_pair_a["private_key"].removeprefix("0x")
        message = {"test": True}
        signature = sign_consensus_message(message, priv)
        assert verify_consensus_message(message, signature, key_pair_a["address"]) is True


# ---------------------------------------------------------------------------
# A1: sign_block_hash / verify_block_signature
# ---------------------------------------------------------------------------


class TestSignBlockHash:
    def test_round_trip_valid(self, key_pair_a: dict[str, str]) -> None:
        """Sign a block hash and verify it — should succeed."""
        block_hash = "0x" + "a" * 64  # 32-byte hash
        signature = sign_block_hash(block_hash, key_pair_a["private_key"])
        assert signature.startswith("0x")
        assert len(signature) == 132  # 0x + 65 bytes hex (130 chars)
        assert verify_block_signature(block_hash, signature, key_pair_a["address"]) is True

    def test_verify_fails_wrong_proposer(self, key_pair_a: dict[str, str], key_pair_b: dict[str, str]) -> None:
        """Block signed by A should not verify against B's address."""
        block_hash = "0x" + "b" * 64
        signature = sign_block_hash(block_hash, key_pair_a["private_key"])
        assert verify_block_signature(block_hash, signature, key_pair_b["address"]) is False

    def test_verify_fails_empty_signature(self, key_pair_a: dict[str, str]) -> None:
        """Empty signature should fail verification."""
        block_hash = "0x" + "c" * 64
        assert verify_block_signature(block_hash, "", key_pair_a["address"]) is False

    def test_verify_fails_invalid_signature_format(self, key_pair_a: dict[str, str]) -> None:
        """Invalid signature length should fail, not raise."""
        block_hash = "0x" + "d" * 64
        assert verify_block_signature(block_hash, "deadbeef", key_pair_a["address"]) is False

    def test_verify_fails_wrong_block_hash(self, key_pair_a: dict[str, str]) -> None:
        """Signature over hash A should not verify against hash B."""
        hash_a = "0x" + "a" * 64
        hash_b = "0x" + "b" * 64
        signature = sign_block_hash(hash_a, key_pair_a["private_key"])
        assert verify_block_signature(hash_b, signature, key_pair_a["address"]) is False

    def test_sign_without_0x_prefix(self, key_pair_a: dict[str, str]) -> None:
        """Block hash without 0x prefix should work."""
        block_hash = "a" * 64
        signature = sign_block_hash(block_hash, key_pair_a["private_key"])
        assert verify_block_signature(block_hash, signature, key_pair_a["address"]) is True

    def test_sign_key_without_0x_prefix(self, key_pair_a: dict[str, str]) -> None:
        """Private key without 0x prefix should work."""
        block_hash = "0x" + "e" * 64
        priv = key_pair_a["private_key"].removeprefix("0x")
        signature = sign_block_hash(block_hash, priv)
        assert verify_block_signature(block_hash, signature, key_pair_a["address"]) is True


# ---------------------------------------------------------------------------
# A2: PBFTMessageData
# ---------------------------------------------------------------------------


class TestPBFTMessageData:
    def test_to_dict_and_from_dict_round_trip(self) -> None:
        """to_dict → from_dict should preserve all fields."""
        msg = PBFTMessageData(
            message_type=PBFTMessageType.COMMIT,
            sender="0xsender",
            view_number=3,
            sequence_number=42,
            digest="0xdigest",
            signature="0xsig",
            timestamp=1234567890.0,
        )
        d = msg.to_dict()
        # to_dict doesn't include signature (it's provided separately for signing)
        assert "signature" not in d
        assert d["message_type"] == "commit"
        assert d["sender"] == "0xsender"
        assert d["view_number"] == 3
        assert d["sequence_number"] == 42
        assert d["digest"] == "0xdigest"
        assert d["timestamp"] == 1234567890.0

        # from_dict with signature
        msg2 = PBFTMessageData.from_dict(d, signature="0xsig")
        assert msg2.message_type == PBFTMessageType.COMMIT
        assert msg2.sender == "0xsender"
        assert msg2.view_number == 3
        assert msg2.sequence_number == 42
        assert msg2.digest == "0xdigest"
        assert msg2.signature == "0xsig"
        assert msg2.timestamp == 1234567890.0

    def test_from_dict_with_embedded_signature(self) -> None:
        """from_dict should read signature from dict if not provided separately."""
        d = {
            "message_type": "pre_prepare",
            "sender": "0x1",
            "view_number": 0,
            "sequence_number": 1,
            "digest": "0xabc",
            "timestamp": 1000.0,
            "signature": "0xsig123",
        }
        msg = PBFTMessageData.from_dict(d)
        assert msg.signature == "0xsig123"

    def test_all_message_types(self) -> None:
        """All PBFTMessageType values should round-trip through to_dict/from_dict."""
        for mt in PBFTMessageType:
            msg = PBFTMessageData(
                message_type=mt,
                sender="0x1",
                view_number=1,
                sequence_number=1,
                digest="0x1",
                signature="",
                timestamp=0.0,
            )
            d = msg.to_dict()
            msg2 = PBFTMessageData.from_dict(d)
            assert msg2.message_type == mt


# ---------------------------------------------------------------------------
# A2: ConsensusConfig
# ---------------------------------------------------------------------------


class TestConsensusConfig:
    def test_defaults(self) -> None:
        cfg = ConsensusConfig()
        assert cfg.enabled is False
        assert cfg.fault_tolerance == 1
        assert cfg.required_messages == 3
        assert cfg.view_change_timeout_seconds == 30
        assert cfg.consensus_round_timeout_seconds == 10
        assert cfg.validator_set_epoch_blocks == 7200
        assert cfg.slashing_enabled is True
        assert cfg.slashing_amount == 100.0
        assert cfg.byzantine_threshold == 3
        assert cfg.max_view_change_backoff_seconds == 300

    def test_custom_values(self) -> None:
        cfg = ConsensusConfig(
            enabled=True,
            fault_tolerance=2,
            required_messages=5,
            view_change_timeout_seconds=60,
        )
        assert cfg.enabled is True
        assert cfg.fault_tolerance == 2
        assert cfg.required_messages == 5
        assert cfg.view_change_timeout_seconds == 60


# ---------------------------------------------------------------------------
# A2: ValidatorInfo
# ---------------------------------------------------------------------------


class TestValidatorInfo:
    def test_defaults(self) -> None:
        vi = ValidatorInfo(address="0x1", stake=1000.0, reputation=0.9)
        assert vi.role == ValidatorRole.VALIDATOR
        assert vi.is_active is True
        assert vi.last_proposed == 0
        assert vi.epoch == 0

    def test_to_dict(self) -> None:
        vi = ValidatorInfo(
            address="0x1",
            stake=500.0,
            reputation=0.8,
            role=ValidatorRole.PROPOSER,
            is_active=True,
            last_proposed=100,
            epoch=5,
        )
        d = vi.to_dict()
        assert d["address"] == "0x1"
        assert d["stake"] == 500.0
        assert d["reputation"] == 0.8
        assert d["role"] == "proposer"
        assert d["is_active"] is True
        assert d["last_proposed"] == 100
        assert d["epoch"] == 5

    def test_all_roles(self) -> None:
        for role in ValidatorRole:
            vi = ValidatorInfo(address="0x1", stake=1.0, reputation=1.0, role=role)
            assert vi.role == role
            assert vi.to_dict()["role"] == role.value


# ---------------------------------------------------------------------------
# A2: SlashingEventData
# ---------------------------------------------------------------------------


class TestSlashingEventData:
    def test_to_dict(self) -> None:
        event = SlashingEventData(
            validator_address="0xvalidator",
            condition=SlashingCondition.DOUBLE_SIGN,
            evidence="Conflicting prepare messages in round 5",
            block_height=1000,
            timestamp=1234567890.0,
            slash_amount=50.0,
        )
        d = event.to_dict()
        assert d["validator_address"] == "0xvalidator"
        assert d["condition"] == "double_sign"
        assert d["evidence"] == "Conflicting prepare messages in round 5"
        assert d["block_height"] == 1000
        assert d["timestamp"] == 1234567890.0
        assert d["slash_amount"] == 50.0

    def test_all_conditions(self) -> None:
        for cond in SlashingCondition:
            event = SlashingEventData(
                validator_address="0x1",
                condition=cond,
                evidence="test",
                block_height=1,
                timestamp=0.0,
                slash_amount=1.0,
            )
            assert event.to_dict()["condition"] == cond.value


# ---------------------------------------------------------------------------
# A2: ConsensusStatus
# ---------------------------------------------------------------------------


class TestConsensusStatus:
    def test_to_dict(self) -> None:
        status = ConsensusStatus(
            mode="multi_validator",
            enabled=True,
            current_view=3,
            current_sequence=42,
            current_epoch=2,
            active_validators=4,
            total_validators=5,
            fault_tolerance=1,
            required_messages=3,
            slashing_events=2,
            view_changes=1,
            consensus_rounds=150,
        )
        d = status.to_dict()
        assert d["mode"] == "multi_validator"
        assert d["enabled"] is True
        assert d["current_view"] == 3
        assert d["current_sequence"] == 42
        assert d["current_epoch"] == 2
        assert d["active_validators"] == 4
        assert d["total_validators"] == 5
        assert d["fault_tolerance"] == 1
        assert d["required_messages"] == 3
        assert d["slashing_events"] == 2
        assert d["view_changes"] == 1
        assert d["consensus_rounds"] == 150

    def test_defaults_single_validator(self) -> None:
        status = ConsensusStatus(mode="single_validator", enabled=False)
        assert status.current_view == 0
        assert status.active_validators == 0
        assert status.consensus_rounds == 0
