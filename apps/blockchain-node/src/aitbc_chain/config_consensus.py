from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from .config_env import UC_TIMING_MARGIN_SECONDS


# Flags that only take effect with the vote-journal master on (#1281/#1301/#1306).
_JOURNAL_DEPENDENT_FLAGS = (
    "vote_journal_justification_enabled",
    "vote_journal_abandon_enabled",
    "vote_journal_sealed_rival_pull",
    "unavail_nonblocking_persist_enabled",
    "vote_journal_liveness_enabled",
)


def _abandon_gap_findings(s: Any, journal: bool) -> list[str]:
    """#1985 (bc-2 halt at h28508, 15 Nov): a journal without proposer abandon.

    With no abandon, a proposal that misses quorum leaves every voter pinned to
    its hash until the unlock valve (and UC) opens, staggered per validator --
    measured as a 2 h stall. The liveness flag re-announces abandons, so it is
    inert without them.
    """
    if not journal or s.vote_journal_abandon_enabled:
        return []
    out = [
        "vote_journal_enabled without vote_journal_abandon_enabled: a proposal that misses quorum pins "
        "every voter to its hash until the unlock valve opens (bc-2 h28508 stall, #1985)"
    ]
    if s.vote_journal_liveness_enabled:
        out.append("vote_journal_liveness_enabled needs vote_journal_abandon_enabled; its abandon re-announce is inert")
    return out


def uc_combo_findings(s: Any) -> tuple[list[str], list[str]]:
    """(errors, warnings) for UC flag combinations that freeze or silently disable liveness.

    Errors are the combinations measured to stall the chain (an armed UC whose evidence +
    collect window outlives the header/cert freshness bound); warnings are inert or
    degenerate settings. #1722; see ``_guard_unsafe_uc_flag_combinations`` for removal.
    """
    errors: list[str] = []
    warnings: list[str] = []
    journal = bool(s.vote_journal_enabled)
    for name in _JOURNAL_DEPENDENT_FLAGS:
        if getattr(s, name) and not journal:
            warnings.append(f"{name} is set but vote_journal_enabled is off, so it has no effect")
    warnings.extend(_abandon_gap_findings(s, journal))
    if (
        journal
        and s.vote_journal_justification_enabled
        and not s.attestation_round_lock_enabled
        and s.consensus_domain_separation_height is None
    ):
        # #1940: UC excuses only apply to ROUND_BOUND_CROSS_ROUND pairs.
        # With neither round-lock nor domain separation, every attestation
        # is legacy-format → every equivocation pair classifies LEGACY →
        # justified_unlock can never fire and UC-released votes mint
        # unexcusable slashable evidence. Fail closed at startup.
        errors.append(
            "vote_journal_justification_enabled requires attestation_round_lock_enabled "
            "or consensus_domain_separation_height: without round-bound attestations "
            "UC-excused equivocations classify LEGACY and stay slashable"
        )
    if journal and s.vote_journal_justification_enabled:
        window = float(s.unavail_evidence_seconds) + float(s.unavail_collect_seconds) + UC_TIMING_MARGIN_SECONDS
        header_max = float(s.attestation_header_max_age_seconds)
        cert_max = float(s.unavail_cert_max_age_seconds)
        if 0 < header_max <= window:
            errors.append(
                f"unavail_evidence_seconds + unavail_collect_seconds + {UC_TIMING_MARGIN_SECONDS:g}s = {window:g}s "
                f"is not below attestation_header_max_age_seconds={header_max:g}s; the header goes stale before "
                "the UC wait ends and every attestation is refused as stale_header"
            )
        if 0 < cert_max <= window:
            errors.append(
                f"unavail_evidence_seconds + unavail_collect_seconds + {UC_TIMING_MARGIN_SECONDS:g}s = {window:g}s "
                f"is not below unavail_cert_max_age_seconds={cert_max:g}s; a certificate expires before it can be used"
            )
    if s.proposer_same_hash_retry_enabled:
        header = float(s.attestation_header_max_age_seconds)
        bound = (
            min(float(s.consensus_proposer_round_seconds), header) if header > 0 else float(s.consensus_proposer_round_seconds)
        )
        reserved = float(s.multi_validator_attestation_timeout_seconds) + float(s.proposer_same_hash_retry_margin_seconds)
        if bound - reserved <= 0:
            warnings.append(
                "proposer_same_hash_retry_enabled is on but the retry horizon is 0 "
                f"(min(round, header max age)={bound:g}s <= collect + margin={reserved:g}s), so retries never reuse a header"
            )
    return errors, warnings


