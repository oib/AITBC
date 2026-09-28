"""Full and delta state synchronization from peers."""

from __future__ import annotations

import base64
from typing import Any

from sqlalchemy import desc, func as sqlfunc
from sqlmodel import select

from aitbc.sync import apply_state_diff, decode_state_diff

from .aux_state import upsert_aux_rows
from .base_models import Account, Block, ChainParameter, _to_ait_address, record_chain_parameter_history
from .config import is_block_producer, settings
from .logger import get_logger
from .metrics import metrics_registry
from .state import state_root_utils
from .sync_base import SyncBase
from .sync_divergence import report_divergence

logger = get_logger(__name__)


def _upsert_chain_parameters(
    session: Any,
    chain_id: str,
    parameters: list[dict[str, Any]],
    parameter_history: list[dict[str, Any]] | None = None,
) -> int:
    """Upsert ``chain_parameter`` rows shipped by the peer's sync response.

    Chain parameters are consensus state (``governance_executors``,
    ``bond_slash_authority``) but live outside the account state root, so
    neither the snapshot nor the diff carries them implicitly. Without this
    the executor gate is enforced only on the node that served the execute
    call — a silent divergence.

    ``applied_height`` rides along on each row so height-scoped lookups keep
    working on the follower; ``parameter_history`` ships the full version
    list so a superseded value stays resolvable for replayed blocks.
    """
    applied = 0
    for p in parameters:
        name = p.get("parameter")
        if not name:
            continue
        height = p.get("applied_height")
        existing = session.exec(
            select(ChainParameter).where(
                ChainParameter.chain_id == chain_id,
                ChainParameter.parameter == name,
            )
        ).first()
        if existing:
            existing.value = str(p.get("value", ""))
            existing.proposal_id = p.get("proposal_id")
            if height is not None:
                existing.applied_height = int(height)
        else:
            session.add(
                ChainParameter(
                    chain_id=chain_id,
                    parameter=name,
                    value=str(p.get("value", "")),
                    proposal_id=p.get("proposal_id"),
                    applied_height=int(height) if height is not None else None,
                )
            )
        applied += 1
    for h in parameter_history or []:
        name = h.get("parameter")
        height = h.get("applied_height")
        if not name or height is None:
            continue
        record_chain_parameter_history(
            session, chain_id, str(name), str(h.get("value", "")), h.get("proposal_id"), int(height)
        )
    return applied


