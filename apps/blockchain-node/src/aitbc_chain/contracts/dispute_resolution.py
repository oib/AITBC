"""
Dispute Resolution Smart Contract
Handles dispute filing, evidence submission, arbitration, and resolution
"""

import fcntl
import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from collections.abc import Callable, Iterator
from typing import Any, TypeVar, cast

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)

_PersistedMethod = TypeVar("_PersistedMethod", bound=Callable[..., Any])


class DisputeStatus(Enum):
    FILED = "filed"
    EVIDENCE_SUBMITTED = "evidence_submitted"
    ARBITRATION_IN_PROGRESS = "arbitration_in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class DisputeType(Enum):
    PERFORMANCE = "Performance"
    PAYMENT = "Payment"
    SERVICE_QUALITY = "ServiceQuality"
    AVAILABILITY = "Availability"
    OTHER = "Other"


@dataclass
class Dispute:
    dispute_id: int
    agreement_id: int
    initiator: str
    respondent: str
    status: DisputeStatus
    dispute_type: DisputeType
    reason: str
    evidence_hash: str
    filing_time: int
    evidence_deadline: int
    arbitration_deadline: int
    resolution_amount: int = 0
    winner: str | None = None
    resolution_reason: str = ""
    arbitrator_count: int = 0
    is_escalated: bool = False
    escalation_level: int = 1


@dataclass
class Evidence:
    evidence_id: int
    dispute_id: int
    submitter: str
    evidence_type: str
    evidence_data: str
    evidence_hash: str
    submission_time: int
    is_valid: bool = False
    verification_score: int = 0
    verified_by: str | None = None


@dataclass
class ArbitrationVote:
    dispute_id: int
    arbitrator: str
    vote_in_favor_of_initiator: bool
    confidence: int
    reasoning: str
    vote_time: int
    is_valid: bool = True


