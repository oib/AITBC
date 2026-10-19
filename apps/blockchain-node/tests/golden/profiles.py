"""Gate-pin profiles the golden corpus is recorded and checked under.

``deployed`` pins every gate attribute to the value the live fleet runs today
(``/etc/aitbc/blockchain.env`` on the fleet: ``STATE_TRANSITION_V2_HEIGHT=0``,
``V3=5470``, ``V11=35400``, ``V12=37500``, ``BRIDGE_LOCK_LEAF_V2_HEIGHT=51000``;
every other gate takes its ``config.py`` default, which is what the chain ran).

``gates0`` sets every gate height to 0 — the ``bc-2`` configuration decided for
the reset. On unmodified code this is *not* "all rules on from genesis":
``get_block_version`` treats a falsy threshold as unset, so the height cascade
returns **1** at every height for an unstamped block (the proposer-side
``get_block_version_for_height`` would return 2), the v8 stamp-vs-height fork
never activates (its ``> 0`` gate fails), and a recorded
``state_transition_version`` stamp is therefore honoured at *every* height.
``bridge_lock_leaf_v2_height`` and ``escrow_fee_sweep_pass_min_height`` have
the opposite convention — a ``>=`` compare against the pin, so 0 activates
them from the first block. The corpus records exactly what the code does under
each profile; any bc-2 release that collapses the gates in code must still
match ``deployed`` on this corpus.
"""

from __future__ import annotations

# Every apply-relevant gate attribute on aitbc_chain.config.settings, in one
# place so a corpus run cannot silently pick up a code-default drift or a
# leaked deployment env file.
GATE_ATTRS: tuple[str, ...] = (
    "state_transition_v2_height",
    "state_transition_v3_height",
    "state_transition_v4_height",
    "state_transition_v5_height",
    "state_transition_v6_height",
    "state_transition_v7_height",
    "state_transition_v8_height",
    "state_transition_v9_height",
    "state_transition_v10_height",
    "state_transition_v11_height",
    "state_transition_v12_height",
    "state_transition_v13_height",
    "state_transition_v14_height",
    "bridge_lock_leaf_v2_height",
    "escrow_fee_sweep_pass_min_height",
)

DEPLOYED_PINS: dict[str, int] = {
    "state_transition_v2_height": 0,
    "state_transition_v3_height": 5470,
    "state_transition_v4_height": 11000,
    "state_transition_v5_height": 24000,
    "state_transition_v6_height": 0,
    "state_transition_v7_height": 24650,
    "state_transition_v8_height": 24800,
    "state_transition_v9_height": 30400,
    "state_transition_v10_height": 32100,
    "state_transition_v11_height": 35400,
    "state_transition_v12_height": 37500,
    "state_transition_v13_height": 46100,
    "state_transition_v14_height": 46100,
    "bridge_lock_leaf_v2_height": 51000,
    "escrow_fee_sweep_pass_min_height": 35400,
}

GATES0_PINS: dict[str, int] = dict.fromkeys(GATE_ATTRS, 0)

PROFILES: dict[str, dict[str, int]] = {
    "deployed": DEPLOYED_PINS,
    "gates0": GATES0_PINS,
}


def apply_profile(settings_obj: object, name: str) -> dict[str, int]:
    """Pin every gate attribute on ``settings_obj`` to the profile's value."""
    pins = PROFILES[name]
    for attr in GATE_ATTRS:
        setattr(settings_obj, attr, pins[attr])
    return dict(pins)