class StateSyncMixin(SyncBase):
    """Pull account state snapshots and deltas from remote peers."""

    # Protocol base declares the attributes the concrete ChainSync sets.

    def _local_head(self, session: Any) -> tuple[int, str]:
        """Return (height, recorded state_root) of our highest local block."""
        head = session.exec(
            select(Block).where(Block.chain_id == self._chain_id).order_by(desc(Block.height))  # type: ignore[arg-type]
        ).first()
        if head is None:
            return 0, ""
        return int(head.height or 0), str(head.state_root or "")

    def _refuse_sync(self, reason: str, message: str, **extra: Any) -> dict[str, Any]:
        """Count and report a refused state sync (incident-27207 guards)."""
        metrics_registry.increment("state_sync_refused_total")
        metrics_registry.increment(f"state_sync_refused_{reason}_total")
        self._logger.warning("%s", message)
        return {"synced": 0, "refused": True, "reason": reason, **extra}

    def _producer_refusal(self) -> dict[str, Any] | None:
        if not is_block_producer():
            return None
        return self._refuse_sync(
            "block_producer",
            "state sync refused: this node produces blocks; its state comes from applying them",
        )

    async def sync_state_from(self, source_url: str) -> dict[str, Any]:
        """Pull account state snapshot from a peer and reconcile local accounts.

        Creates missing accounts and corrects balances/nonces to match
        the peer's state root.  Does NOT delete accounts that exist locally
        but not on the peer (those may be from local transactions).
        """
        if (refusal := self._producer_refusal()) is not None:
            return refusal
        self._logger.info("Starting state sync from %s", source_url)
        # Balances describe a chain. Copying them from a peer whose blocks we are rejecting leaves
        # the account table agreeing with the peer while the block history does not, so the head
        # block's state_root no longer describes the accounts underneath it — which is what this
        # function did 414 times during the V23-90 outage, healing the symptom it should report.
        # If the follower is far behind, do not pull a snapshot now. The block
        # sync path will build the state from the actual blocks and the snapshot
        # would only make old transactions fail their nonce checks.
        max_gap = getattr(settings, "state_sync_max_gap", 10)
        divergence, peer_height = await self.peer_head_divergence(source_url)
        with self._session_factory() as session:
            local_height, local_root = self._local_head(session)
        if peer_height - local_height > max_gap:
            self._logger.info(
                "State sync skipped: local head %s is %s blocks behind remote head %s (threshold %s)",
                local_height,
                peer_height - local_height,
                peer_height,
                max_gap,
                extra={"chain_id": self._chain_id, "local_head": local_height, "remote_head": peer_height},
            )
            return {
                "synced": 0,
                "skipped": True,
                "reason": "large gap",
                "local_head": local_height,
                "remote_head": peer_height,
            }
        if divergence is not None:
            report_divergence(self._chain_id, divergence)
            self._logger.error(
                "State sync skipped: our block history disagrees with %s at height %s, so its balances do not "
                "describe our chain",
                source_url,
                divergence.height,
                extra={"chain_id": self._chain_id, "divergence_height": divergence.height},
            )
            return {"synced": 0, "diverged": True, "divergence_height": divergence.height}
        try:
            resp = await self._client.get(
                f"{source_url}/rpc/state/snapshot",
                params={"chain_id": self._chain_id},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            self._logger.error("Failed to fetch state snapshot: %s", e)
            return {"synced": 0, "error": str(e)}

        remote_accounts = data.get("accounts", [])
        remote_root = data.get("state_root", "")
        remote_parameters = data.get("chain_parameters", [])
        remote_parameter_history = data.get("chain_parameter_history", [])
        remote_aux = data.get("aux_state", {}) or {}
        self._logger.info(
            "State snapshot: %s accounts, state_root=%s",
            len(remote_accounts),
            remote_root,
        )

        # The snapshot must describe OUR chain head. A source claiming a root
        # different from the recorded head root is diverged from us — applying
        # it would overwrite good state (incident 27207, the 22:03 poison path).
        if local_root and remote_root != local_root:
            return self._refuse_sync(
                "source_root_disagrees",
                f"state sync refused: {source_url} snapshot claims root {remote_root} "
                f"but our head {local_height} records {local_root}",
                local_head=local_height,
                remote_root=remote_root,
            )

        created = 0
        updated = 0
        with self._session_factory() as session:
            # Batch-fetch all existing accounts for the chain in one query
            # (eliminates the N+1 per-account session.get() lookup).
            existing_accounts = session.exec(select(Account).where(Account.chain_id == self._chain_id)).all()
            account_map: dict[str, Account] = {_to_ait_address(acc.address): acc for acc in existing_accounts}
            for acct_data in remote_accounts:
                addr = _to_ait_address(acct_data["address"])
                balance = acct_data["balance"]
                nonce = acct_data["nonce"]
                existing = account_map.get(addr)
                if existing is None:
                    new_account = Account(
                        chain_id=self._chain_id,
                        address=addr,
                        balance=balance,
                        nonce=nonce,
                    )
                    session.add(new_account)
                    account_map[addr] = new_account
                    created += 1
                elif existing.balance != balance or existing.nonce != nonce:
                    existing.balance = balance
                    existing.nonce = nonce
                    updated += 1
            _upsert_chain_parameters(session, self._chain_id, remote_parameters, remote_parameter_history)
            aux_counts = upsert_aux_rows(session, self._chain_id, remote_aux)
            if any(aux_counts.values()):
                self._logger.info("Aux state upserted from snapshot: %s", aux_counts)
            # Verify against the LOCAL head's recorded root before committing —
            # a snapshot that applied cleanly but produces a different root must
            # never reach the account table.
            session.flush()
            computed_hex = state_root_utils.compute_state_root_full(session, self._chain_id)
            if computed_hex is None:
                computed_hex = "0x" + "\x00" * 32
            if local_root and computed_hex != local_root:
                session.rollback()
                return self._refuse_sync(
                    "root_mismatch_local_head",
                    f"state sync rolled back: resulting root {computed_hex} != local head {local_height} "
                    f"recorded root {local_root} (source claimed {remote_root})",
                    local_head=local_height,
                    remote_root=remote_root,
                )
            session.commit()

        match = computed_hex == remote_root
        # A mismatch that survives a full account sync is not information: either the peer's root
        # covers a different account set than ours, or the roots are computed differently. Either
        # way it needs looking at, so it is a warning rather than the INFO it was for 414 cycles.
        log = self._logger.info if match else self._logger.warning
        log(
            "State sync complete: created=%s, updated=%s, local_root=%s, remote_root=%s, match=%s",
            created,
            updated,
            computed_hex,
            remote_root,
            match,
        )
        return {
            "synced": created + updated,
            "created": created,
            "updated": updated,
            "local_state_root": computed_hex,
            "remote_state_root": remote_root,
            "match": match,
        }

    async def delta_sync_from(self, source_url: str, from_height: int, to_height: int) -> dict[str, Any]:
        """Sync state delta from a peer (only changed accounts).

        Feature-flagged via settings.sync_delta_enabled. Falls back to
        full state sync (sync_state_from) when:
        - delta is too large (> sync_delta_threshold * full_state_size)
        - gap exceeds sync_delta_max_blocks
        - peer doesn't support delta endpoint
        - state root verification fails
        """
        if (refusal := self._producer_refusal()) is not None:
            return refusal
        if not getattr(settings, "sync_delta_enabled", False):
            return await self.sync_state_from(source_url)

        max_blocks = getattr(settings, "sync_delta_max_blocks", 100)
        if to_height - from_height > max_blocks:
            self._logger.info("Delta sync gap too large (%d > %d), using full sync", to_height - from_height, max_blocks)
            return await self.sync_state_from(source_url)

        # A delta may only describe our own head height. Older deltas replay
        # already-superseded state over the head (incident 27207, the 21:59
        # poison path); newer deltas describe blocks we have not imported —
        # block import must catch up first, so there is no snapshot fallback.
        with self._session_factory() as session:
            local_height, local_root = self._local_head(session)
        if to_height < local_height:
            return self._refuse_sync(
                "stale_target",
                f"delta sync refused: target {to_height} is behind our head {local_height}",
                local_head=local_height,
                to_height=to_height,
            )
        if to_height > local_height:
            return self._refuse_sync(
                "ahead_of_local_head",
                f"delta sync refused: target {to_height} is ahead of our head {local_height}; "
                "block import must catch up first",
                local_head=local_height,
                to_height=to_height,
            )

        self._logger.info("Starting delta sync from %s, heights %d -> %d", source_url, from_height, to_height)
        try:
            resp = await self._client.get(
                f"{source_url}/rpc/state/delta",
                params={"from_height": from_height, "to_height": to_height, "chain_id": self._chain_id},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            self._logger.warning("Delta sync endpoint failed (%s), falling back to full sync", e)
            return await self.sync_state_from(source_url)

        # Consensus-relevant chain parameters ride alongside the diff — the
        # account-only state root never covers them.
        remote_parameters = data.get("chain_parameters", [])
        remote_parameter_history = data.get("chain_parameter_history", [])
        remote_aux = data.get("aux_state", {}) or {}

        # The response contains an encoded StateDiff
        encoded_diff = data.get("diff")
        if not encoded_diff:
            self._logger.warning("No diff in delta sync response, falling back to full sync")
            return await self.sync_state_from(source_url)

        # Decode the StateDiff
        try:
            diff_bytes = base64.b64decode(encoded_diff) if isinstance(encoded_diff, str) else encoded_diff
            diff = decode_state_diff(diff_bytes)
        except Exception as e:
            self._logger.error("Failed to decode state diff: %s", e)
            return await self.sync_state_from(source_url)

        # The diff's claimed root must equal our head's recorded root — a
        # source describing a different state at our head height is diverged.
        if diff.to_state_root != local_root:
            return self._refuse_sync(
                "source_root_disagrees",
                f"delta sync refused: {source_url} claims root {diff.to_state_root} for height {to_height} "
                f"but our head records {local_root}",
                local_head=local_height,
                to_height=to_height,
                remote_root=diff.to_state_root,
            )

        # Check if delta is too large
        threshold = getattr(settings, "sync_delta_threshold", 0.5)
        # Estimate full state size from current account count
        with self._session_factory() as session:
            count_result = session.exec(
                select(sqlfunc.count()).select_from(Account).where(Account.chain_id == self._chain_id)
            ).first()
            total_accounts = count_result or 0
        full_state_size = total_accounts * 100  # rough estimate
        if diff.is_too_large(full_state_size, threshold=threshold):
            self._logger.info(
                "Delta too large (%d bytes > %d threshold), using full sync",
                diff.size_bytes(),
                int(threshold * full_state_size),
            )
            return await self.sync_state_from(source_url)

        # Apply delta to local state
        with self._session_factory() as session:
            existing_accounts = session.exec(select(Account).where(Account.chain_id == self._chain_id)).all()
            account_map: dict[str, Any] = {_to_ait_address(acc.address): acc for acc in existing_accounts}
            changed = apply_state_diff(diff, account_map)
            # Handle new accounts (created as dicts by apply_state_diff)
            for raw_addr in changed:
                addr = _to_ait_address(raw_addr)
                acc = account_map.get(addr)
                if acc is not None and isinstance(acc, dict):
                    # New account created as dict — convert to Account model, but only
                    # if the account is not already tracked in this session. The peer may
                    # mark an existing account as `is_new` when it lacks historical state.
                    db_acc = session.get(Account, (self._chain_id, addr))
                    if db_acc is not None:
                        db_acc.balance = acc["balance"]
                        db_acc.nonce = acc["nonce"]
                    else:
                        new_acc = Account(
                            chain_id=self._chain_id,
                            address=addr,
                            balance=acc["balance"],
                            nonce=acc["nonce"],
                        )
                        session.add(new_acc)
                elif acc is None:
                    # Account was deleted — already removed from map, need to delete from DB
                    db_acc = session.exec(
                        select(Account).where(Account.chain_id == self._chain_id, Account.address == addr)
                    ).first()
                    if db_acc:
                        session.delete(db_acc)
                # Existing accounts were mutated in place (SQLModel tracks changes)
            _upsert_chain_parameters(session, self._chain_id, remote_parameters, remote_parameter_history)
            aux_counts = upsert_aux_rows(session, self._chain_id, remote_aux)
            if any(aux_counts.values()):
                self._logger.info("Aux state upserted from delta: %s", aux_counts)
            # Verify against the LOCAL head's recorded root in the same
            # transaction, before commit — the diff's claimed root was already
            # checked above; this catches a diff whose contents do not
            # reproduce our head state.
            session.flush()
            computed_hex = state_root_utils.compute_state_root_full(session, self._chain_id)
            if computed_hex is None:
                computed_hex = "0x" + "\x00" * 32
            if computed_hex != local_root:
                session.rollback()
                return self._refuse_sync(
                    "root_mismatch_local_head",
                    f"delta sync rolled back: resulting root {computed_hex} != local head {local_height} "
                    f"recorded root {local_root} (source claimed {diff.to_state_root})",
                    local_head=local_height,
                    to_height=to_height,
                )
            session.commit()

        self._logger.info("Delta sync complete: %d accounts changed, state root matches", len(changed))
        return {
            "synced": len(changed),
            "created": sum(1 for c in diff.changes if c.is_new),
            "updated": sum(1 for c in diff.changes if not c.is_new and not c.is_deleted),
            "deleted": sum(1 for c in diff.changes if c.is_deleted),
            "local_state_root": computed_hex,
            "remote_state_root": diff.to_state_root,
            "match": True,
            "mode": "delta",
        }