class DisputeResolutionContract:
    """In-memory implementation of Dispute Resolution contract"""

    def __init__(self, state_path: str | Path | None = None) -> None:
        # state_path=None → auto: AITBC_DISPUTE_STATE_FILE, else a
        # ``disputes.json`` beside chain.db so every uvicorn worker (and a
        # restart) shares one store (#2387). ``state_path="memory"`` or the
        # env value ``memory``/``none``/``off`` keeps the legacy per-process
        # behaviour for tests and dev.
        mode = str(state_path).lower() if state_path is not None else ""
        self._state_forced_memory = mode in ("memory", "none", "off")
        self._state_path_arg = None if state_path is None or self._state_forced_memory else Path(state_path)
        self._resolved_state_path: Path | None = None
        self._state_mode_locked = self._state_forced_memory
        self.disputes: dict[int, Dispute] = {}
        self.evidence: dict[int, list[Evidence]] = {}
        self.votes: dict[int, list[ArbitrationVote]] = {}
        self.arbitrators: dict[str, int] = {}
        self.dispute_counter = 0
        self.evidence_counter = 0
        self._owner: str | None = None
        self._state_dirty = False
        self._load_state()
        self._seed_arbitrators()

    # ------------------------------------------------------------------
    # shared-state persistence (#2387)
    # ------------------------------------------------------------------

    def _resolve_state_path(self) -> Path | None:
        """State file path, or None for in-memory mode. Resolved lazily so
        the module-level singleton picks up the engine once the app is up."""
        if self._state_path_arg is not None:
            return self._state_path_arg
        if self._state_mode_locked:
            return self._resolved_state_path
        mode = os.getenv("AITBC_DISPUTE_STATE_FILE", "").strip()
        if mode.lower() in ("memory", "none", "off"):
            self._state_mode_locked = True
            return None
        if mode:
            self._resolved_state_path = Path(mode)
        else:
            try:
                from ..chain_id import ChainIdNotConfigured
                from ..database import ChainDbMissingError, ForeignChainDbError, get_engine

                db = get_engine().url.database
            except (ChainIdNotConfigured, ChainDbMissingError, ForeignChainDbError, ValueError, OSError):
                # engine not up yet / unavailable — retry next call
                return None
            if not db or db == ":memory:":
                self._state_mode_locked = True
                self._resolved_state_path = None
                return None
            self._resolved_state_path = Path(db).parent / "disputes.json"
        self._state_mode_locked = True
        return self._resolved_state_path

    @staticmethod
    def _dispute_to_dict(dispute: Dispute) -> dict[str, Any]:
        raw = asdict(dispute)
        raw["status"] = dispute.status.value
        raw["dispute_type"] = dispute.dispute_type.value
        return raw

    @staticmethod
    def _dispute_from_dict(raw: dict[str, Any]) -> Dispute:
        return Dispute(**{**raw, "status": DisputeStatus(raw["status"]), "dispute_type": DisputeType(raw["dispute_type"])})

    def _load_state(self) -> None:
        path = self._resolve_state_path()
        if path is None or not path.is_file():
            return
        try:
            data = json.loads(path.read_text())
            self.dispute_counter = int(data.get("dispute_counter", 0))
            self.evidence_counter = int(data.get("evidence_counter", 0))
            self._owner = data.get("owner")
            self.arbitrators = {str(k): int(v) for k, v in (data.get("arbitrators") or {}).items()}
            self.disputes = {int(k): self._dispute_from_dict(v) for k, v in (data.get("disputes") or {}).items()}
            self.evidence = {int(k): [Evidence(**e) for e in v] for k, v in (data.get("evidence") or {}).items()}
            self.votes = {int(k): [ArbitrationVote(**v) for v in v] for k, v in (data.get("votes") or {}).items()}
        except (OSError, ValueError, TypeError, KeyError) as e:
            logger.error("Dispute state file %s unreadable/corrupt: %s", path, e)
            return
        env_seed = self._arbitrators_from_env()
        if env_seed:
            self.arbitrators.update(env_seed)

    def _save_state(self) -> None:
        path = self._resolve_state_path()
        if path is None:
            return
        payload = {
            "version": 1,
            "dispute_counter": self.dispute_counter,
            "evidence_counter": self.evidence_counter,
            "owner": self._owner,
            "arbitrators": self.arbitrators,
            "disputes": {str(k): self._dispute_to_dict(v) for k, v in self.disputes.items()},
            "evidence": {str(k): [asdict(e) for e in v] for k, v in self.evidence.items()},
            "votes": {str(k): [asdict(v) for v in vs] for k, vs in self.votes.items()},
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, path)
        except OSError as e:
            logger.error("Failed to persist dispute state to %s: %s", path, e)

    @contextmanager
    def _state_transaction(self, always_save: bool = True) -> Iterator[None]:
        """Exclusive cross-process mutation: flock, reload, yield, save.

        ``always_save=False`` (read paths) persists only when the overdue
        sweep actually changed state, so a GET doesn't rewrite the file.
        """
        path = self._resolve_state_path()
        if path is None:
            yield
            self._escalate_overdue()
            return
        lock_path = path.with_name(path.name + ".lock")
        try:
            lock_file = open(lock_path, "a+b")
        except OSError as e:
            logger.error("Dispute state lock %s unavailable: %s — operating unlocked", lock_path, e)
            self._load_state()
            self._state_dirty = False
            yield
            self._escalate_overdue()
            if always_save or self._state_dirty:
                self._save_state()
            return
        with lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                self._load_state()
                self._state_dirty = False
                yield
                self._escalate_overdue()
                if always_save or self._state_dirty:
                    self._save_state()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _escalate_overdue(self) -> bool:
        """Escalate non-terminal disputes past ``arbitration_deadline``.

        Runs inside every state transaction so deadline expiry is observed
        on the next mutation even without a dedicated sweeper (#2387).
        """
        now = int(time.time())
        changed = False
        for dispute in self.disputes.values():
            if dispute.status in (DisputeStatus.RESOLVED, DisputeStatus.ESCALATED):
                continue
            if now <= dispute.arbitration_deadline:
                continue
            dispute.status = DisputeStatus.ESCALATED
            dispute.is_escalated = True
            dispute.escalation_level += 1
            dispute.resolution_reason = "Arbitration deadline passed without a ruling — escalated"
            logger.info("Dispute %s escalated: arbitration deadline passed", dispute.dispute_id)
            changed = True
            self._state_dirty = True
        return changed

    @staticmethod
    def _is_closed(dispute: Dispute) -> bool:
        return dispute.status in (DisputeStatus.RESOLVED, DisputeStatus.ESCALATED)

    def _maybe_resolve(self, dispute_id: int) -> None:
        """Auto-resolve once every authorized arbitrator has voted.

        Tally uses each arbitrator's latest vote (revisions supersede).
        Plurality wins; a tie escalates. Record-only: ``winner`` and
        ``resolution_reason`` are stored for the settlement layer — no
        funds move here (#2387).
        """
        dispute = self.disputes.get(dispute_id)
        if dispute is None or self._is_closed(dispute):
            return
        votes = self.votes.get(dispute_id, [])
        latest: dict[str, ArbitrationVote] = {}
        for vote in votes:
            latest[vote.arbitrator] = vote
        if set(latest) != set(self.arbitrators):
            return
        for_initiator = sum(1 for v in latest.values() if v.vote_in_favor_of_initiator)
        against = len(latest) - for_initiator
        dispute.arbitrator_count = len(latest)
        if for_initiator == against:
            dispute.status = DisputeStatus.ESCALATED
            dispute.is_escalated = True
            dispute.escalation_level += 1
            dispute.resolution_reason = f"Arbitration tie {for_initiator}-{against} — escalated"
            logger.info("Dispute %s escalated on tied arbitration", dispute_id)
            return
        dispute.winner = dispute.initiator if for_initiator > against else dispute.respondent
        dispute.resolution_reason = f"Arbitration plurality {max(for_initiator, against)}-{min(for_initiator, against)} for {'initiator' if for_initiator > against else 'respondent'}"
        dispute.status = DisputeStatus.RESOLVED
        logger.info("Dispute %s resolved: winner=%s", dispute_id, dispute.winner)

    def _refresh(self) -> None:
        """Reads see the latest committed state in file mode."""
        if self._resolve_state_path() is not None:
            self._load_state()

    @staticmethod
    def _persisted(method: _PersistedMethod) -> _PersistedMethod:
        """Route a mutating method through the shared-state transaction."""

        @wraps(method)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self = args[0]
            with self._state_transaction():
                return method(*args, **kwargs)

        return cast(_PersistedMethod, wrapper)

    def set_owner(self, owner_address: str) -> None:
        """Set the contract owner address (called during deployment)."""
        with self._state_transaction():
            self._owner = owner_address.lower().strip()
            if not self._owner.startswith("0x"):
                self._owner = "0x" + self._owner

    def _seed_arbitrators(self) -> None:
        """Seed authorized arbitrators.

        ``AITBC_DISPUTE_ARBITRATORS`` (comma-separated ``0xaddress:score``
        entries) always merges into the set — env wins over persisted state
        so operators can rotate identities without editing the state file
        (#2052, #2387). When neither env nor persisted state supplies any
        arbitrators, the historical placeholder trio is kept so existing
        dev/test flows are unchanged — live evidence runs must set the env.
        """
        env = self._arbitrators_from_env()
        if env:
            self.arbitrators.update(env)
            logger.info("Seeded %s arbitrators from AITBC_DISPUTE_ARBITRATORS", len(env))
            return
        if self.arbitrators:
            return
        self.arbitrators = {
            "0x1111111111111111111111111111111111111111": 90,
            "0x2222222222222222222222222222222222222222": 85,
            "0x3333333333333333333333333333333333333333": 88,
        }
        logger.info(
            "Initialized %s placeholder arbitrators (set AITBC_DISPUTE_ARBITRATORS for real identities)", len(self.arbitrators)
        )

    @staticmethod
    def _arbitrators_from_env() -> dict[str, int]:
        """Parse ``AITBC_DISPUTE_ARBITRATORS`` = ``0xaddr:score[,0xaddr:score...]``."""
        from eth_utils import to_checksum_address

        raw = os.getenv("AITBC_DISPUTE_ARBITRATORS", "")
        out: dict[str, int] = {}
        for entry in raw.split(","):
            entry = entry.strip()
            if not entry:
                continue
            addr, _, score = entry.partition(":")
            addr = addr.strip()
            try:
                canon = to_checksum_address(addr)
                out[canon] = int(score.strip() or "50")
            except (ValueError, TypeError):
                logger.warning("Ignoring malformed AITBC_DISPUTE_ARBITRATORS entry: %r", entry)
        return out

    @staticmethod
    def _canon(address: str) -> str:
        """Canonicalize an arbitrator address for set membership checks."""
        try:
            from eth_utils import to_checksum_address

            return to_checksum_address(address.strip())
        except (ValueError, TypeError):
            return address.strip().lower()

    @_persisted
    def file_dispute(
        self, agreement_id: int, respondent: str, dispute_type: str, reason: str, evidence_hash: str, sender_address: str
    ) -> dict[str, Any]:
        """File a new dispute"""
        self.dispute_counter += 1
        dispute_id = self.dispute_counter
        current_time = int(time.time())
        evidence_deadline = current_time + 86400 * 3
        arbitration_deadline = current_time + 86400 * 7
        dispute = Dispute(
            dispute_id=dispute_id,
            agreement_id=agreement_id,
            initiator=sender_address,
            respondent=respondent,
            status=DisputeStatus.FILED,
            dispute_type=DisputeType(dispute_type),
            reason=reason,
            evidence_hash=evidence_hash,
            filing_time=current_time,
            evidence_deadline=evidence_deadline,
            arbitration_deadline=arbitration_deadline,
        )
        self.disputes[dispute_id] = dispute
        self.evidence[dispute_id] = []
        self.votes[dispute_id] = []
        logger.info("Filed dispute %s for agreement %s", dispute_id, agreement_id)
        return {
            "success": True,
            "dispute_id": dispute_id,
            "status": dispute.status.value,
            "message": f"Dispute {dispute_id} filed successfully",
        }

    @_persisted
    def submit_evidence(
        self,
        dispute_id: int,
        evidence_type: str,
        evidence_data: str,
        submitter_address: str,
        evidence_hash: str = "",
    ) -> dict[str, Any]:
        """Submit evidence for a dispute"""
        if dispute_id not in self.disputes:
            return {"success": False, "error": f"Dispute {dispute_id} not found"}
        dispute = self.disputes[dispute_id]
        if self._is_closed(dispute):
            return {"success": False, "error": "Dispute is closed"}
        if int(time.time()) > dispute.evidence_deadline:
            return {"success": False, "error": "Evidence submission deadline has passed"}
        self.evidence_counter += 1
        evidence_id = self.evidence_counter
        evidence = Evidence(
            evidence_id=evidence_id,
            dispute_id=dispute_id,
            submitter=submitter_address,
            evidence_type=evidence_type,
            evidence_data=evidence_data,
            evidence_hash=evidence_hash or f"0x{evidence_id:040x}",
            submission_time=int(time.time()),
        )
        self.evidence[dispute_id].append(evidence)
        if dispute.status == DisputeStatus.FILED:
            dispute.status = DisputeStatus.EVIDENCE_SUBMITTED
        logger.info("Submitted evidence %s for dispute %s", evidence_id, dispute_id)
        return {
            "success": True,
            "evidence_id": evidence_id,
            "status": "Submitted",
            "message": f"Evidence {evidence_id} submitted successfully",
        }

    @_persisted
    def verify_evidence(
        self, dispute_id: int, evidence_id: int, is_valid: bool, verification_score: int, arbitrator_address: str
    ) -> dict[str, Any]:
        """Verify evidence (arbitrator only)"""
        arbitrator_address = self._canon(arbitrator_address)
        if arbitrator_address not in self.arbitrators:
            return {"success": False, "error": "Not an authorized arbitrator"}
        if dispute_id not in self.disputes:
            return {"success": False, "error": f"Dispute {dispute_id} not found"}
        if self._is_closed(self.disputes[dispute_id]):
            return {"success": False, "error": "Dispute is closed"}
        for evidence in self.evidence[dispute_id]:
            if evidence.evidence_id == evidence_id:
                evidence.is_valid = is_valid
                evidence.verification_score = verification_score
                evidence.verified_by = arbitrator_address
                logger.info("Verified evidence %s for dispute %s", evidence_id, dispute_id)
                return {"success": True, "status": "Verified", "message": f"Evidence {evidence_id} verified"}
        return {"success": False, "error": f"Evidence {evidence_id} not found"}

    @_persisted
    def submit_arbitration_vote(
        self, dispute_id: int, vote_in_favor_of_initiator: bool, confidence: int, reasoning: str, arbitrator_address: str
    ) -> dict[str, Any]:
        """Submit arbitration vote (arbitrator only)"""
        arbitrator_address = self._canon(arbitrator_address)
        if arbitrator_address not in self.arbitrators:
            return {"success": False, "error": "Not an authorized arbitrator"}
        if dispute_id not in self.disputes:
            return {"success": False, "error": f"Dispute {dispute_id} not found"}
        dispute = self.disputes[dispute_id]
        if self._is_closed(dispute):
            return {"success": False, "error": "Dispute is closed"}
        if int(time.time()) > dispute.arbitration_deadline:
            return {"success": False, "error": "Arbitration deadline has passed"}
        # One arbitrator, one effective vote: an identical re-cast (e.g. a
        # client retry) is rejected, but a changed verdict is allowed and
        # appended like any other vote (#2387).
        if any(
            v.arbitrator == arbitrator_address
            and v.vote_in_favor_of_initiator == vote_in_favor_of_initiator
            and v.reasoning == reasoning
            for v in self.votes[dispute_id]
        ):
            return {"success": False, "error": "Duplicate arbitration vote"}
        vote = ArbitrationVote(
            dispute_id=dispute_id,
            arbitrator=arbitrator_address,
            vote_in_favor_of_initiator=vote_in_favor_of_initiator,
            confidence=confidence,
            reasoning=reasoning,
            vote_time=int(time.time()),
        )
        vote_id = len(self.votes[dispute_id])
        self.votes[dispute_id].append(vote)
        dispute.arbitrator_count += 1
        dispute.status = DisputeStatus.ARBITRATION_IN_PROGRESS
        self._maybe_resolve(dispute_id)
        logger.info("Submitted vote for dispute %s by %s", dispute_id, arbitrator_address)
        return {
            "success": True,
            "status": "Submitted",
            "vote_id": vote_id,
            "resolved": self.disputes[dispute_id].status == DisputeStatus.RESOLVED,
            "message": "Vote submitted successfully",
        }

    @_persisted
    def authorize_arbitrator(
        self, arbitrator_address: str, reputation_score: int, owner_address: str, owner_signature: str | None = None
    ) -> dict[str, Any]:
        """Authorize a new arbitrator (admin only).

        Bug 5: Previously accepted any owner_address without verification.
        Now requires that owner_address matches the contract's recorded owner
        and that owner_signature is a valid signature from the owner.
        """
        owner_address = owner_address.lower().strip()
        if not owner_address.startswith("0x"):
            owner_address = "0x" + owner_address

        # Verify caller is the contract owner
        if self._owner is None:
            return {"success": False, "status": "error", "message": "Contract owner not set"}
        if owner_address != self._owner:
            logger.warning("Unauthorized arbitrator authorization attempt by %s (owner: %s)", owner_address, self._owner)
            return {"success": False, "status": "error", "message": "Not contract owner"}

        # Verify owner signature (Bug 5: require signature proof of ownership)
        if not owner_signature:
            return {"success": False, "status": "error", "message": "Owner signature required"}
        sign_data = {
            "action": "authorize_arbitrator",
            "arbitrator_address": arbitrator_address,
            "reputation_score": reputation_score,
        }
        if not self._verify_owner_signature(owner_address, owner_signature, sign_data):
            return {"success": False, "status": "error", "message": "Invalid owner signature"}

        self.arbitrators[self._canon(arbitrator_address)] = reputation_score
        logger.info("Authorized arbitrator %s with reputation %s", arbitrator_address, reputation_score)
        return {"success": True, "status": "Authorized", "message": f"Arbitrator {arbitrator_address} authorized"}

    def _verify_owner_signature(self, owner_address: str, signature: str, sign_data: dict[str, Any]) -> bool:
        """Verify the owner's signature on authorization data."""
        import json

        message = json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode()
        try:
            from eth_utils import keccak

            from aitbc.crypto.signature_recovery import SignatureMalformed, verify_signature

            try:
                return verify_signature(keccak(message), signature, owner_address)
            except SignatureMalformed as e:
                logger.warning("Malformed owner signature (encoding fault): %s", e)
                return False
        except (ImportError, TypeError, ValueError, KeyError, AttributeError) as e:
            logger.warning("Owner signature verification failed: %s", e)
            return False

    def get_dispute(self, dispute_id: int) -> dict[str, Any]:
        """Get dispute details"""
        # Transaction (not just _refresh) so an overdue dispute is escalated
        # and persisted on read (#2387).
        with self._state_transaction(always_save=False):
            self._escalate_overdue()
            if dispute_id not in self.disputes:
                return {"success": False, "error": f"Dispute {dispute_id} not found"}
            dispute = self.disputes[dispute_id]
            return {"success": True, "dispute": asdict(dispute)}

    def get_dispute_evidence(self, dispute_id: int) -> dict[str, Any]:
        """Get all evidence for a dispute"""
        self._refresh()
        if dispute_id not in self.disputes:
            return {"success": False, "error": f"Dispute {dispute_id} not found"}
        return {
            "success": True,
            "evidence": [asdict(e) for e in self.evidence.get(dispute_id, [])],
            "count": len(self.evidence.get(dispute_id, [])),
        }

    def get_arbitration_votes(self, dispute_id: int) -> dict[str, Any]:
        """Get all arbitration votes for a dispute"""
        self._refresh()
        if dispute_id not in self.disputes:
            return {"success": False, "error": f"Dispute {dispute_id} not found"}
        return {
            "success": True,
            "votes": [asdict(v) for v in self.votes.get(dispute_id, [])],
            "count": len(self.votes.get(dispute_id, [])),
        }

    def get_user_disputes(self, user_address: str) -> dict[str, Any]:
        """Get all disputes for a user"""
        self._refresh()
        user_disputes = [
            d_id for d_id, d in self.disputes.items() if d.initiator == user_address or d.respondent == user_address
        ]
        return {"success": True, "user_address": user_address, "disputes": user_disputes, "count": len(user_disputes)}

    def get_arbitrator_disputes(self, arbitrator_address: str) -> dict[str, Any]:
        """Get all disputes assigned to an arbitrator"""
        self._refresh()
        arbitrator_disputes = [
            d_id
            for d_id, d in self.disputes.items()
            if d.status in [DisputeStatus.FILED, DisputeStatus.EVIDENCE_SUBMITTED, DisputeStatus.ARBITRATION_IN_PROGRESS]
        ]
        return {
            "success": True,
            "arbitrator_address": arbitrator_address,
            "disputes": arbitrator_disputes,
            "count": len(arbitrator_disputes),
        }

    def get_authorized_arbitrators(self) -> dict[str, Any]:
        """Get all authorized arbitrators"""
        self._refresh()
        return {"success": True, "arbitrators": list(self.arbitrators.keys()), "count": len(self.arbitrators)}

    def get_active_disputes(self) -> dict[str, Any]:
        """Get all active disputes"""
        self._refresh()
        active_disputes = [
            d_id
            for d_id, d in self.disputes.items()
            if d.status in [DisputeStatus.FILED, DisputeStatus.EVIDENCE_SUBMITTED, DisputeStatus.ARBITRATION_IN_PROGRESS]
        ]
        return {"success": True, "disputes": active_disputes, "count": len(active_disputes)}


dispute_resolution_contract = DisputeResolutionContract()
