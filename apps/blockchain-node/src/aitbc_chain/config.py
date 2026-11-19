from __future__ import annotations

import os
import uuid as uuid
from decimal import Decimal as Decimal
from pathlib import Path
from typing import Any as Any

from pydantic import BaseModel as BaseModel, Field as Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aitbc.constants import DATA_DIR

from .config_bridge import BridgeConfig
from .config_chain import SyncConfig
from .config_consensus import (
    _JOURNAL_DEPENDENT_FLAGS as _JOURNAL_DEPENDENT_FLAGS,
    ConsensusConfig,
    _abandon_gap_findings as _abandon_gap_findings,
    uc_combo_findings,
)
from .config_env import (
    _CHAIN_ENV_FILES,
    _chain_env_raw as _chain_env_raw,
    DEFAULT_ISLAND_ID as DEFAULT_ISLAND_ID,
    KEYSTORE_DIR as KEYSTORE_DIR,
    ProposerConfig as ProposerConfig,
    SHARED_ACTIVATION_HEIGHT,
    UC_TIMING_MARGIN_SECONDS as UC_TIMING_MARGIN_SECONDS,
    V13_HEIGHT_NOT_ARMED as V13_HEIGHT_NOT_ARMED,
)
from .config_infra import InfraConfig
from .config_node import NodeConfig


