from __future__ import annotations

from pydantic import BaseModel


class BridgeConfig(BaseModel):
    # Cross-chain bridge release fence (v0.5.16 → v0.7.2 UNFENCED).
    # The bridge release path (confirm_transfer / /bridge/confirm) now uses
    # full cryptographic verification: Merkle proof verification against
    # stored block headers (v0.7.2 §B3), block header signature verification
    # against the v0.7.1 validator set (v0.7.2 §B4), finality tracking
    # (v0.7.2 §B5), and multi-sig threshold signatures (v0.7.1 §B6).
    # v0.10.16: fail-closed by default. The release path must be explicitly
    # enabled in production configuration after Merkle proof verification and
    # validator-set admission control are operational. Production fleet:
    # BRIDGE_RELEASE_ENABLED=true.
    bridge_release_enabled: bool = False

    # Operator pause switch for NEW bridge locks (BRIDGE_LOCKS_PAUSED). While
    # set, every lock-request surface — POST /bridge/lock,
    # /swap and /cross-chain/bridge, plus the initiate_transfer chokepoint
    # itself — refuses new locks with HTTP 503; refunds, status reads and the
    # confirm path are untouched. In place pending the attestation-based
    # bridge validator set (the multisig confirm threshold is unreachable
    # while block headers carry only the proposer signature). A lock already
    # in the mempool still seals — gating admission would strand its funds
    # (BRIDGE_REFUND binds a *sealed* lock from v6).
    bridge_locks_paused: bool = False

    # SEC-REPLAY-1: when set (BRIDGE_LOCK_REQUIRE_REPLAY_GUARD), POST
    # /bridge/lock refuses old-form signatures — the six-field dict has no
    # nonce/expiry, so a captured signed body replays as a new transfer. New-form
    # locks (issued_at + nonce in the signed dict) are always replay-checked,
    # flag or not. Default off for deployed-CLI compatibility; enabling is a
    # deliberate operator step after clients are updated.
    bridge_lock_require_replay_guard: bool = False

    # SEC-REPLAY-2: when set (CROSS_CHAIN_REQUIRE_REPLAY_GUARD), the
    # /cross-chain/bridge and /swap lock paths refuse old-form signatures —
    # same scheme as BRIDGE_LOCK_REQUIRE_REPLAY_GUARD, on the shared
    # _lock_transfer helper. New-form bodies (issued_at + nonce signed) are
    # always replay-checked, flag or not. Default off for client compat.
    cross_chain_require_replay_guard: bool = False

    # Bridge configuration (v0.7.0). Operational parameters for the cross-chain
    # bridge. Defaults mirror the constants in aitbc/constants.py
    # (BRIDGE_TIMEOUT_SECONDS, BRIDGE_RETRY_LIMIT, etc.) so they can be tuned
    # per-deployment via env vars without code changes.
    bridge_timeout: int = 300  # Seconds before a transfer is considered stale
    bridge_retry_limit: int = 3  # Retry attempts for failed bridge operations
    bridge_fee_basis_points: int = 10  # Bridge fee in basis points (10 = 0.1%)
    bridge_supported_chains: str = ""  # Comma-separated list of chain IDs the bridge serves
    bridge_batch_size: int = 10  # Max transfers per batch operation
    bridge_monitor_interval: int = 60  # Seconds between bridge health checks
    bridge_header_sync_batch: int = 500  # Max block headers mirrored into the bridge table per finalizer pass
    # #1305: heights below the mirror head re-verified against the canonical
    # block table each pass — a fork heal leaves stale mirror rows the
    # resume-at-last_stored sync never revisits.
    bridge_header_verify_window: int = 128
    bridge_header_commit_batch: int = (
        50  # Headers stored per sqlite commit in the finalizer backfill (one commit per N, not per header)
    )
    # Opt-in to installing this chain's validator set under a FOREIGN
    # bridge-supported chain id on an empty table. Off by default: the
    # local set only stands in for a chain that genuinely shares
    # validator identities; anything else is a phantom set (Refs #659).
    bridge_backfill_foreign_validators: bool = False
    # Seconds a single chain's finalizer pass may occupy the worker thread
    # before the loop abandons it and moves on (the abandoned thread keeps
    # running; a new pass for that chain is skipped until it returns). Guards
    # the finalizer loop against a silently wedged sqlite call starving the
    # other chains' phases.
    bridge_finalizer_pass_timeout: int = 900
    # Seconds before a chain whose bridge store failed the readiness probe is
    # re-probed. A transient failure (store file not yet created, sqlite lock
    # during startup) must not silence the chain for the process's lifetime.
    bridge_chain_unavailable_retry_seconds: int = 300
    # #1290: total budget for retrying a bridge header store that hits
    # "database is locked" past the per-connection busy_timeout. Every
    # app-lifespan process (RPC workers, island RPC) mirrors the same headers
    # into the same chain.db; the single-writer flock serializes them, and
    # this budget covers a foreign long write transaction (observed 36-126 s
    # on node1). 0 disables the retry (single attempt, pre-#1290 behaviour).
    bridge_header_lock_retry_seconds: int = 120
    bridge_stuck_transfer_timeout: int = 3600  # Seconds before a pending transfer is flagged as stuck
    bridge_refund_delay_seconds: int = 0  # Minimum seconds after lock_time before a refund is allowed (0 = no delay)
    # Maximum per-lock amount in compute units. 0 = unlimited in
    # development only: production nodes refuse locks when this is unset
    # (fail-closed, see BridgeTransferMixin._enforce_lock_cap). The
    # production fleet sets BRIDGE_MAX_LOCK_AMOUNT=36000000000 (1,000 AIT).
    bridge_max_lock_amount: int = 0
    # GAP-47: in-process relayer. When True the bridge finalizer loop also
    # mirrors locally produced/synced block headers into bridge_block_header
    # and confirms pending transfers whose lock has reached finality (the
    # normal /rpc/bridge/confirm path — Merkle proof, header signature,
    # finality, multisig checks all still apply). It is AND-gated on
    # bridge_release_enabled in the finalizer loop, so this flag alone cannot
    # move value; disabling it turns the loop back into finalize-only.
    bridge_relayer_enabled: bool = True
    # Shared transfer ledger (issue #696): base URL of the rpc hosting the
    # /rpc/bridge/ledger/* surface (hub's rpc in production). Unset = the
    # relayer keeps its local status='pending' scan — byte-for-byte today's
    # behaviour; intake does no write-through register.
    bridge_ledger_url: str = ""

    # GAP-47: cross-chain swap quote table. Comma-separated
    # "from_chain::to_chain=rate" or "chain:token::chain:token=rate" entries
    # the operator configures; swaps over pairs with no configured rate are
    # rejected unless both assets are identical (parity settlement at 1.0).
    # There is no cross-chain AMM to derive a price from, so the endpoint
    # refuses rather than inventing one.
    cross_chain_swap_rates: str = ""

    # Bridge multi-sig configuration (v0.7.1). Security layer for the
    # cross-chain bridge: M-of-N validators must sign each proof before
    # funds can be released. Defaults match aitbc/constants.py. The release
    # fence (bridge_release_enabled) stays in place until v0.7.2 completes
    # Merkle proof verification — multi-sig is an additional layer, not a
    # replacement for the fence.
    bridge_multisig_enabled: bool = False  # require multi-sig for confirm (production fleet: true)
    bridge_multisig_threshold: int = 3  # M-of-N minimum signatures (production fleet: 2)
    bridge_multisig_validators: int = 5  # N total validators (production fleet: 2)
    bridge_multisig_timeout: int = 3600  # seconds to collect signatures
    bridge_validator_set_grace_period: int = 7200  # seconds — old epoch valid during rotation
    bridge_block_signature_required: bool = True  # require block header signatures
    # Max seconds build_proof spends asking remote validators to attest the
    # sealed block's canonical header when the sealed metadata attestation set
    # alone is below bridge_multisig_threshold (issue #670). Remote answers only
    # ever arrive while the sealed block is still at/near a peer's tip (v9
    # parent-binding), so this is a short best-effort window, not a retry.
    bridge_proof_attestation_timeout_seconds: float = 2.0
    # v0.10.16: comma-separated list of Ethereum addresses authorized to register
    # bridge validators and ingest remote block headers. Empty means no admin is
    # configured, so validator/header admission is denied when the release fence
    # is enabled (fail-closed).
    bridge_admin_addresses: str = ""

    # Bridge verification configuration (v0.7.2). Replaces the trivially
    # forgeable field-equality proof validation with cryptographic Merkle
    # proof verification against stored block headers. The release fence
    # (bridge_release_enabled) is unfenced after this verification is
    # operational and tested.
    bridge_verification_mode: str = "in_process"  # "in_process" | "oracle"
    bridge_min_confirmations: int = 3  # minimum confirmations for any transfer
    bridge_finality_blocks: int = 6  # full finality threshold
    # Confirmations stop being counted at this depth (never below bridge_finality_blocks or
    # bridge_min_confirmations). Every new header used to bump every earlier header's count, a full
    # rewrite of bridge_block_header per block (22k rows, 12.5 MiB, ~3,200 WAL frames per block per node
    # on 2026-10-01, growing with chain height). Nothing decides on a count above the deepest requirement.
    bridge_confirmation_count_cap: int = 100
    # Whole AIT, converted to compute-units (1 AIT = 36,000,000) at the
    # comparison: a transfer whose amount >= this threshold requires full
    # finality (bridge_finality_blocks); below it, bridge_min_confirmations.
    bridge_large_transfer_threshold: int = 10000
    # Production hardening: when True, _validate_proof REJECTS any proof that
    # does not carry a Merkle inclusion proof (merkle_proof + lock_event). The
    # default is False to preserve the v0.7.2 "field + signature" verification
    # mode used by isolated/dev networks; set BRIDGE_REQUIRE_MERKLE_PROOF=true
    # before enabling the release path on networks that move real value.
    # Production fleet: BRIDGE_REQUIRE_MERKLE_PROOF=true.
    bridge_require_merkle_proof: bool = False

    # External oracle configuration (v0.7.4). When bridge_verification_mode
    # is "oracle", bridge proof verification calls an external oracle service
    # instead of the in-process verifier. The in-process verifier remains as
    # a fallback when oracle endpoints are unreachable.
    bridge_oracle_endpoints: list[str] = []  # External oracle endpoints (e.g. ["http://oracle-1:9000"])
    bridge_oracle_health_check_interval: int = 60  # seconds between oracle health checks
    bridge_oracle_timeout: int = 30  # seconds before an oracle request times out