class ConsensusConfig(BaseModel):
    # Multi-validator consensus (v0.7.5). Master toggle for activating
    # MultiValidatorPoA + PBFT. When False, single-validator PoA remains
    # active. The RuntimeError guards in multi_validator_poa.py and pbft.py
    # read this setting.
    # v0.10.16 / G6: fail-closed by default. The single-proposer hub deployment must
    # not report itself as multi-validator. Enable only after explicit security review
    # and a validator_set has been configured.
    multi_validator_consensus_enabled: bool = False
    # Validator set: JSON list of {"address": "...", "stake": "1000"} objects.
    # Used by MultiValidatorPoA to select proposers and validate attestations.
    validator_set: str = ""
    # DEAD-ISLAND-GOSSIP-1 (#393): the island hub's proposer id.
    # Empty disables the island liveness monitor (detection-only default).
    island_hub_proposer_id: str = ""
    # Validator keys controlled by this node: JSON mapping address -> private key.
    # May be set in blockchain-secrets.env. The mapping is used to sign blocks and
    # produce attestations. Keep this value out of the repository.
    validator_keys: str = ""
    # Minimum number of attestations required in block_metadata for a multi-validator
    # block to be accepted during sync (in addition to the proposer signature).
    # G6: require at least 2 validator attestations when multi-validator is active.
    # TRAP: this default is *nonzero*. Setting it explicitly to 0 or 1 LOWERS the
    # quorum bar below the shipped default — 0 does not mean "extra safe", it means
    # "no attestation certificate required". Do not set it without understanding
    # that larger is stricter, smaller is weaker.
    multi_validator_min_attestations: int = 2

    # Comma-separated ``gpu_id``s that GPU_REGISTER and GPU_ALLOCATE may not name (env ``GPU_RETIRED_IDS``). Empty
    # (the default) refuses nothing. Admission only: it is a door check on this node's REST, gossip and p2p intake,
    # not a consensus rule, so a block from a validator that does not set it still applies such a transaction. Its
    # purpose is to keep the ids retired on 2 Oct 2026 (scripts/ops/gpu-registry-sweep.py lists them) from being
    # registered again by anyone; it does not change what a replay of sealed history produces.
    gpu_retired_ids: str = ""
    # S-4: address allowed to sign ESCROW_RELEASE and ESCROW_REFUND on v3+.
    # The on-chain escrow_settlement_authority chain parameter takes precedence;
    # this setting (or ESCROW_RELEASE_ADDRESS) is the fallback for chains that
    # never set it. Below v5 an unset authority disables the check (legacy);
    # from state_transition_v5_height the transition fails closed instead.
    escrow_settlement_authority: str = ""
    # v11: ESCROW_FEE_SWEEP must pay this recipient — the treasury account that
    # collects the residue v3 custody strands in each per-escrow account.
    # The on-chain escrow_fee_recipient chain parameter takes precedence; this
    # setting (or ESCROW_FEE_RECIPIENT env) is the fallback for chains that
    # never set it. Unset fails closed: the sweep is refused, never misdirected.
    escrow_fee_recipient: str = ""
    # v5: BRIDGE_RELEASE/BRIDGE_REFUND must carry a secp256k1 signature over
    # the credit's semantic fields that recovers to this authority. The
    # on-chain bridge_release_authority chain parameter takes precedence; this
    # setting (or BRIDGE_RELEASE_AUTHORITY env) is the fallback, then the
    # escrow settlement authority — the bridge service signs credits with the
    # same operator settlement key unless told otherwise.
    bridge_release_authority: str = ""
    # Optional dedicated key (BRIDGE_RELEASE_PRIVATE_KEY env) used by the
    # bridge service to sign issued credits. Falls back to
    # ESCROW_RELEASE_PRIVATE_KEY, which the RPC process already holds.
    bridge_release_private_key: str = ""
    # Seconds to wait for remote attestation responses over gossip when this node is the proposer.
    multi_validator_attestation_timeout_seconds: float = 1.0
    # After the attestation quorum is reached, keep collecting this many extra
    # seconds so slower-but-valid validators still land in the block instead of
    # losing the first-to-min_count race every round. 0 keeps the old
    # seal-as-soon-as-quorum behaviour. Bounded by the timeout above.
    attestation_post_quorum_linger_seconds: float = 0.0
    # v0.18.0: reject unsigned PBFT messages by default; test harnesses must
    # set this to False explicitly.
    pbft_require_signatures: bool = True
    # v0.7.6 PBFT master toggle. When True, block production runs the full
    # pre-prepare / prepare / commit phases before a block is committed.
    # Fail-closed by default; requires at least 4 validators for f=1 BFT.
    pbft_consensus_enabled: bool = False
    # View-change timeout used by PBFT consensus (seconds).
    pbft_view_change_timeout: int = 30
    # #1940 F3: first block height at which PBFT commit certificates must
    # satisfy the strict contract in consensus/pbft_certificate.py — one
    # coherent (sequence, view) quorum verified identically at producer and
    # importer. None/unset keeps the legacy union-count verifier.
    pbft_certificate_strict_height: int | None = Field(default=None, ge=0)
    # #1940 F3-A: first sequence/height at which a validator's COMMIT votes
    # for different block hashes at the same height but different PBFT views
    # are recorded as cross-view equivocation evidence (slashing kind
    # ``pbft_cross_view_vote_equivocation``). Detection/evidence only — it does
    # NOT change which votes are legal (that is the F3-B commit lock, still
    # gated separately and unarmed). None/unset/malformed keeps detection
    # dormant and behavior byte-identical.
    pbft_cross_view_commit_lock_height: int | None = Field(default=None, ge=0)
    # #1940 F3-B: first height at which importers pin a strict-era PBFT
    # commit certificate's view to the timestamp-derived proposer round —
    # the same round the producer signs commits under — instead of accepting
    # any coherent view. Independent of the commit-lock gate: the lock gates
    # which votes a validator may EMIT, this gates which certificate view a
    # block may CARRY. None/unset/malformed keeps the unpinned strict check.
    pbft_certificate_view_binding_height: int | None = Field(default=None, ge=0)
    # #2005 F3-C: first sequence/height at which the signed
    # VIEW_CHANGE/NEW_VIEW protocol is live — VC intake/quorum, floor rule,
    # forced value selection, proposal-body persistence in pre-prepares, and
    # the importer certificate-view pin to the derived round. Everything is
    # dormant while None/unset/malformed: messages are ignored, votes are
    # unchanged and historical replay is byte-identical. Arming is deferred
    # fleet-wide (ruling 4C) — PBFT itself stays OFF regardless.
    pbft_view_change_height: int | None = Field(default=None, ge=0)
    # #2171: height-armed cross-author re-proposal. From this height (and only
    # while ``pbft_view_change_height`` is also active) the round's scheduled
    # proposer re-proposes the commit-locked block even when someone else
    # authored it, and followers accept that body under a locked NEW_VIEW. Dormant
    # while None/unset/malformed: #2157 behaviour and R4 are byte-identical.
    # Arm on all four validators before the height (version-height rule).
    pbft_locked_cross_author_height: int | None = Field(default=None, ge=0)
    consensus_view_change_timeout_seconds: int = 30  # H6 — timeout before view change
    consensus_round_timeout_seconds: int = 10  # per-round timeout
    # v0.25.6: deterministic proposer rotation. When the scheduled proposer for
    # a height does not produce a block, the round derived from the parent
    # block's timestamp advances and the next validator in the round-robin
    # takes the slot. Every node derives the same round from on-chain
    # timestamps, so an unavailable proposer is routed around without any
    # view-change message exchange. Set it comfortably larger than the largest
    # gap the network produces when it is healthy. A smaller value is still
    # safe, because the proposer derives the round from the same timestamp its
    # validators will, but the slot then rotates on ordinary blocks instead of
    # only when a proposer is missing. The default aligns with the heartbeat
    # interval so a silent proposer is skipped within one heartbeat cycle.
    # Left unset, this is derived from ``max_empty_block_interval`` -- see
    # ``_scale_the_proposer_round_to_the_heartbeat``. An explicit value wins.
    consensus_proposer_round_seconds: int = 60
    # v0.25.x attester lock: a validator that signs (attests) a peer's block
    # at height h will not propose — or re-attest — a different block at h
    # for one proposer round. Instead it tries to fetch the attested block
    # from a mesh peer and pull it. The lock expires after one round window
    # so an attested block that never materialises cannot stall production.
    attestation_lock_enabled: bool = True
    # #1242 staged rollout: re-key the attester lock to (height, round), bind
    # the round into the signed attestation payload, add the tip-height /
    # canonical-parent check before signing, and persist signed
    # (height, round, hash) records so a restart cannot forget an
    # equivocation decision. Off preserves the legacy height-only lock and
    # the version-gated v9 parent check exactly. Sandbox evaluation only —
    # production merge stays gated on independent review.
    attestation_round_lock_enabled: bool = False
    # #1198 staged rollout: when armed, slash-driven validator deactivation is
    # read from canonical chain state (validator_deactivation markers written
    # by VALIDATOR_DEACTIVATE transactions) instead of node-local
    # ConsensusState mutation, and local Byzantine detection becomes
    # advisory-only (metrics/evidence, never is_active). Off preserves the
    # legacy local-persistence behavior exactly. Arming order per the
    # approved migration plan: draft markers from slashing_events_json →
    # operator signs → VALIDATOR_DEACTIVATE txs seal → confirm marker heights
    # → arm this flag fleet-wide.
    consensus_chain_slashing_enabled: bool = False
    # #1206: draft_deactivation_txs only cites slashing evidence sealed at
    # least this many blocks deep, so a reorg cannot invalidate the
    # justification an evidence_hash commits to. Defaults to max_reorg_depth's
    # value — evidence deeper than the deepest possible reorg is safe to cite.
    consensus_slashing_evidence_finality_depth: int = 10
    # #2118: max recorded slashing events per (validator, condition, height).
    # A flood of distinct forged hash pairs at one height grew hub's persisted
    # history to 67 MB (30,245 events at one height) and stalled the RPC
    # worker. Bounded by default since #2169 (0 = unbounded, the legacy opt-out); the
    # cap applies on record and when a persisted history is loaded.
    slashing_max_events_per_height: int = 8
    # #2130: verify equivocation evidence before it is recorded or levied. When
    # armed, an equivocation claim is admitted only if its two signatures verify
    # against the accused (same height/round, differing hashes, signer == accused),
    # the accused still has stake, and no signed or levied record already stands at
    # that (validator, condition, height). Dormant (False) = legacy behaviour.
    equivocation_verify_before_record: bool = False
    # #2131: bound the persisted slashing history per validator. Keeps the newest N
    # events per validator (levied events are never dropped — they are the audit
    # trail of a deducted penalty — then signed evidence, then advisory records) and
    # persists a pruned count + digest per validator instead of the dropped events.
    # Bounded by default since #2169 (0 = unbounded, the legacy opt-out). An existing
    # oversized blob is compacted on the first persist after the bound applies;
    # nothing is pruned while this is 0.
    slashing_history_persist_max_per_validator: int = 1000
    # U2 failure-evidence window for cross-round signing: after observing a
    # later-round attest_request at the same height, the locked round's
    # gates window must fully elapse before a rival hash may be signed.
    # 0 derives it from the attestation timeout (+1s margin, +PBFT view
    # timeout when PBFT is armed).
    attestation_round_unlock_window_seconds: float = 0.0
    # #1245: freshness bound on the SIGNED HEADER timestamp (not on request
    # arrival time, which a replayer controls). An attester refuses a request
    # whose header timestamp is older than this many seconds, so a captured
    # request cannot be re-fed to refresh or re-arm the attester lock after
    # a restart (the header timestamp is hash-bound at v9, so it cannot be
    # rewritten). 60 s is 3.75x the proposer's longest collection window
    # (15 s timeout + 0.5 s per missing attestation) -- see the #1245 ledger.
    # 0 or less disables the check.
    attestation_header_max_age_seconds: float = 60.0
    # #1245: how far in the FUTURE a header timestamp may sit relative to this
    # node's clock before the request is refused. Absorbs honest clock
    # disagreement between validators; a header from further ahead would
    # otherwise stay "fresh" for longer than the bound above.
    attestation_header_future_skew_seconds: float = 10.0
    # #1298 FRESHHASH-RETRY-1: when a proposal fails its gates, the next
    # retry at the same height reuses the failed block's timestamp (and thus
    # its hash) while it is still inside the attestation-lock / header-age
    # windows, instead of re-assembling with datetime.now() and producing a
    # fresh hash every round. Attesters that already signed the first hash
    # treat the retry as an idempotent re-publish inside the lock window;
    # after the horizon the retry falls back to a fresh timestamp/hash, so a
    # lapsed lock still forces the fresh-round path (never a timer-only
    # unlock). Proposer-local retry policy: the sealed block, its hash and
    # signature are identical either way, so replayed verdicts do not
    # change. Default OFF per operator ruling: same-hash retry is enabled
    # per-deployment via env until the AD design review clears default-on.
    # False restores the old fresh-timestamp-per-retry behaviour.
    proposer_same_hash_retry_enabled: bool = False
    # Slack reserved on top of one collect window when computing the same-hash
    # retry horizon: the pinned timestamp must leave room for a final gate
    # cycle (attestation collect ≈ multi_validator_attestation_timeout_seconds)
    # plus propagation/signing slack before the header hits
    # attestation_header_max_age_seconds and goes stale at attesters. The
    # horizon is min(round_seconds, header_max_age) - (timeout + this).
    proposer_same_hash_retry_margin_seconds: float = 12.0
    # #1268 Phase 1 (dual-seal prevention) -- every switch below defaults OFF;
    # off is byte-identical to the pre-#1268 behavior.
    #
    # Durable per-height vote journal. A validator records every vote it casts
    # (attestation signature, or its own proposal) in ``vote_journal.json``
    # BEFORE the signature leaves the process, and keeps the entry until the
    # height is below the local tip. While an entry for a DIFFERENT hash is
    # live, the validator refuses to attest a rival at that height and refuses
    # to propose at it -- across restarts, and without a wall-clock expiry
    # (the legacy 60 s lock and its restart amnesia are the G1/G3 gaps).
    vote_journal_enabled: bool = False
    # Liveness valve: a journal entry blocks a rival only until it is this old
    # AND the voted block could not be fetched from the proposer or any mesh
    # peer (fetch-before-unlock). Far longer than the 60 s legacy window on
    # purpose. Every use of the valve is counted and recorded as #1198
    # equivocation evidence.
    vote_journal_unlock_seconds: float = 300.0
    # #1310: run the attest-listener v9 tx check in a worker thread instead of
    # on the event loop (default OFF; the check is timed either way).
    attest_v9_check_offload_enabled: bool = False
    # #1295 ATTEST-LAG-WAIT-1 (optional hardening, default OFF): when the
    # local tip sits 1..attest_lag_wait_max_blocks behind the attestation
    # request's parent, the v9 check waits up to attest_lag_wait_seconds
    # for the import to catch up before refusing not_at_parent — absorbs
    # transient import stalls (e.g. sqlite lock windows) without weakening
    # fork protection: a tip ahead of, or on a rival at, the parent height
    # still refuses immediately. Enabling implies the check runs off the
    # event loop (the wait sleeps).
    attest_lag_wait_enabled: bool = False
    attest_lag_wait_seconds: float = 10.0
    attest_lag_wait_max_blocks: int = 2
    # #1940 F4: dormant post-state attestation gate. At/above the configured
    # height every attest request's transactions are re-executed on a
    # consistent SQLite snapshot of local parent state inside the v9 check;
    # the claimed state/aux roots must reproduce under the real importer
    # rules and the carried bridge root is bound to the authenticated
    # header/stored row (the legacy importer trusts it — deterministic
    # bridge-root enforcement is F5 scope) or the attestation is refused.
    # None disables the probe entirely — no activation value is chosen
    # here; rollout requires a uniform configured height.
    attestation_post_state_height: int | None = Field(default=None, ge=0)
    # Node-local budget for one probe (snapshot + apply). Expiry refuses the
    # attestation; it is never a consensus verdict and never extends the
    # request's own deadline semantics.
    attestation_post_state_timeout_seconds: float = Field(default=10.0, gt=0, allow_inf_nan=False)
    # #2003 (ATTEST-POSTSTATE-PROBE-ARMING-1) F2: pre-flight bound on the
    # source chain.db size (main file plus -wal) the probe copies into an
    # in-memory snapshot. A database larger than this refuses
    # "post_state_db_too_large" before the backup runs — on multi-GB files
    # the copy alone can exceed the probe timeout, turning every probe into
    # post_state_timeout and silently stalling attestations. 0 disables the
    # guard; the default 1 GiB is sized so the snapshot fits comfortably
    # inside attestation_post_state_timeout_seconds on fleet hardware.
    attestation_post_state_max_db_bytes: int = Field(default=1073741824, ge=0)
    # #1306: unlock_justification waits inside the serial attest-request
    # listener are timed; waits at or above this many seconds increment
    # attest_listener_unlock_stall_total (instrumentation only, no behavior).
    attest_listener_stall_seconds: float = 5.0
    # #1301 L2: a proposer that missed attestation quorum signs and publishes
    # an abandon statement; voters whose journal holds an attest vote for that
    # exact hash from that proposer release the entry. Needs vote_journal_enabled.
    vote_journal_abandon_enabled: bool = False
    # #1985 liveness hardening for the abandon path (dormant, default OFF;
    # needs vote_journal_enabled + vote_journal_abandon_enabled). Gossip is not
    # durable: a voter that restarted or lost the one abandon publish stays
    # pinned to a hash nobody will seal (bc-2 h28508). Armed: (1) a proposer
    # re-signs and re-publishes its abandons while the height is undecided,
    # at most once per ``vote_journal_abandon_reannounce_seconds`` per hash, owed from
    # the moment of the drop (even if the first send fails), persisted in
    # ``abandon_ledger.json`` next to the journal so a proposer restart keeps it, and
    # checked on every proposer-loop iteration, not only in its own slots;
    # (2) on start it abandons and retracts its own journal proposals above
    # the tip (the block died with the process); (3) the attestation lock is
    # minted only after the journal accepts the vote, so a refused rival no
    # longer leaves a lock for a hash this validator never signed.
    vote_journal_liveness_enabled: bool = False
    vote_journal_abandon_reannounce_seconds: float = 30.0
    # #1311: replicate signature-bearing attestation-equivocation evidence over
    # the restricted ``consensus.equivocation.<chain>`` topic. Default OFF:
    # nothing is published, subscribed or stored. Advisory only — ingest never
    # slashes; it records into the same advisory event list local detection uses.
    equivocation_replication_enabled: bool = False
    # #2119: max prior hashes a newly signed hash is paired with when recording
    # attestation equivocation (the pairing was all-priors: n hashes -> n(n-1)/2
    # events). 0 = every prior (legacy, dormant until armed).
    equivocation_max_pairs_per_signature: int = 0
    equivocation_replication_ring_cap: int = 10000  # records per chain, FIFO eviction
    equivocation_replication_max_record_bytes: int = 4096
    equivocation_replication_max_hashes_per_slot: int = 4  # distinct hashes per (validator, height, round)
    equivocation_replication_rate_per_minute: int = 20  # per reporting validator, sliding window
    equivocation_replication_max_publishes: int = 3  # per record, per process lifetime
    # #1280 VALVE-P15-1: a peer serving a DIFFERENT block at the voted height
    # is positive contention evidence. While such a sighting is fresh it
    # suppresses the re-vote path (delay only — never a signature outside the
    # journal/UC path), capped at ``vote_journal_contended_max_seconds`` from
    # the first observation so a stuck peer cannot hold a height forever.
    vote_journal_contention_fresh_seconds: float = 60.0
    # On sealed-rival contention, pull the rival block: sealed material is
    # canonical, importing it passes the height and ends the stall. Unsealed
    # rivals are never pulled (would import a fork block).
    vote_journal_sealed_rival_pull: bool = False
    # #1281 Phase 2 (verifiable-justification barrier) -- dormant default-OFF,
    # requires vote_journal_enabled. When armed, the liveness valve no longer
    # releases a rival vote on age+miss alone: the unlock needs an
    # UnavailabilityCertificate (>= MIN_ATTESTATIONS validator-signed
    # absence statements), a clean GossipObservationIndex window for the
    # voted hash, and T_evidence seconds of continuous unfetchability —
    # independently verifiable protocol evidence per the #1274 ruling.
    vote_journal_justification_enabled: bool = False
    # #1306 nonblocking persist -- dormant default-OFF, requires the UC barrier
    # (vote_journal_enabled + vote_journal_justification_enabled). The attest-
    # request listener's leg-1 ``unfetchable_persists`` otherwise polls inside
    # the serial listener for the whole unavail_evidence_seconds window per
    # rival hash, answering no attest requests meanwhile (driver11: 40 s
    # stalls, frozen height). Armed, the listener starts/joins the shared
    # sampler and reads its current verdict instead of waiting; the rival is
    # refused now and re-evaluated on the next attest retry. No release can
    # happen before T_evidence has matured -- only the waiting moves. The
    # proposer path always blocks, unchanged.
    unavail_nonblocking_persist_enabled: bool = False
    # UC collection window and certificate freshness bound.
    unavail_collect_seconds: float = 15.0
    unavail_cert_max_age_seconds: float = 120.0
    # Observation-index quiet window (T_evidence) and fetch-miss sampling
    # cadence. unavail_min_responses <= 0 derives from
    # multi_validator_min_attestations (quorum-intersection threshold).
    unavail_evidence_seconds: float = 90.0
    unavail_sample_seconds: float = 10.0
    # Mesh-visibility window for the observation index (coarser than
    # T_evidence — reachability signal, not quiet-window evidence).
    unavail_visibility_seconds: float = 300.0
    unavail_min_responses: int = 0
    # #1281 respin: negative-result backoff after a failed UC collection —
    # the probe is single-flight per (chain, height, hash), and a failed
    # collection suppresses re-probes for at least this long (floored at
    # 2x unavail_collect_seconds) so gate retries cannot storm the topic.
    unavail_collect_backoff_seconds: float = 30.0
    # Re-publish a sealed-but-unconfirmed block on the gossip topic until a
    # child block exists or a mesh peer serves it, so one failed publish no
    # longer leaves the seal visible only on its proposer.
    seal_republish_enabled: bool = False
    seal_republish_interval_seconds: float = 10.0
    seal_republish_max_seconds: float = 120.0
    # Additive ``confirmations`` / ``finalized`` / ``finalized_height`` fields on
    # /head and the block and transaction reads. ``finalized`` means at least
    # ``rpc_finality_depth`` blocks sit on top (N=3, the
    # BRIDGE_WITHDRAW_SEAL_DEPTH convention). Existing fields never change.
    rpc_finality_fields_enabled: bool = False
    rpc_finality_depth: int = 3
    # Delta-journal undo for non-empty losing fork segments
    # (``state/block_deltas.py``). While False the resolvers escalate a
    # non-empty segment to the operator exactly as before the journal
    # existed — the journal still records, but nothing is reverted. Default
    # on: the journal is fail-closed (any capture gap stamps an ``incomplete``
    # sentinel and revert refuses the block) and per-family differential
    # tests prove apply+revert restores every chain table. The ancestor
    # state-root check remains as a second net for the ``account`` table.
    sync_fork_undo_enabled: bool = True
    # #1322: before a winning peer segment displaces ours, apply it in a
    # tentative reorg (revert + apply inside one transaction, always rolled
    # back). An unappliable segment is vetoed; an inconclusive probe defers.
    sync_fork_apply_probe_enabled: bool = False
    # Drop a pre-prepare whose sender is not the scheduled proposer for the
    # block's height and round. Setting this False restores the pre-v0.25.6
    # behaviour, where any validator's proposal was prepared.
    consensus_enforce_proposer_schedule: bool = True
    # Refuse attest_requests that carry no proposer_signature: the schedule
    # check proves the claimed name, not authorship, so an unsigned request
    # naming the scheduled proposer squats the attestation lock (#1240).
    # Default on. Proposers sign requests since #1058/#1156 (a build older
    # than #1156 sends them unsigned), so during a rolling upgrade from such
    # a build set CONSENSUS_REQUIRE_SIGNED_ATTEST_REQUEST=false until every
    # validator is upgraded, then drop the override. The live fleet has
    # carried an explicit =true since 5 Nov 2026.
    consensus_require_signed_attest_request: bool = True
    # Pre-proposal freshness gate: before building a block, compare the local
    # head with every GOSSIP_MESH_PEER_URLS peer's /rpc/head. A peer ahead (or
    # disagreeing at our height) blocks the proposal; per-peer query timeout
    # bounds the added latency and unreachable peers degrade to UNVERIFIED
    # (propose anyway, metric recorded) rather than halting the chain.
    proposal_freshness_check_enabled: bool = True
    proposal_freshness_peer_timeout_seconds: float = 2.0
    # A cached freshness verdict is only valid this long — far below the round
    # window, so a "fresh" verdict can never survive into a later round after a
    # network blip. UNVERIFIED results are never cached at all.
    proposal_freshness_cache_ttl_seconds: float = 5.0
    # An ahead peer whose bulk pull finishes without moving our head is dropped
    # from the ahead check for this long (~10 round windows): its taller fork
    # would otherwise silence us forever. Hash votes are unaffected.
    proposal_freshness_peer_quarantine_seconds: float = 600.0
    # consensus_validator_set_epoch_blocks was removed (#848): validator-set
    # epoch rotation was never invoked and has been deleted; the env var is now
    # ignored (pydantic extra="ignore").
    consensus_slashing_enabled: bool = True  # C2 — enable slashing
    consensus_slashing_amount: Decimal = Decimal("100.0")  # stake to slash per offense
    consensus_byzantine_threshold: int = 3  # slash count before deactivation

    # Cross-chain settlement (v0.9.0). Atomic settlement uses HTLCs to
    # ensure either both chains settle or both refund. Settlement RPC
    # endpoints and CrossChainSettlementService are now active; B4 (HTLC
    # contract integration) is complete. Enabled by default for the homebrew
    # network — operators can still disable explicitly if they run a private
    # deployment before a security review.
    escrow_enabled: bool = True
    escrow_atomic_settlement: bool = True  # use HTLC (vs manual admin refund)
    escrow_timeout_default: int = 3600  # 1 hour default timeout
    escrow_timeout_large: int = 86400  # 24 hours for large trades
    escrow_timeout_extension_max: int = 604800  # 7 days max extension
    escrow_htlc_enabled: bool = True  # use HTLC contract for escrow
    escrow_htlc_contract_address: str = ""  # deployed CrossChainAtomicSwap.sol
    escrow_large_trade_threshold: int = 10000  # trades above this use large timeout