class ChainSettings(ConsensusConfig, InfraConfig, BridgeConfig, SyncConfig, NodeConfig, BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_CHAIN_ENV_FILES, env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # v0.25.7: historical state-transition rule changes are gated by block version.
    # New blocks set state_transition_version=2 in their metadata. Blocks that
    # lack the version key are treated as v1 if their height is below this value
    # and as v2 at or above it. Default 0 means all unversioned blocks are v1,
    # so new chains with no history work under v2 from the first produced block.
    state_transition_v2_height: int = 0
    # S-4: per-escrow custody (v3) activation height. New blocks at or above this
    # height set state_transition_version=3. Default 0 means v3 is not activated;
    # existing chains continue under v2 until the operator sets a positive height.
    state_transition_v3_height: int = 0
    # GAP-42 remainder: consensus-enforced stake lock windows (v4). At or above
    # this height, STAKE_RELEASE txs must name their lock tx hashes and the
    # locks must have matured. Hardcoded rather than env-dependent because the
    # activation is itself consensus: an env-drifted fleet would fork. The
    # proposer stamps it into block_metadata and followers replay that stamp.
    state_transition_v4_height: int = 11000
    # Fail-closed authority gates (v5). At or above this height,
    # ESCROW_RELEASE/ESCROW_REFUND require a configured settlement authority,
    # GOVERNANCE_EXECUTE requires the governance_executors chain parameter, and
    # BRIDGE_RELEASE/BRIDGE_REFUND must carry the bridge pseudo-sender. Below it
    # the same checks stay lenient so sealed history replays. Hardcoded like
    # v4 — the activation is itself consensus — so keep it ahead of the chain
    # head until every fleet node runs a build that knows the rules.
    state_transition_v5_height: int = 24000
    # v6: a BRIDGE_REFUND must name the sealed BRIDGE_LOCK it repays on the same
    # chain (payload.lock_tx_hash, sender/amount match, not already refunded).
    # Below it refunds stay lenient for replay. Unlike v5 this is env-gated
    # (STATE_TRANSITION_V6_HEIGHT) rather than baked — set it uniformly on
    # every node once the fleet runs a build that enforces it; fleet-config-check
    # watches for drift. 0 disables the gate.
    state_transition_v6_height: int = 0
    # v7: a GPU_REGISTER for an existing gpu_id must come from the registrant
    # recorded on that row (registered_by = the first registrant's tx sender).
    # Below it any funded account could overwrite another provider's GPU
    # registration; replay keeps that lenient behavior. Activated fleet-wide
    # at block 24650 on 2026-09-26 and verified across a full proposer
    # rotation, so the height is now consensus and is hardcoded like v4/v5 —
    # a lost env file must not re-open the overwrite rule.
    state_transition_v7_height: int = 24650
    # v8: stamped-version integrity. At or above this height a block's
    # recorded block_metadata.state_transition_version becomes advisory —
    # validation always uses the height-derived version, and a mismatched or
    # missing stamp is logged + counted (block_version_stamp_mismatch_total)
    # rather than obeyed or rejected. block_metadata is covered by neither
    # the block hash nor the proposer signature, so trusting the stamp would
    # let any relay pick the rules a block is validated under. Below this
    # height the stamp stays proposer-controlled and trusted (pre-v8
    # semantics); the fleet audit showed every recorded stamp matches its
    # height-derived version, so no historical block is affected. Activated
    # fleet-wide at block 24800 on 2026-09-26 and proven over a full
    # rotation plus node0's range-sync import, so the height is now
    # consensus and hardcoded like v4/v5/v7 — a lost env file must not
    # silently return a node to trusting the recorded stamp.
    state_transition_v8_height: int = 24800
    # v9: transaction authorization. At or above this height every
    # user-originated transaction must carry a valid sender signature at
    # apply time (V9_UNSIGNED_ALLOWED_TX_TYPES in state/v9_policy.py are
    # the only unsigned exceptions, each with its own authority check),
    # served block transactions carry the stored signed envelope, and
    # attesters verify tx signatures + nonce order against their own
    # parent state before signing. None means v9 is NOT activated: the
    # same rules still evaluate in shadow mode — every would-reject logs
    # and counts v9_would_reject_*_total instead of rejecting, so the
    # allowlist can be proven complete against live traffic. Activated
    # fleet-wide at block 30400 on 2026-09-30 after a >24h clean shadow
    # window and a nine-type canary sweep with zero substantive
    # v9_would_reject counters, so the height is now consensus and is
    # hardcoded like v4/v5/v7/v8.
    state_transition_v9_height: int | None = 30400
    # v10: GPU_DEREGISTER. At or above this height the registrant of a gpu_registration row can set it to
    # ``deactivated`` with a signed GPU_DEREGISTER; GPU_ALLOCATE against a deactivated row is refused. Below
    # it the type name has no consensus meaning at all and a block carrying it replays exactly as before (a
    # plain value transfer), so sealed history is untouched; None still disables it the same way. Every
    # validator and follower must run a build that knows the type BEFORE this height: an older build leaves
    # the row ``active`` and would accept a later GPU_ALLOCATE the new rules refuse. Activated fleet-wide
    # at block 32100 on 2026-10-02, proven over a full proposer rotation and the first live GPU_REGISTER /
    # GPU_DEREGISTER sealed under it (blocks 32803/32804), so the height is now consensus and is hardcoded
    # like v4 to v9. An environment value (STATE_TRANSITION_V10_HEIGHT) still overrides this default.
    # fleet-config-check watches for drift.
    state_transition_v10_height: int | None = 32100
    # v11: ESCROW_FEE_SWEEP. At or above this height the settlement authority may sweep a settled escrow's
    # custody residue — the withheld platform fee plus rounding dust that v3 custody strands in the
    # per-escrow account — to the recipient pinned by the on-chain ``escrow_fee_recipient`` chain parameter
    # (env fallback ESCROW_FEE_RECIPIENT, unset fails closed). Apply-time rules: payload.job_id names the
    # custody account, sender must equal ``escrow_settlement_authority`` resolved at apply height, recipient
    # must equal the resolved fee recipient, and value is bounded only by the custody balance — the same
    # trust bound the authority already holds over each release's amount. Below this height the type name
    # has no consensus meaning at all and a block carrying it replays exactly as before (a plain value
    # transfer), so sealed history is untouched; None still disables it the same way. Every validator and
    # follower must run a build that knows the type BEFORE this height: an older build would apply a sealed
    # sweep as a plain transfer and diverge. Activated fleet-wide at block 35400 on 2026-10-05 — all five
    # hosts agreed on the transition block's hash and production continued cleanly past it — so the height
    # is now consensus and is hardcoded like v4 to v10. An environment value (STATE_TRANSITION_V11_HEIGHT)
    # still overrides this default. fleet-config-check watches for drift.
    state_transition_v11_height: int | None = 35400
    # v12: authority-parameter value checks. At or above this height a GOVERNANCE_EXECUTE ``parameter_change``
    # to one of the five authority chain parameters (governance_executors, bond_slash_authority,
    # bridge_release_authority, escrow_settlement_authority, escrow_fee_recipient) must carry a well-formed
    # value: non-empty, every comma-separated element a canonical 0x+40-hex address, no zero address, no
    # duplicates after canonicalisation, at most one element for the four single-address parameters, and —
    # for governance_executors — at least one member holding the baked executor minimum (DEFAULT_TX_FEE_UNITS,
    # the lowest balance that can pay a fee; decided as a constant, not the tx's fee, because consensus has no
    # minimum fee). Below the height a malformed value seals exactly as before (B9: a typo'd, empty or
    # never-funded executor list seals and freezes all parameters), so sealed history is untouched; None still
    # disables it the same way. Every validator and follower must run a build that enforces the checks BEFORE
    # this height: an older build would seal a transaction the fleet rejects and diverge. Activated fleet-wide
    # at block 37500 — STATE_TRANSITION_V12_HEIGHT=37500 was set on all five hosts and block 37500 stamped
    # version 12 — so the height is now consensus and is hardcoded like v4 to v11. An environment value
    # (STATE_TRANSITION_V12_HEIGHT) still overrides this default. fleet-config-check watches for drift.
    state_transition_v12_height: int | None = 37500
    # v13 (V-2): GOVERNANCE_EXECUTE applies the sealed GOVERNANCE_PROPOSE's
    # stored execution_payload; an execute naming no earlier-sealed proposal —
    # or carrying a payload that differs from it — is refused in admission and
    # block verification, and a GOVERNANCE_PROPOSE must carry the
    # execution_payload it commits to. Default: SHARED_ACTIVATION_HEIGHT (the
    # shared ACT-1 activation). STATE_TRANSITION_V13_HEIGHT overrides it;
    # V13_HEIGHT_NOT_ARMED parks the rules as dead code.
    state_transition_v13_height: int | None = SHARED_ACTIVATION_HEIGHT
    # v14 (V-3 + V-4, same shared ACT-1 height): block headers carry
    # aux_state_root — the fingerprint over the 13 committed side tables
    # after the block's transactions apply — bound into the block hash and
    # verified at import; and a BRIDGE_LOCK carrying no derivable leaf data
    # is refused in apply instead of only counted by the dry-run guard.
    # STATE_TRANSITION_V14_HEIGHT overrides it; V13_HEIGHT_NOT_ARMED parks
    # the rules as dead code. Both thresholds move together: the STOP-rule
    # "move H" path sets both on every host.
    state_transition_v14_height: int | None = SHARED_ACTIVATION_HEIGHT
    # v15 (EDGE-REG-CONSENSUS-1, operator card 21 Oct): ``edge_node_registration``
    # leaves the committed side-table set — ``committed_fingerprint`` covers 12
    # tables at/after this height instead of 13. The v14 set stays frozen for
    # replay of already-sealed eras. ``None`` (the default) keeps the rule
    # unarmed: the activation height is a separate operator pin, set on every
    # host together with the validator restart wave — a mid-rollout mixed set
    # would reject blocks as aux_state_root mismatches.
    state_transition_v15_height: int | None = None
    # v16 (GPU-ADMISSION-1 #384, operator ruling 24 Oct — multisig-accounts moves
    # to v17 if it lands second): GPU_ALLOCATE must name ``allocation_id`` and an
    # existing ``gpu_id`` at validation, not only at apply. ``None`` (the
    # default) keeps the rule unarmed: the activation height is a separate
    # operator pin, set on every host together with the validator restart wave.
    state_transition_v16_height: int | None = None
    # v17 (BNT-1 revival, operator ruling 28 Oct — multisig-accounts moves to
    # v18): the v9 signature rule additionally admits ``STAKE_LOCK``,
    # ``STAKE_RELEASE``, ``BOUNTY_LOCK``, ``BOUNTY_PAYOUT`` and
    # ``BOUNTY_REFUND`` carrying a well-formed ``payload.auth`` in place of a
    # top-level sender signature — the keyless protocol escrow cannot sign and
    # the auth is re-verified for binding immediately after (option 1 of
    # docs/design/v9-unsigned-protocol-transfers.md). HTLC_* and unsigned
    # AUTO_STAKE stay dead (they emit no auth). The height is code-pinned at
    # 8900 — the bc-2 activation (fleet wave 28 Oct, operator card 4A): a
    # permanent historical gate belongs in code like the v4-v14 literals,
    # not in driftable env pins. ``None`` keeps the rule unarmed for a chain
    # that wants it deferred; per-chain env still overrides the literal.
    state_transition_v17_height: int | None = 8900
    # v18 (deterministic committed apply — remediates
    # docs/design/v14-aux-root-nondeterminism.md): at/after this height the
    # apply output is a pure function of (transaction, prior state, block
    # header) — ``stake`` leaves the committed side-table set, liquidity
    # stake ids derive from ``tx_hash`` (``liq_<tx_hash[:16]>``) instead of
    # ``secrets.token_hex``, and every ``datetime.now(UTC)`` on the apply
    # path (locked_until, accrual elapsed, bond verdict) is replaced by the
    # sealed header timestamp. ``None`` (the default) keeps the rule
    # unarmed: the activation height is a separate operator pin, set on
    # every host together with the validator restart wave — a mid-rollout
    # mixed set would reject blocks as aux_state_root mismatches.
    state_transition_v18_height: int | None = (
        9600  # armed 9600 fleet-wide 2026-10-28 (env pin -> literal per the v17 pattern); None keeps the rule unarmed for future configs; per-chain env still overrides
    )
    # v19 (BOND-LOCK-TOPUP-SLASHED-1, #782): at/after this height validate and
    # admission refuse a ``BOND_LOCK`` top-up whose existing bond row is not
    # ``status=active`` — topping up a slashed/released bond used to raise
    # ``amount`` while the row kept its terminal status, stranding the funds
    # (release and slash both require ``active``). ``None`` (the default) keeps
    # the rule unarmed: the activation height is a separate operator pin, set
    # on every host together with the validator restart wave.
    state_transition_v19_height: int | None = None
    state_transition_v20_height: int | None = None
    # v21 (AGENT-SPEND-B-1, #1142): on-chain agent spend sessions. At/after
    # this height ``AGENT_SESSION_GRANT``/``AGENT_SESSION_REVOKE`` manage the
    # ``agent_spend_session`` table, session-bound senders must name a live
    # ``payload.session_id`` on TRANSFER/ESCROW_LOCK, and spends accrue to the
    # ``agent_spend_ledger`` day bucket (height // 1290) inside the same apply
    # transaction. Both tables join the committed fingerprint set at v21.
    # ``None`` (the default) keeps the rule unarmed: the activation height is
    # a separate operator pin, set on every host together with the validator
    # restart wave — a mid-rollout mixed set would apply different session
    # rules and fork.
    state_transition_v21_height: int | None = None
    # v22 (BOND-RELEASE-001, BOND-LOCK-TOPUP-PROVIDER-MISMATCH, #1166/#1167):
    # bond ownership bound to the persisted provider (mandatory
    # payload.provider == signer == bond.provider), the absolute lock
    # ceiling ``min(now + lock_days, created_at + 3650d)`` with
    # post-ceiling top-ups refused, and NULL locked_until failing closed
    # on release. The 3650-day horizon is a compile-time protocol
    # constant (PROTOCOL_MAX_LOCK_DURATION) — never env/config-driven.
    # ``None`` (the default) keeps the rule unarmed: the activation
    # height is a separate operator pin, set on every host together with
    # the validator restart wave.
    state_transition_v22_height: int | None = None
    # v23 (R12-05-F1/#1232 + R14-06-F1/#1230): escrow obligation bound.
    # ESCROW_RELEASE/ESCROW_REFUND value is capped by the job's remaining
    # obligation (Σ ESCROW_LOCK.value − Σ prior release/refund.value,
    # tx-derived); ESCROW_FEE_SWEEP is capped by custody − remaining
    # obligation (residue only). Locks/settlements with unparseable value
    # fail closed as unbounded obligation. ``None`` keeps the rule
    # unarmed: activation height is an operator pin set fleet-wide with
    # the restart wave — a mid-rollout mixed set would apply different
    # settlement rules and fork.
    state_transition_v23_height: int | None = None
    # v24 (#1314 R1/R2): stale-state and proposer/importer parity fixes —
    # central identity-map invalidation after raw-SQL writes, authoritative
    # reads at the V-site inventory, and Transaction-row visibility parity
    # between proposer and importer. ``None`` (the default) keeps every
    # rule unarmed: the activation height is an operator pin set fleet-wide
    # with the restart wave — a mid-rollout mixed set would apply different
    # state rules and fork. Second independent boundary per AD ruling: the
    # existing v23 ruleset stays untouched; v24 activates only the #1314
    # changes on top of it.
    state_transition_v24_height: int | None = None
    # v25 (#1566): GPU_REGISTER price_per_hour bounds — the payload price must
    # be a finite Decimal in [0, Numeric(20,8) max] at validate AND apply.
    # ``None`` (the default) keeps every rule unarmed: the activation height is
    # an operator pin set fleet-wide with the restart wave — a mid-rollout
    # mixed set would apply different state rules and fork, and an unguarded
    # bound would diverge replay of any historical block carrying an
    # out-of-range price.
    state_transition_v25_height: int | None = None
    # v26 (#2186 DEV3-BLOCK-SCOPED-RUNG-1): at or above this height the
    # pre-registered bridge mutations (BRIDGE_LOCK debit, BRIDGE_RELEASE /
    # BRIDGE_REFUND credit) are deferred to block apply *unconditionally* —
    # the rule becomes a property of the block version instead of the
    # process-local ``block_scoped_preregistered_transactions`` setting.
    # ``None`` (the default) leaves the setting in charge at every height, so
    # this is byte-identical to pre-rung behaviour (the fleet runs the setting
    # true and construction refuses env-false). Activation is a separate
    # operator pin set fleet-wide with a restart wave.
    state_transition_v26_height: int | None = None
    # v27 (#2252 BRIDGE-SIG-NONCE-OVERRIDE-1): at or above this height a tx
    # carrying a ``bridge_signature`` (BRIDGE_LOCK) keeps its signed envelope
    # nonce at apply instead of having it rewritten to the account's live
    # nonce — the authority signature binds that nonce, so the rewrite made a
    # second lock sharing a nonce (block-scoped preregistration) fail
    # verification after the first sealed. ``None`` (the default) keeps the
    # rewrite at every height: byte-identical to pre-rung behaviour and to
    # historical replay. Activation is a separate operator pin set fleet-wide
    # only after every validator runs the code — a mixed set would apply
    # different rules and fork.
    state_transition_v27_height: int | None = None
    # #1298 I3b domain separation: at or above this height, block-proposal
    # and block-attestation signatures use domain-separated preimages
    # (aitbc-consensus-v1:block_proposal / :block_attestation) so a signature
    # minted for one purpose can never verify for the other. ``None`` keeps
    # every sign/verify path byte-identical to pre-activation (historical
    # replay preserved). Activation is an operator pin set fleet-wide only
    # after all nodes run a build that understands the new preimages —
    # a mixed fleet would refuse each other's signatures and fork.
    consensus_domain_separation_height: int | None = None
    # #1298 dual-accept migration window (design v2.2 CARD5 / v2.6): while the
    # message height sits in [consensus_domain_separation_height, this value),
    # ATTESTATION-channel verification accepts EITHER the domain-separated
    # preimage or the legacy shared preimage, so stragglers still minting
    # pre-domain signatures keep counting while the fleet converges. At
    # heights >= this value only the domain preimage verifies; below the
    # activation height only the legacy preimage does (unchanged). The gate
    # is height-derived, never wall-clock. ``None`` (the default) opens no
    # window — legacy attestations verify only below the activation height
    # (hard cutover). A value <= the activation height is an empty window,
    # equivalent to unset. Proposal signatures NEVER dual-accept: at/above
    # the activation height they require the proposal domain regardless of
    # this setting.
    consensus_legacy_attestation_until_height: int | None = None

    def get_db_path(self, chain_id: str = "") -> Path:
        """Get database path for a specific chain.

        Args:
            chain_id: Chain ID to get path for. If empty, uses self.chain_id or default.

        Returns:
            Path to chain-specific database file.
        """
        # Resolve chain_id: parameter > settings > environment > empty
        resolved_chain_id = chain_id or self.chain_id or os.getenv("CHAIN_ID", "")

        # The "legacy path" fallback that used to sit here was `Path("/var/lib/aitbc/data") /
        # chain_id / "chain.db"` -- byte for byte what this expression produced, since DATA_DIR
        # was that literal. It could never be reached. Now that DATA_DIR follows
        # AITBC_DATA_DIR, keeping it would have been worse than dead: a run pointed at a
        # temporary directory would have fallen back to the deployed one (V23-73).
        return DATA_DIR / "data" / resolved_chain_id / "chain.db"

    @model_validator(mode="after")
    def _default_supported_chains(self) -> ChainSettings:
        """Default supported_chains to chain_id when empty.

        Without this, when SUPPORTED_CHAINS is unset the island ID is
        constructed as ``"-island"`` (empty string + suffix). Defaulting
        to ``chain_id`` produces a valid island ID like
        ``"ait-localnet-island"``.
        """
        if not self.supported_chains.strip():
            self.supported_chains = self.chain_id
        return self

    @model_validator(mode="after")
    def _pin_block_scoped_preregistered_transactions(self) -> ChainSettings:
        """Refuse ``BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=false`` at startup.

        The non-block-scoped bridge path writes committed tables (``account``,
        ``transaction``) directly, outside block apply — the pre-v14 behaviour
        the flag replaced. An env flip on a live node silently re-opens that
        committed-write escape with no check able to see it, so it is refused
        here rather than warned. The legacy path survives only as a test
        mode: tests patch the attribute post-construction (no
        ``validate_assignment``), never via env.
        """
        if not self.block_scoped_preregistered_transactions:
            raise ValueError(
                "block_scoped_preregistered_transactions=false is refused: the "
                "non-block-scoped bridge path mutates committed tables outside "
                "block apply (test-only via monkeypatched settings)"
            )
        return self

    @classmethod
    def get_genesis_candidates(cls, chain_id: str) -> list[str]:
        """Get genesis file candidates for a specific chain ID"""
        return [
            str(DATA_DIR / "data" / "genesis.json"),
            f"{DATA_DIR}/data/{chain_id}/genesis.json",
            f"{DATA_DIR}/data/{os.getenv('CHAIN_ID', '')}/genesis.json",
        ]

    @field_validator("chain_configs", mode="before")
    @classmethod
    def parse_chain_configs(cls, v: dict[str, str] | str) -> dict[str, str]:
        """Validate chain_configs dict. Values are raw config strings
        parsed later by ChainConfigParser at point of use."""
        if not v:
            return {}
        if isinstance(v, str):
            import json

            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                raise ValueError(f"chain_configs must be a dict or JSON string, got: {v}") from None
            if not isinstance(parsed, dict):
                raise ValueError(f"chain_configs must parse to a dict, got: {type(parsed)}") from None
            v = parsed
        # Validate each value is a non-empty string
        from aitbc.utils.chain_config import ChainConfigParser

        for chain_id, config_str in v.items():
            if not isinstance(config_str, str):
                raise ValueError(f"chain_configs['{chain_id}'] must be a string, got: {type(config_str)}")
            if config_str.strip():
                ChainConfigParser.parse(config_str)
        return v

    @field_validator("chain_sync_sources")
    @classmethod
    def validate_chain_sync_sources(cls, v: str) -> str:
        """Fail fast on malformed CHAIN_SYNC_SOURCES at startup (v0.6.3)."""
        if not v or not v.strip():
            return v
        seen: set[str] = set()
        for pair in v.split(","):
            pair = pair.strip()
            if not pair:
                continue
            parts = pair.split(":", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid CHAIN_SYNC_SOURCES entry: '{pair}'. Expected 'chain_id:url'")
            chain_id, url = parts[0].strip(), parts[1].strip()
            if not chain_id or not url:
                raise ValueError(f"Invalid CHAIN_SYNC_SOURCES entry: '{pair}'. Empty chain_id or url")
            if chain_id in seen:
                raise ValueError(f"Duplicate chain_id in CHAIN_SYNC_SOURCES: '{chain_id}'")
            seen.add(chain_id)
        return v

    @field_validator("island_registry")
    @classmethod
    def validate_island_registry(cls, v: str) -> str:
        """Fail fast on malformed ISLAND_REGISTRY at startup (v0.6.3)."""
        if not v or not v.strip():
            return v
        seen: set[str] = set()
        for entry in v.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) < 3:
                raise ValueError(f"Invalid ISLAND_REGISTRY entry: '{entry}'. Expected 'island_id:chain_id:hub_url'")
            island_id = parts[0].strip()
            if not island_id:
                raise ValueError(f"Invalid ISLAND_REGISTRY entry: '{entry}'. Empty island_id")
            if island_id in seen:
                raise ValueError(f"Duplicate island_id in ISLAND_REGISTRY: '{island_id}'")
            seen.add(island_id)
        return v

    @field_validator("gossip_backends")
    @classmethod
    def validate_gossip_backends(cls, v: str) -> str:
        """Fail fast on malformed GOSSIP_BACKENDS at startup (v0.6.3)."""
        if not v or not v.strip():
            return v
        seen: set[str] = set()
        for entry in v.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid GOSSIP_BACKENDS entry: '{entry}'. Expected 'chain_id:redis://url'")
            chain_id = parts[0].strip()
            if not chain_id:
                raise ValueError(f"Invalid GOSSIP_BACKENDS entry: '{entry}'. Empty chain_id")
            if chain_id in seen:
                raise ValueError(f"Duplicate chain_id in GOSSIP_BACKENDS: '{chain_id}'")
            seen.add(chain_id)
        return v

    @field_validator("bridge_islands")
    @classmethod
    def validate_bridge_islands(cls, v: str) -> str:
        """Validate bridge_islands CSV format: UUIDs only, no spaces, no empty entries (v0.6.3)."""
        if not v or not v.strip():
            return v
        islands = [i.strip() for i in v.split(",") if i.strip()]
        if len(islands) != len(set(islands)):
            raise ValueError(f"Duplicate island_id in bridge_islands: '{v}'")
        for island_id in islands:
            if " " in island_id:
                raise ValueError(f"Invalid bridge_islands entry: '{island_id}'. No spaces allowed (use UUID format)")
        return v

    @model_validator(mode="after")
    def _scale_the_proposer_round_to_the_heartbeat(self) -> ChainSettings:
        """Size the round window from the heartbeat unless it was set explicitly.

        The window has to clear the longest gap a healthy network leaves
        between blocks, or an ordinary late block is attributed to the next
        round and its proposer is skipped. That gap is set by
        ``max_empty_block_interval``, so a constant here and a per-deployment
        heartbeat there are free to drift apart -- and had: 300s against the
        deployed 60s heartbeat, on a chain measured producing a block every
        62-72s, meant a validator going dark cost five minutes on every height
        it owned. Aligning the round with the heartbeat (rather than 2x) means
        a silent proposer is skipped within one heartbeat cycle instead of two.
        """
        if "consensus_proposer_round_seconds" not in self.model_fields_set:
            # Align the round window with the heartbeat interval, not 2x it.
            # The C-2 live exercise found that a 120s round vs 60s heartbeat
            # stalls the chain for 2 full heartbeats when a proposer is silent,
            # because the round does not advance until 120s but the heartbeat
            # fires at 60s — and the heartbeat cannot be produced because the
            # round-0 proposer is the one that is dead. Setting the round to
            # the heartbeat interval means the round advances at the same
            # moment the heartbeat would fire, handing the slot to the next
            # validator within one heartbeat cycle.
            self.consensus_proposer_round_seconds = max(30, self.max_empty_block_interval)
        return self

    @model_validator(mode="after")
    def _resolve_validate_signatures(self) -> ChainSettings:
        """If SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL is a future timestamp, disable validation.

        Both outcomes are logged. Turning proposer-signature validation off is a
        security-relevant change that used to happen silently, so a stale value
        left over from a past migration was invisible; a malformed value fails
        closed, which is the safe direction but is just as easy to miss.

        In production the kill-switch is additionally horizon-limited: a
        skip-until more than 48h out is almost certainly an operator mistake
        or a leftover from a long-forgotten incident, so the node refuses to
        start rather than run with signature validation off indefinitely.
        """
        if not self.sync_validate_signatures or not self.sync_validate_signatures_skip_until:
            return self
        # Imported locally: this validator runs while the module is still being
        # imported, before aitbc_chain.logger can be safely pulled in.
        import logging

        from aitbc.utils.env import is_production

        logger = logging.getLogger(__name__)
        try:
            from datetime import UTC, datetime, timedelta

            skip_until = datetime.fromisoformat(self.sync_validate_signatures_skip_until)
            # Naive timestamps are read as UTC — a naive/aware comparison would
            # otherwise raise TypeError outside the ValueError guard below.
            if skip_until.tzinfo is None:
                skip_until = skip_until.replace(tzinfo=UTC)
        except ValueError:
            logger.warning(
                "SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL=%r is not a valid ISO timestamp; "
                "leaving block proposer signature validation ENABLED",
                self.sync_validate_signatures_skip_until,
            )
            return self
        if datetime.now(UTC) >= skip_until:
            return self
        horizon = skip_until - datetime.now(UTC)
        if is_production() and horizon > timedelta(hours=48):
            raise ValueError(
                "SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL="
                f"{self.sync_validate_signatures_skip_until} disables block proposer signature "
                f"validation for {horizon.days} days; production nodes may skip at most 48h"
            )
        self.sync_validate_signatures = False
        logger.warning(
            "Block proposer signature validation is DISABLED by "
            "SYNC_VALIDATE_SIGNATURES_SKIP_UNTIL=%s; it re-enables itself after that time",
            self.sync_validate_signatures_skip_until,
        )
        return self

    @model_validator(mode="after")
    def _guard_unsafe_uc_flag_combinations(self) -> ChainSettings:
        """Refuse (production) or warn about UC flag combinations measured to freeze the chain (#1722).

        Non-consensus: it reads settings only and changes no default. Source: the #1301
        armed-combo matrix (c29699).

        TEMPORARY -- remove or invert when ``unavail_prewarm_enabled`` (#1701) lands. Prewarm
        stamps the header after the UC wait, which makes the evidence + collect window
        independent of ``attestation_header_max_age_seconds``; until then the bound below is
        what keeps an armed UC from refusing every attestation as ``stale_header``.
        """
        import logging

        from aitbc.utils.env import is_production

        errors, warnings = uc_combo_findings(self)
        logger = logging.getLogger(__name__)
        for message in warnings:
            logger.warning("UC flag guard: %s", message)
        if errors and is_production():
            raise ValueError("unsafe UC flag combination: " + "; ".join(errors))
        for message in errors:
            logger.warning("UC flag guard (refused in production): %s", message)
        return self

    def served_chain_ids(self) -> list[str]:
        """Chains this process claims to serve (``supported_chains`` CSV).

        ``supported_chains`` already defaults to ``chain_id`` when empty, so
        this is never empty on a configured node. Serving a chain still
        requires a resolvable gossip backend — see ``gossip_backend_map``.
        """
        chains = [c.strip() for c in self.supported_chains.split(",") if c.strip()]
        if not chains and self.chain_id:
            chains = [self.chain_id]
        return chains

    def gossip_shared_validator_chain_ids(self) -> set[str]:
        """Chains that deliberately share the default ``VALIDATOR_SET`` (#1259 opt-in)."""
        return {c.strip() for c in self.gossip_shared_validator_chains.split(",") if c.strip()}

    def gossip_backend_map(self) -> dict[str, str]:
        """Parsed ``GOSSIP_BACKENDS`` as ``{chain_id: url}`` (empty entries dropped).

        Entries use the ``chain_id:<url>`` grammar validated by
        ``validate_gossip_backends``; the URL may itself contain colons
        (``redis://host:port``), so only the FIRST colon separates the pair.
        """
        backends: dict[str, str] = {}
        for entry in self.gossip_backends.split(","):
            entry = entry.strip()
            if not entry:
                continue
            chain_id, _, url = entry.partition(":")
            chain_id = chain_id.strip()
            url = url.strip()
            if chain_id and url:
                backends[chain_id] = url
        return backends

    @staticmethod
    def _mesh_peer_chain_tag(entry: str) -> tuple[str | None, str]:
        """Split a ``GOSSIP_MESH_PEER_URLS`` entry into ``(chain_id, url)``.

        A chain tag is either a ``<chain_id>:`` prefix (mirroring
        ``GOSSIP_BACKENDS``; the prefix is whatever precedes the first colon
        when the entry does not start with a URL scheme, so tags for chains
        this process does not serve are simply never returned) or a
        ``?chain=<id>`` query parameter in the URL. Untagged entries return
        ``(None, entry)``. The returned URL keeps its ``?chain=`` query
        intact — the dialer preserves or re-derives it — while a
        ``<chain_id>:`` prefix is stripped.
        """
        import re

        if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", entry):
            prefix, sep, rest = entry.partition(":")
            if sep and prefix.strip():
                return prefix.strip(), rest.strip()
        if "?" in entry or "&" in entry:
            from urllib.parse import parse_qs, urlsplit

            parts = urlsplit(entry)
            chain = parse_qs(parts.query).get("chain", [None])[0]
            if chain:
                return chain.strip() or None, entry
        return None, entry

    def mesh_peer_urls_for_chain(self, chain_id: str | None) -> list[str]:
        """Peer URLs for one chain from ``GOSSIP_MESH_PEER_URLS``.

        ``chain_id=None`` returns only UNTAGGED entries — the default chain's
        mesh. Tagged entries (``?chain=<id>`` or ``<chain_id>:`` prefix) are
        consumed by the per-chain broker registry (#1159) and must not leak
        into another chain's peer set.
        """
        urls: list[str] = []
        for raw in self.gossip_mesh_peer_urls.split(","):
            entry = raw.strip()
            if not entry:
                continue
            tag, url = self._mesh_peer_chain_tag(entry)
            if tag == chain_id:
                urls.append(url)
        return urls

    def mesh_peer_url_list(self) -> list[str]:
        """Parsed ``GOSSIP_MESH_PEER_URLS`` (empty entries dropped).

        Untagged entries only — chain-tagged peers belong to their own
        chain's broker registry entry (#1159).
        """
        return self.mesh_peer_urls_for_chain(None)

    def mesh_peer_urls_for_service(self, chain_id: str | None) -> list[str]:
        """Peer URLs a service path should dial for ``chain_id`` (#1260).

        Strict convention (Director ruling on #1260): the default chain's
        peers are the UNTAGGED ``GOSSIP_MESH_PEER_URLS`` entries; any other
        chain's peers are the entries tagged with that chain (``<chain>:``
        prefix or ``?chain=<id>``). ``chain_id=None`` resolves to the default
        chain. This is the same split ``_backend_for_chain`` applies to the
        gossip broker registry.
        """
        if chain_id is None or chain_id == self.chain_id:
            return self.mesh_peer_url_list()
        return self.mesh_peer_urls_for_chain(chain_id)

    def gpu_retired_id_set(self) -> frozenset[str]:
        """Parsed ``GPU_RETIRED_IDS`` (empty entries dropped)."""
        return frozenset(i.strip() for i in self.gpu_retired_ids.split(",") if i.strip())


settings = ChainSettings()


def legacy_attestation_dual_accept_open(height: int | None, cfg: ChainSettings = settings) -> bool:
    """#1298: whether ``height`` sits inside the bounded dual-accept window.

    True iff both ``consensus_domain_separation_height`` (H) and
    ``consensus_legacy_attestation_until_height`` (S) are armed and
    ``H <= height < S``. Inside the window attestation-channel verification
    accepts legacy shared-preimage signatures alongside domain-separated
    ones; at ``height >= S`` (or when S is unset) only the domain preimage
    verifies at/above H, and below H only the legacy preimage does.
    Proposal verification never consults this — it has no dual-accept.
    """
    if height is None:
        return False
    activation = cfg.consensus_domain_separation_height
    until = cfg.consensus_legacy_attestation_until_height
    if activation is None or until is None:
        return False
    return activation <= height < until


def bridge_header_signature_domains(height: int | None, channel: str, cfg: ChainSettings = settings) -> list[str | None]:
    """#1521: preimages a bridge proof's header-message signatures may verify under.

    Bridge proofs carry the sealed block's consensus signature plus validator
    attestations over the same canonical header message. Since #1298 those
    are domain-separated at/above ``consensus_domain_separation_height``:
    the proposer signature lives under ``DOMAIN_BLOCK_PROPOSAL`` and
    validator attestations under ``DOMAIN_BLOCK_ATTESTATION`` — inside the
    bounded dual-accept window legacy attestation preimages still verify.
    Below the activation height, or while it is unset, only the legacy
    preimage is valid — byte-identical to pre-#1298 behaviour.

    ``channel`` is ``"proposal"`` (the block's own signature — hard cutover,
    no dual-accept, mirroring consensus) or ``"attestation"`` (validator
    signatures — dual-accept inside the window, mirroring consensus).
    ``None`` entries mean the legacy shared preimage.
    """
    from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION, DOMAIN_BLOCK_PROPOSAL

    activation = cfg.consensus_domain_separation_height
    if activation is None or height is None or height < activation:
        return [None]
    if channel == "proposal":
        return [DOMAIN_BLOCK_PROPOSAL]
    domains: list[str | None] = [DOMAIN_BLOCK_ATTESTATION]
    if legacy_attestation_dual_accept_open(height, cfg):
        domains.append(None)
    return domains


def bridge_header_signing_domain(height: int | None, channel: str, cfg: ChainSettings = settings) -> str | None:
    """#1521: the single domain a NEW bridge-proof signature at ``height`` mints under.

    Returns ``None`` for the legacy shared preimage (pre-activation), else the
    channel's domain tag — ``DOMAIN_BLOCK_PROPOSAL`` for the block signature
    slot, ``DOMAIN_BLOCK_ATTESTATION`` for validator signature slots.
    """
    return bridge_header_signature_domains(height, channel, cfg)[0]


def is_block_producer(cfg: ChainSettings = settings) -> bool:
    """Whether this node produces blocks — hub mode or a configured PBFT validator.

    Producers derive state by applying blocks; follower state sync must never
    overwrite their account table (incident 27207, 2026-09-28). Same predicate
    as main.py's "Running as block producer" gate.
    """
    return cfg.blockchain_mode == "hub" or bool(
        cfg.multi_validator_consensus_enabled and cfg.validator_set and cfg.proposer_id and cfg.proposer_key
    )
