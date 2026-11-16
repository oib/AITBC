"""Round-lock and attestation-lock persistence for ``RemoteAttestationService`` (#1950 pure-move split)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any


from ..config import settings
from ..metrics import metrics_registry
from .remote_attestation_crypto import (
    _attestation_signature_domain,
    _lock_lapse_seconds,
    attestation_lock_window_seconds,
)
from .remote_attestation_round_lock_types import _RoundLockEntry, _RoundLockVerdict
from . import remote_attestation as _ra

if TYPE_CHECKING:
    import logging

    logger: logging.Logger
else:
    logger = _ra.logger

from .remote_attestation import _EvidenceMixin


class _RoundLockMixin(_EvidenceMixin):
    def _header_age_seconds(self, header: dict[str, Any]) -> float | None:
        """Seconds between this node's clock and the header's signed
        timestamp (negative = header is in the future). None when the header
        carries no parseable timestamp -- headers predate v9 without one."""
        raw = header.get("timestamp")
        if raw is None or raw == "":
            return None
        try:
            ts = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return None
        if ts.tzinfo is None:
            # Block timestamps are stored as naive UTC.
            ts = ts.replace(tzinfo=UTC)
        return self._now_epoch() - ts.timestamp()

    def _header_freshness_refusal(self, header_age: float | None) -> str | None:
        """Refusal reason for a stale or future header, else None.

        A header with no timestamp skips the bound (counted): the v9 hash
        recompute in `_v9_check_transactions` binds the timestamp, so once v9
        is active a request cannot omit it and still pass.
        """
        max_age = float(getattr(settings, "attestation_header_max_age_seconds", 60.0))
        if max_age <= 0:
            return None
        if header_age is None:
            metrics_registry.increment("attestation_header_timestamp_missing_total")
            return None
        if header_age > max_age:
            return "stale_header"
        skew = float(getattr(settings, "attestation_header_future_skew_seconds", 10.0))
        if header_age < -skew:
            return "future_header"
        return None

    def _signed_once_contains(self, height: int, block_hash: str, domain: str | None) -> bool:
        """#1298: True when (height, block_hash) was already signed under
        ``domain`` — the domain is part of the acceptance key, so a signing
        under another domain does not count (T9-class coexistence)."""
        domains = self._signed_once.get(height)
        if not domains:
            return False
        return block_hash in domains.get(domain, ())

    def _signed_once_add(self, height: int, block_hash: str, domain: str | None) -> None:
        """#1298: record a signing of (height, block_hash) under ``domain``."""
        self._signed_once.setdefault(height, {}).setdefault(domain, set()).add(block_hash)

    def _record_attestation_lock(
        self, height: int, block_hash: str, proposer: str, signature_domain: str | None = None
    ) -> bool:
        """Record that this node's validator key(s) signed block `block_hash`
        at `height`. Locks expire by wall clock in `attestation_lock`.

        #1245: only the FIRST signing of (height, hash) starts the window.
        A duplicate returns False and leaves the lock untouched, so replaying
        a request can never extend or re-arm it. #1298: ``signature_domain``
        is part of the acceptance key — the same (height, hash) signed under
        a different domain is a distinct signing, not a duplicate."""
        self._ensure_round_locks_loaded()
        if self._signed_once_contains(height, block_hash, signature_domain):
            return False
        now = _ra.time.monotonic()
        # #1298 T15: each height prunes at 2x ITS effective lock window —
        # pre-activation heights keep the 60s round window, post-activation
        # heights the 130s lapse, so a live lock is never dropped early.
        self._attested = {
            h: {d: e for d, e in domains.items() if now - e[2] < 2 * attestation_lock_window_seconds(h)}
            for h, domains in self._attested.items()
        }
        self._attested = {h: domains for h, domains in self._attested.items() if domains}
        self._attested.setdefault(height, {})[signature_domain] = (block_hash, proposer, now)
        self._signed_once_add(height, block_hash, signature_domain)
        self._prune_signed_once()
        return True

    def _prune_signed_once(self) -> None:
        """Forget signings for heights below the local tip; hard-cap the rest.

        Pruned by height, never by wall clock: a replay must not be able to
        outwait a timer. A height below our own tip is settled, so a rival
        there no longer matters. The tip is the one the v9 check last read --
        no extra database access on the attestation path. The cap bounds
        memory when no tip has been read (shadow mode, no session factory)."""
        tip_height = self._tip_height_hint
        if tip_height is not None:
            self._signed_once = {h: s for h, s in self._signed_once.items() if h >= tip_height}
        self._signed_once = {h: domains for h, domains in self._signed_once.items() if domains}
        cap = _ra.SIGNED_ONCE_MAX_HEIGHTS
        if len(self._signed_once) > cap:
            keep = sorted(self._signed_once)[-cap:]
            self._signed_once = {h: self._signed_once[h] for h in keep}

    def attestation_lock(
        self, height: int, window_seconds: float, signature_domain: str | None = None
    ) -> tuple[str, str] | None:
        """Return ``(block_hash, proposer)`` this validator attested at
        ``height`` if the lock is still live, else None. Expired entries are
        dropped lazily. #1298: the durable journal is loaded first so a
        restart cannot forget a live lock (proposer-side callers included).

        ``signature_domain`` scopes the lookup to one domain's entries;
        ``None`` matches entries under ANY domain — the proposer-side
        suppression in ``_honor_attestation_lock`` uses that wider view so a
        signing under any domain still suppresses a rival proposal."""
        self._ensure_round_locks_loaded()
        entries = self._attested.get(height)
        if not entries:
            return None
        now = _ra.time.monotonic()
        best: tuple[str, str, float] | None = None
        for dom, entry in list(entries.items()):
            block_hash, proposer, signed_at = entry
            if now - signed_at >= window_seconds:
                del entries[dom]
                continue
            if signature_domain is not None and dom != signature_domain:
                continue
            if best is None or signed_at > best[2]:
                best = entry
        if not entries:
            del self._attested[height]
        return (best[0], best[1]) if best is not None else None

    def _round_lock_enabled(self) -> bool:
        return bool(getattr(settings, "attestation_round_lock_enabled", False))

    def _round_seconds(self) -> int:
        return int(float(getattr(settings, "consensus_proposer_round_seconds", 60)))

    def _derive_request_round(self, header: dict) -> int | None:
        """Independently derive the proposer round for an attest_request header.

        Mirrors the proposer-side derivation exactly: ``proposer_round`` over
        (sealed parent timestamp, proposed block timestamp, round window).
        Returns None when either timestamp or the parent row is unavailable —
        callers must treat that as underivable, never as round 0.
        """
        try:
            ts_raw = header.get("timestamp")
            block_ts = ts_raw if isinstance(ts_raw, datetime) else datetime.fromisoformat(str(ts_raw))
        except (TypeError, ValueError):
            return None
        parent_ts = self._parent_timestamp(str(header.get("parent_hash", "")))
        if parent_ts is None:
            return None
        try:
            from .multi_validator_poa import proposer_round

            return proposer_round(parent_ts, block_ts, self._round_seconds())
        except Exception as e:  # noqa: BLE001 - optional consensus helper, None means unavailable
            logger.debug("consensus helper failed: %s", type(e).__name__)
            return None

    def _collect_round_for_block(self, block: Any) -> int | None:
        """Round for the block this node is about to attest-collect.

        Same derivation attesters apply to the request header, so the
        declared round always matches their independent check.
        """
        parent_ts = self._parent_timestamp(str(getattr(block, "parent_hash", "") or ""))
        ts = getattr(block, "timestamp", None)
        if ts is None or parent_ts is None:
            return None
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                return None
        try:
            from .multi_validator_poa import proposer_round

            return proposer_round(parent_ts, ts, self._round_seconds())
        except Exception as e:  # noqa: BLE001 - optional consensus helper, None means unavailable
            logger.debug("consensus helper failed: %s", type(e).__name__)
            return None

    def _unlock_window(self) -> float:
        """U2 protocol-evidence window: the applicable consensus_gates span.

        Defaults to the attestation-collection timeout + 1s margin, plus the
        PBFT view-change timeout when PBFT is armed. An explicit
        ``attestation_round_unlock_window_seconds`` wins.
        """
        override = float(getattr(settings, "attestation_round_unlock_window_seconds", 0.0) or 0.0)
        if override > 0:
            return override
        window = float(getattr(settings, "multi_validator_attestation_timeout_seconds", 15.0) or 15.0)
        if getattr(settings, "pbft_consensus_enabled", False):
            window += float(getattr(settings, "pbft_view_change_timeout", 30) or 0.0)
        return window + 1.0

    def _record_request_seen(self, height: int, round_: int) -> None:
        """Note the first time an authentic request for (height, round) arrived.

        U2 evidence: a later-round request's existence proves earlier rounds
        at this height were minted and (once the gates window elapses) are
        irrevocably closed.
        """
        now = _ra.time.monotonic()
        rounds = self._requests_seen.setdefault(height, {})
        if round_ not in rounds or now < rounds[round_]:
            rounds[round_] = now
        if len(self._requests_seen) > 32:
            keep_above = max(self._requests_seen) - 16
            self._requests_seen = {h: r for h, r in self._requests_seen.items() if h >= keep_above}

    def _u2_satisfied(
        self,
        height: int,
        locked_round: int,
        entry: _RoundLockEntry,
        round_: int,
        now: float,
        window: float,
        unlock_window: float,
    ) -> bool:
        """U2 failure evidence for a locked round (AD ruling: full gates window).

        Two routes, either sufficient:
          fallback — the monotonic lock window elapsed (liveness recovery;
            never overrides U1 or the tip check);
          protocol — an attest_request at a strictly later round (up to the
            round being signed) was observed at this height AND the locked
            round's full gates window has elapsed since its request was seen
            (its collection is closed and cannot be counted again).
        """
        if now - entry.signed_at >= window:
            return True
        if entry.request_seen_at is None:
            return False
        rounds = self._requests_seen.get(height) or {}
        if not any(locked_round < r <= round_ for r in rounds):
            return False
        return (now - entry.request_seen_at) >= unlock_window

    def round_lock_verdict(self, height: int, round_: int, block_hash: str) -> _RoundLockVerdict:
        """Shared U1/U2 transition check for attester signing and proposer suppression.

        Signing (or proposing) ``block_hash`` at ``(height, round_)`` is
        permitted iff every locked entry at ``height`` binding a DIFFERENT
        hash has satisfied unlock evidence:

          U1 — ``round_`` is strictly later than the locked round; and
          U2 — the locked round's failure is evidenced (see ``_u2_satisfied``).

        Both enforcement points call this single function so attester and
        proposer can never disagree about whether a lock transition is legal.
        """
        self._ensure_round_locks_loaded()
        now = _ra.time.monotonic()
        # #1298 T15: the U2 monotonic-fallback window is the same effective
        # attestation-lock lapse the attester path enforces.
        window = attestation_lock_window_seconds(height)
        unlock_window = self._unlock_window()
        for (lh, lr, _domain), entry in self._round_locks.items():
            if lh != height or entry.block_hash == block_hash:
                continue
            if round_ <= lr:
                return _RoundLockVerdict(
                    False,
                    f"round_not_advanced:locked_r{lr}_req_r{round_}",
                    entry.block_hash,
                    entry.proposer,
                )
            if not self._u2_satisfied(height, lr, entry, round_, now, window, unlock_window):
                return _RoundLockVerdict(False, "round_failure_unproven", entry.block_hash, entry.proposer)
        return _RoundLockVerdict(True, None)

    def _ensure_round_locks_loaded(self) -> None:
        if self._round_locks_loaded:
            return
        self._round_locks_loaded = True
        self._load_round_locks()

    def _load_round_locks(self) -> None:
        """Restore persisted signed (height, round, hash) records (#1242/D)
        plus the always-on attestation-lock journal records (#1298).

        Wall-clock timestamps are converted into monotonic-equivalent ages at
        load so the same U1/U2 math applies after restart. Records older than
        two lock windows are dropped — they can no longer bind anything.
        """
        try:
            if not self._round_locks_path.exists():
                return
            data = json.loads(self._round_locks_path.read_text())
            if data.get("chain_id") != self._chain_id:
                return
            now_mono = _ra.time.monotonic()
            now_wall = _ra.time.time()
            for rec in data.get("records", []):
                try:
                    if rec.get("kind") == "attestation":
                        self._load_attestation_lock_record(rec, now_mono, now_wall)
                        continue
                    h, r = int(rec["h"]), int(rec["r"])
                    signed_wall = float(rec["signed_wall"])
                    age_wall = now_wall - signed_wall
                    # #1298 T15: prune at 2x the record height's effective
                    # lock window (post-activation lapse, not the 60s round).
                    if age_wall >= 2 * attestation_lock_window_seconds(h):
                        continue
                    req_wall = rec.get("request_seen_wall")
                    # #1298: the record's signature_domain is part of the
                    # acceptance key — absent/malformed reads as the legacy
                    # (None) domain so pre-#1298 records reseed unchanged.
                    raw_domain = rec.get("signature_domain")
                    domain = raw_domain if isinstance(raw_domain, str) else None
                    self._round_locks[(h, r, domain)] = _RoundLockEntry(
                        str(rec["hash"]),
                        str(rec.get("proposer", "")),
                        now_mono - age_wall,
                        signed_wall,
                        (now_mono - (now_wall - float(req_wall))) if req_wall is not None else None,
                        float(req_wall) if req_wall is not None else None,
                        signature_domain=domain,
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            # Reseeded ``_signed_once`` entries prune by height/cap exactly
            # like live ones.
            self._prune_signed_once()
        except (ArithmeticError, AttributeError, KeyError, OSError, RecursionError, RuntimeError, TypeError, ValueError) as e:
            logger.warning("Failed to load round-lock records for %s: %s", self._chain_id, e)

    def _load_attestation_lock_record(self, rec: dict[str, Any], now_mono: float, now_wall: float) -> None:
        """Reseed one durable attestation-lock journal record (#1298 v2.5).

        ``signed_wall`` converts to a monotonic-equivalent timestamp with the
        same ``now_mono - (now_wall - signed_wall)`` math ``_load_round_locks``
        uses, clamped at zero age so a backwards wall-clock step cannot mint
        a negative age. Records older than two lock-lapse windows (260s at
        defaults — v2.6 defect-1 fix) are dropped: they can no longer bind
        anything. Records without a derived round or domain tag (legacy or
        underivable) still reseed — the lock state is (height, hash,
        domain)-keyed, so coverage is never weaker than a round-tagged
        record (T21).
        """
        h = int(rec["h"])
        block_hash = str(rec["hash"])
        signed_wall = float(rec["signed_wall"])
        age_wall = max(0.0, now_wall - signed_wall)
        if age_wall >= 2 * _lock_lapse_seconds():
            return
        signed_at = now_mono - age_wall
        proposer = str(rec.get("proposer", ""))
        raw_round = rec.get("derived_round")
        try:
            derived_round = int(raw_round) if raw_round is not None else None
        except (TypeError, ValueError):
            derived_round = None
        domain = rec.get("signature_domain")
        domain = domain if isinstance(domain, str) else None
        key = (h, block_hash, domain)
        self._attested_lock_records[key] = {
            "proposer": proposer,
            "signed_wall": signed_wall,
            "derived_round": derived_round,
            "signature_domain": domain,
        }
        self._signed_once_add(h, block_hash, domain)
        # ``_attested`` keeps the LATEST signing per (height, domain) — the
        # same last-write-wins semantics ``_record_attestation_lock`` applies.
        domains = self._attested.setdefault(h, {})
        current = domains.get(domain)
        if current is None or signed_at > current[2]:
            domains[domain] = (block_hash, proposer, signed_at)

    def _persist_round_locks(self) -> None:
        """Atomically persist signed (height, round, hash) records.

        Temp-file + fsync + rename so a crash cannot leave a torn record.
        Raises on failure — the caller must not release a signature it could
        not durably record.
        """
        import os

        self._round_locks_path.parent.mkdir(parents=True, exist_ok=True)
        now_wall = _ra.time.time()
        payload_records = []
        for (h, r, _domain), e in self._round_locks.items():
            # #1298 T15: 2x the record height's effective lock window.
            if now_wall - e.signed_wall >= 2 * attestation_lock_window_seconds(h):
                continue
            record = {
                "h": h,
                "r": r,
                "hash": e.block_hash,
                "proposer": e.proposer,
                "signed_wall": e.signed_wall,
                "request_seen_wall": e.request_seen_wall,
            }
            # #1298: signature_domain joins the acceptance key — written only
            # when set so legacy (pre-activation) records stay byte-identical.
            if e.signature_domain is not None:
                record["signature_domain"] = e.signature_domain
            payload_records.append(record)
        # #1298: the always-on attestation-lock journal shares this file.
        # kind="attestation" records carry no "r" key, so a pre-#1298 build
        # reading this file skips them (KeyError) instead of misreading them
        # as round locks. Pruned by WALL AGE at 2x the lock-lapse window
        # (260s at defaults), never the 60s round window — v2.6 defect 1.
        lapse_prune = 2 * _lock_lapse_seconds()
        for (h, block_hash, _domain), rec in self._attested_lock_records.items():
            signed_wall = float(rec["signed_wall"])
            if now_wall - signed_wall >= lapse_prune:
                continue
            payload_records.append(
                {
                    "kind": "attestation",
                    "h": h,
                    "hash": block_hash,
                    "proposer": rec["proposer"],
                    "signed_wall": signed_wall,
                    "derived_round": rec["derived_round"],
                    "signature_domain": rec["signature_domain"],
                }
            )
        payload = json.dumps({"version": 1, "chain_id": self._chain_id, "records": payload_records})
        tmp = self._round_locks_path.with_name(self._round_locks_path.name + ".tmp")
        with open(tmp, "w") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self._round_locks_path)
        try:
            dir_fd = os.open(str(self._round_locks_path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    def _record_round_lock(
        self, height: int, round_: int, block_hash: str, proposer: str, signature_domain: str | None = None
    ) -> None:
        """Record + durably persist that this node signed ``block_hash`` at
        ``(height, round_)``. Called BEFORE the signature is released; a
        persistence failure propagates so no signature goes out unrecorded."""
        self._ensure_round_locks_loaded()
        now_mono = _ra.time.monotonic()
        now_wall = _ra.time.time()
        # #1298 T15: prune each entry at 2x ITS height's effective lock
        # window — post-activation heights keep records for the full lapse.
        self._round_locks = {
            k: e for k, e in self._round_locks.items() if now_mono - e.signed_at < 2 * attestation_lock_window_seconds(k[0])
        }
        key = (height, round_, signature_domain)
        if key not in self._round_locks:
            req_seen = self._requests_seen.get(height, {}).get(round_)
            req_seen_wall = now_wall - (now_mono - req_seen) if req_seen is not None else None
            self._round_locks[key] = _RoundLockEntry(
                block_hash, proposer, now_mono, now_wall, req_seen, req_seen_wall, signature_domain=signature_domain
            )
        self._persist_round_locks()

    def _record_attestation_lock_journal(
        self,
        height: int,
        block_hash: str,
        proposer: str,
        header: dict[str, Any],
    ) -> None:
        """Durably record an attestation-lock signing BEFORE release (#1298).

        Always-on counterpart of ``_record_round_lock`` for the non-round-lock
        path: the record carries the signing wall-clock time, the best-effort
        derived round, and the signature domain in effect, so a restart can
        re-derive ``_attested``/``_signed_once`` instead of forgetting every
        lock (design v2.5 restart fix — best-effort reseed was rejected).
        Idempotent per (height, hash, signature_domain): a duplicate request
        adds nothing and skips the fsync. A persistence failure propagates —
        the caller must not release a signature it could not durably record.
        """
        self._ensure_round_locks_loaded()
        domain = _attestation_signature_domain(height)
        # #1298: the domain is part of the journal key — the same
        # (height, hash) signed under another domain is a distinct record.
        key = (height, block_hash, domain)
        if key in self._attested_lock_records:
            return
        now_wall = _ra.time.time()
        lapse_prune = 2 * _lock_lapse_seconds()
        self._attested_lock_records = {
            k: r for k, r in self._attested_lock_records.items() if now_wall - float(r["signed_wall"]) < lapse_prune
        }
        record = {
            "proposer": proposer,
            "signed_wall": now_wall,
            "derived_round": self._derive_request_round(header),
            "signature_domain": domain,
        }
        self._attested_lock_records[key] = record
        try:
            self._persist_round_locks()
        except (ArithmeticError, AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            # Roll back the in-memory record: an unpersisted entry must not
            # dedup a later retry into releasing a signature it never
            # durably recorded (fail-closed, not fail-open).
            if self._attested_lock_records.get(key) is record:
                del self._attested_lock_records[key]
            raise

    def _record_pre_sign_lock(
        self,
        height: int,
        request_round: int | None,
        header_hash: str,
        proposer: str,
        header: dict[str, Any],
        round_lock: bool,
    ) -> bool:
        """Persist the durable lock record for this signing; False = refuse.

        Round-lock path keeps the ``_record_round_lock`` contract — a
        persistence failure propagates. The attestation-lock journal path
        (#1298) catches the failure, counts it, and refuses the signature
        (fail-closed): the node stops attesting until the disk recovers,
        which is the detectable liveness cost the design accepted over
        silently losing restart coverage.
        """
        if round_lock and request_round is not None:
            self._record_round_lock(height, request_round, header_hash, proposer, _attestation_signature_domain(height))
            return True
        try:
            self._record_attestation_lock_journal(height, header_hash, proposer, header)
        except (ImportError, ArithmeticError, AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as e:
            metrics_registry.increment("attestation_lock_persist_failure_total")
            logger.error(
                "Attestation-lock journal persist failed at height %s — refusing to sign: %s",
                height,
                e,
            )
            return False
        return True
