"""CONSENSUS-PIN-DIGEST-1 (#1723): digest stability and sensitivity pins."""

from __future__ import annotations

import re

import pytest

from aitbc_chain.config import ChainSettings
from aitbc_chain.consensus_digest import consensus_config_digest, consensus_config_fields


def test_digest_is_stable_hex() -> None:
    digest = consensus_config_digest()
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert consensus_config_digest() == digest


def test_consensus_pin_change_moves_digest() -> None:
    """A different effective activation pin must change the digest — that is
    the whole point: partial arming becomes visible across validators."""
    base = ChainSettings()
    shifted = ChainSettings(state_transition_v4_height=base.state_transition_v4_height + 1)
    assert consensus_config_digest(base) != consensus_config_digest(shifted)


def test_flag_change_moves_digest() -> None:
    base = ChainSettings()
    flipped = ChainSettings(consensus_require_signed_attest_request=not base.consensus_require_signed_attest_request)
    assert consensus_config_digest(base) != consensus_config_digest(flipped)


def test_node_local_tuning_is_excluded() -> None:
    """Listener/sync tuning is node-local — including it would make correctly
    configured validators disagree. Only consensus prefixes feed the digest."""
    fields = consensus_config_fields()
    assert all(name.startswith(("state_transition_", "consensus_", "pbft_", "multi_validator_")) for name in fields)
    assert "attest_listener_stall_seconds" not in fields
    assert "mempool_entry_ttl" not in fields


def test_covered_set_includes_activation_pins() -> None:
    fields = consensus_config_fields()
    for pin in (
        "state_transition_v4_height",
        "state_transition_v12_height",
        "state_transition_v25_height",
        "consensus_domain_separation_height",
        "consensus_legacy_attestation_until_height",
    ):
        assert pin in fields


@pytest.mark.parametrize("bad", [None, ""])
def test_no_secret_looking_values(bad) -> None:
    """Covered fields are heights/flags/counts — nothing resembling a key."""
    for name, value in consensus_config_fields().items():
        assert not any(token in name for token in ("key", "secret", "private", "seed", "password"))
        if isinstance(value, str):
            assert len(value) < 64
