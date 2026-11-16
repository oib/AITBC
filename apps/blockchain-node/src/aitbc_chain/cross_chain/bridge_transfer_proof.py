"""Cross-chain bridge transfer — Proof construction (``build_proof``) and proof validation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select


from ..config import settings
from ..logger import get_logger
from ..models import Block, BridgeBlockHeader, CrossChainTransfer, Transaction
from .bridge_base import BridgeBase, _OPS_ERRORS
from .bridge_leaf import lock_leaf_v2_active, lock_leaf_value, unknown_lock_leaf
from .bridge_tx_root import (
    build_tx_bridge_trie,
    canonical_lock_fields,
    stored_lock_body,
    tx_only_root_active,
)

logger = get_logger(__name__)


class BridgeTransferProofMixin(BridgeBase):
    def build_proof(
        self,
        transfer_id: str,
        source_chain: str | None = None,
        block_height: int = 1,
        block_hash: str = "",
    ) -> dict[str, Any]:
        """Build a Merkle proof for a locked cross-chain transfer.

        v0.7.3: Looks up the source block that includes the lock, rebuilds the
        bridge event trie from all BRIDGE_LOCK transactions in that block, and
        returns the block-signed proposer/validator signatures plus the Merkle
        proof for this transfer.
        """
        source_chain = source_chain or str(getattr(settings, "chain_id", "") or "")
        with self._session_for(source_chain) as session:
            # #1940 F5: resolve the source through the shared locator
            # precedence — explicit block_hash, caller block_height, the
            # transfer_id-as-tx_hash row, then the CCT source_tx_hash block
            # hint. A resolved NEW-ERA source is proven from sealed tx rows
            # and the shared contract; anything else falls through to the
            # legacy path, whose own block resolution is funnel-checked
            # below before any CCT-derived trie is built.
            resolved_block, resolved_tx = self._resolve_proof_lock_source(
                session, source_chain, transfer_id, block_height, block_hash
            )
            if resolved_block is not None:
                return self._build_proof_tx_only(session, resolved_block, resolved_tx, source_chain)
            record = session.get(CrossChainTransfer, transfer_id)
            if not record:
                raise ValueError(f"Transfer not found: {transfer_id}")

            # Prefer the block that recorded the lock transaction.
            lock_tx = session.exec(
                select(Transaction).where(
                    Transaction.chain_id == source_chain,
                    Transaction.tx_hash == (record.source_tx_hash or transfer_id),
                )
            ).first()
            if lock_tx and lock_tx.block_height:
                block_height = lock_tx.block_height
            elif lock_tx is not None and not block_hash:
                # The lock exists but is not sealed into a block yet — a proof
                # built now would anchor to the wrong block. Report the real
                # state instead of falling back to the default height.
                raise ValueError(f"Lock transaction {record.source_tx_hash or transfer_id} is not sealed in a block yet")

            block = session.exec(
                select(Block).where(
                    Block.chain_id == source_chain,
                    Block.height == block_height,
                )
            ).first()
            if block is None:
                raise ValueError(f"Source block not found: {source_chain} height {block_height}")

            # #1940 F5 final funnel: the block THIS path actually resolved
            # decides the era — a new-era source must never be served
            # through the legacy CCT-derived trie, and a strong explicit
            # block_hash may not be silently overridden.
            funnel = self._proof_new_era_funnel(session, block, source_chain, transfer_id, block_hash)
            if funnel is not None:
                return funnel

            from ..state.merkle_patricia_trie import MerklePatriciaTrie

            trie = MerklePatriciaTrie()
            # GAP-47: detect lock txs by the persisted ``type`` column, not
            # only ``payload["type"]`` — under block-scoped pre-registration
            # the mempool entry carries no ``payload`` key, so the sealed row
            # has ``payload={}`` and the column is the only reliable marker.
            lock_txs = [
                tx for tx in block.transactions if (tx.type or (tx.payload or {}).get("type", "")).upper() == "BRIDGE_LOCK"
            ]
            transfer_ids = [tx.tx_hash for tx in lock_txs]
            records = session.exec(
                select(CrossChainTransfer).where(
                    CrossChainTransfer.source_chain == source_chain,
                    CrossChainTransfer.transfer_id.in_(transfer_ids),  # type: ignore[attr-defined]
                )
            ).all()
            record_map = {r.transfer_id: r for r in records}
            for tx in lock_txs:
                tx_record = record_map.get(tx.tx_hash)
                if tx_record is None:
                    value = unknown_lock_leaf(tx.tx_hash)
                else:
                    value = self._build_lock_event_value(tx_record, block.height)
                trie.put(tx.tx_hash.encode(), value.encode())

            computed_root = "0x" + trie.get_root().hex()
            if computed_root != (block.bridge_state_root or ""):
                raise ValueError("Computed bridge state root does not match block")

            lock_tx_hash = record.source_tx_hash or transfer_id
            lock_value = self._build_lock_event_value(record, block.height).encode()
            proof_bytes = trie.get_proof(lock_tx_hash.encode())

            validator_signatures = self._proof_validator_signatures(block, source_chain)

            return {
                "source_chain": record.source_chain,
                "target_chain": record.target_chain,
                "lock_tx_hash": lock_tx_hash,
                "amount": record.amount,
                "sender": record.sender,
                "recipient": record.recipient,
                "asset": record.asset,
                "chain_id": record.source_chain,
                "block_height": block.height,
                "block_hash": block.hash,
                "proposer": block.proposer,
                "parent_hash": block.parent_hash,
                "state_root": block.state_root or "",
                "bridge_state_root": block.bridge_state_root or "",
                "merkle_proof": [p.hex() for p in proof_bytes],
                "lock_event": lock_value.decode(),
                "proposer_signature": block.signature,
                "validator_signatures": validator_signatures,
            }

    @staticmethod
    def _row_matches_transfer_id(row: Any, source_chain: str, height: int, transfer_id: str) -> bool:
        """True when the sealed row's canonical signed descriptor names ``transfer_id``."""
        try:
            fields = canonical_lock_fields(stored_lock_body(row), str(row.tx_hash), source_chain, height)
        except (TypeError, ValueError):
            return False
        return fields.transfer_id == transfer_id

    def _canonical_lock_matches_in_block(self, session: Any, block: Block, source_chain: str, transfer_id: str) -> list[Any]:
        """Sealed rows in ``block`` whose canonical signed id is ``transfer_id``.

        Multiple matches are ambiguous and refuse — a proof must never pick
        one of two locks that claim the same signed id.
        """
        matches: list[Any] = []
        for tx in session.exec(
            select(Transaction).where(
                Transaction.chain_id == source_chain,
                Transaction.block_height == block.height,
                # #1940 F5 review F2: only confirmed sealed rows may be
                # selected — _build_proof_tx_only admits exactly this
                # status into the trie, so matching anything else could
                # serve a proof with an empty merkle path.
                Transaction.status == "confirmed",
            )
        ).all():
            if self._row_matches_transfer_id(tx, source_chain, int(block.height), transfer_id):
                matches.append(tx)
        if len(matches) > 1:
            raise ValueError(f"ambiguous lock matches for transfer_id {transfer_id} in block {block.height}")
        return matches

    def _strict_source_from_block(
        self, session: Any, block: Block, source_chain: str, transfer_id: str, *, authoritative: bool
    ) -> tuple[Block | None, Any | None]:
        """Canonical-id match inside one new-era candidate block."""
        matches = self._canonical_lock_matches_in_block(session, block, source_chain, transfer_id)
        if not matches:
            if authoritative:
                raise ValueError(f"Lock not found for transfer_id {transfer_id} in explicitly located block {block.height}")
            return (None, None)
        return (block, matches[0])

    def _resolve_proof_lock_source(
        self,
        session: Any,
        source_chain: str,
        transfer_id: str,
        block_height: int,
        block_hash: str,
    ) -> tuple[Block | None, Any | None]:
        """#1940 F5: shared source resolver — returns (Block, lock row) for a
        NEW-ERA source, (None, None) when the source is absent or historical.

        Locator precedence: caller ``block_hash`` (authoritative — a missing
        block or absent lock refuses rather than silently selecting another),
        caller positive strict-int ``block_height`` when it contains the
        requested canonical id (the legacy default of 1 never blocks other
        locators), ``transfer_id``-as-``tx_hash`` sealed row only when its
        canonical signed id matches, then ``CrossChainTransfer.
        source_tx_hash`` as a BLOCK LOCATOR whose block is scanned for the
        requested id. No whole-chain scan; CCT fields other than the locator
        are never consulted.
        """
        if block_hash:
            return self._proof_source_by_block_hash(session, source_chain, transfer_id, block_hash)
        for stage in (
            self._proof_source_by_height,
            self._proof_source_by_tx_row,
            self._proof_source_by_cct_hint,
        ):
            resolved = stage(session, source_chain, transfer_id, block_height)
            if resolved[0] is not None:
                return resolved
        return (None, None)

    def _proof_source_by_block_hash(
        self, session: Any, source_chain: str, transfer_id: str, block_hash: str
    ) -> tuple[Block | None, Any | None]:
        block = session.exec(select(Block).where(Block.chain_id == source_chain, Block.hash == block_hash)).first()
        if block is not None and tx_only_root_active(session, source_chain, int(block.height)):
            return self._strict_source_from_block(session, block, source_chain, transfer_id, authoritative=True)
        return (None, None)

    def _proof_source_by_height(
        self, session: Any, source_chain: str, transfer_id: str, block_height: int
    ) -> tuple[Block | None, Any | None]:
        if not (isinstance(block_height, int) and not isinstance(block_height, bool) and block_height > 0):
            return (None, None)
        block = session.exec(select(Block).where(Block.chain_id == source_chain, Block.height == block_height)).first()
        if block is None or not tx_only_root_active(session, source_chain, int(block.height)):
            return (None, None)
        return self._strict_source_from_block(session, block, source_chain, transfer_id, authoritative=False)

    def _proof_source_by_tx_row(
        self, session: Any, source_chain: str, transfer_id: str, block_height: int
    ) -> tuple[Block | None, Any | None]:
        lock_tx = session.exec(
            select(Transaction).where(
                Transaction.chain_id == source_chain,
                Transaction.tx_hash == transfer_id,
            )
        ).first()
        if lock_tx is None or not getattr(lock_tx, "block_height", None):
            return (None, None)
        if not self._row_matches_transfer_id(lock_tx, source_chain, int(lock_tx.block_height), transfer_id):
            return (None, None)
        block = session.exec(
            select(Block).where(
                Block.chain_id == source_chain,
                Block.height == lock_tx.block_height,
            )
        ).first()
        if block is not None and tx_only_root_active(session, source_chain, int(block.height)):
            # #1940 F5 review F1: resolve through the same strict block scan
            # as every other locator — the tx_hash==transfer_id shortcut must
            # not bypass the multi-match ambiguity refusal or the confirmed
            # status predicate. The scan is deterministic, so a unique match
            # returns this same lock_tx.
            return self._strict_source_from_block(session, block, source_chain, transfer_id, authoritative=False)
        return (None, None)

    def _proof_source_by_cct_hint(
        self, session: Any, source_chain: str, transfer_id: str, block_height: int
    ) -> tuple[Block | None, Any | None]:
        record = session.get(CrossChainTransfer, transfer_id)
        if record is None or not record.source_tx_hash:
            return (None, None)
        hint_tx = session.exec(
            select(Transaction).where(
                Transaction.chain_id == source_chain,
                Transaction.tx_hash == record.source_tx_hash,
            )
        ).first()
        if hint_tx is None or not getattr(hint_tx, "block_height", None):
            return (None, None)
        block = session.exec(
            select(Block).where(
                Block.chain_id == source_chain,
                Block.height == hint_tx.block_height,
            )
        ).first()
        if block is not None and tx_only_root_active(session, source_chain, int(block.height)):
            return self._strict_source_from_block(session, block, source_chain, transfer_id, authoritative=False)
        return (None, None)

    def _proof_new_era_funnel(
        self,
        session: Any,
        block: Block,
        source_chain: str,
        transfer_id: str,
        block_hash: str,
    ) -> dict[str, Any] | None:
        """#1940 F5 final funnel on the legacy path's ACTUAL resolved block.

        Returns the tx-only proof for a new-era source, None for a
        historical one (legacy CCT-derived behavior preserved)."""
        if not tx_only_root_active(session, source_chain, int(block.height)):
            return None
        if block_hash and str(block.hash) != str(block_hash):
            raise ValueError("explicit block_hash conflicts with the resolved source block")
        matches = self._canonical_lock_matches_in_block(session, block, source_chain, transfer_id)
        if not matches:
            raise ValueError(f"Lock not found for transfer_id {transfer_id} in new-era source block")
        return self._build_proof_tx_only(session, block, matches[0], source_chain)

    def _build_proof_tx_only(
        self,
        session: Any,
        block: Block,
        lock_tx: Any,
        source_chain: str,
    ) -> dict[str, Any]:
        """#1940 F5: Merkle proof from sealed tx rows — no CrossChainTransfer.

        All block leaves come from confirmed sealed row bodies via the
        shared contract and must reproduce the block's sealed
        ``bridge_state_root``; payout fields come from the selected
        ``CanonicalLock``. The requested id was already verified against
        the canonical descriptor by the resolver.
        """
        bodies: list[dict[str, Any]] = []
        for tx in session.exec(
            select(Transaction).where(
                Transaction.chain_id == source_chain,
                Transaction.block_height == block.height,
            )
        ).all():
            if getattr(tx, "status", "") != "confirmed":
                continue
            body = stored_lock_body(tx)
            try:
                canonical_lock_fields(body, str(tx.tx_hash), source_chain, int(block.height))
            except (TypeError, ValueError):
                continue
            bodies.append(body)
        trie = build_tx_bridge_trie(bodies, source_chain, int(block.height))
        computed_root = "0x" + trie.get_root().hex()
        if computed_root != (block.bridge_state_root or ""):
            raise ValueError("Computed bridge state root does not match block")

        fields = canonical_lock_fields(stored_lock_body(lock_tx), str(lock_tx.tx_hash), source_chain, int(block.height))
        proof_bytes = trie.get_proof(str(lock_tx.tx_hash).encode())
        lock_value = lock_leaf_value(
            fields.transfer_id, fields.amount, fields.target_chain, fields.target_recipient, int(block.height)
        ).encode()
        validator_signatures = self._proof_validator_signatures(block, source_chain)
        return {
            "source_chain": source_chain,
            "target_chain": fields.target_chain,
            "lock_tx_hash": str(lock_tx.tx_hash),
            "amount": fields.amount,
            "sender": fields.sender,
            "recipient": fields.target_recipient,
            "asset": fields.asset,
            "chain_id": source_chain,
            "block_height": block.height,
            "block_hash": block.hash,
            "proposer": block.proposer,
            "parent_hash": block.parent_hash,
            "state_root": block.state_root or "",
            "bridge_state_root": block.bridge_state_root or "",
            "merkle_proof": [p.hex() for p in proof_bytes],
            "lock_event": lock_value.decode(),
            "proposer_signature": block.signature,
            "validator_signatures": validator_signatures,
        }

    def _proof_validator_signatures(self, block: Block, source_chain: str) -> list[str]:
        """Sealed + threshold-top-up validator signatures for a proof."""
        validator_signatures: list[str] = []
        if block.block_metadata:
            try:
                metadata = json.loads(block.block_metadata)
                validator_signatures = [a.get("signature", "") for a in metadata.get("attestations", []) if a.get("signature")]
            except (RecursionError, TypeError, ValueError):  # malformed payload JSON decodes to the empty/default branch
                validator_signatures = []

        # Issue #670: the sealed metadata may carry fewer attestations than
        # the proof-side multisig threshold needs — the attestation gate
        # seals blocks with attestations=[] whenever the PBFT commit
        # certificate covers effective_min, and such proofs stall on
        # "Threshold not met 1/2" forever. Top the signature list up to the
        # configured threshold with fresh signatures over THIS sealed
        # block's canonical header message; verification is unchanged
        # (same message shape, same membership check).
        return self._augment_proof_validator_signatures(block, source_chain, validator_signatures)

    @staticmethod
    def _proof_header_message(block: Block) -> dict[str, Any]:
        """Canonical header message for this sealed block — verifier-identical.

        Built via ``aitbc.bridge.build_verification_message``, the same builder
        ``_verify_header_threshold_signatures`` runs on the mirrored header.
        The field set is identical to ``poa._block_header_message``
        (chain_id, height, hash, parent_hash, proposer, state_root,
        bridge_state_root), so signatures produced here recover on the verify
        side without any verifier change.
        """
        from aitbc.bridge import build_verification_message
        from aitbc.bridge.types import BridgeBlockHeader as _VerificationHeader

        return build_verification_message(
            _VerificationHeader(
                chain_id=block.chain_id,
                height=block.height,
                hash=block.hash,
                parent_hash=block.parent_hash,
                proposer=block.proposer,
                state_root=block.state_root or "",
                bridge_state_root=block.bridge_state_root or "",
            )
        )

    def _local_validator_key_map(self) -> dict[str, str]:
        """Validator address → private key held by this node (VALIDATOR_KEYS JSON)."""
        raw = getattr(settings, "validator_keys", "") or ""
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except (RecursionError, TypeError, ValueError):
            logger.warning("VALIDATOR_KEYS is not valid JSON; local proof signing unavailable")
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(a): str(k) for a, k in data.items() if a and k}

    def _proof_source_validator_set(self, source_chain: str) -> Any | None:
        """Validator set for the source chain, registered set first.

        Falls back to the VALIDATOR_SET env JSON when the bridge registry has
        no set for the node's own chain — on a producing node env is the
        membership source of truth, and without it proof augmentation has no
        membership list to top up against.
        """
        vset = None
        try:
            vset = self.get_validator_set(source_chain)
        except (SQLAlchemyError, OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.debug("Validator set lookup failed for %s: %s", source_chain, e)
        if vset is not None:
            return vset
        raw = getattr(settings, "validator_set", "") or ""
        own_chain = str(getattr(settings, "chain_id", "") or "")
        if not raw.strip() or source_chain != own_chain:
            return vset
        try:
            from aitbc.bridge.types import ValidatorInfo, ValidatorSet

            members = json.loads(raw)
            validators = [
                ValidatorInfo(
                    address=str(v["address"]),
                    public_key=str(v.get("public_key") or v.get("pubkey") or ""),
                    chain_id=source_chain,
                    epoch=0,
                    is_active=bool(v.get("is_active", True)),
                )
                for v in members
                if isinstance(v, dict) and v.get("address")
            ]
            if not validators:
                return None
            return ValidatorSet(
                chain_id=source_chain,
                epoch=0,
                validators=validators,
                threshold=int(getattr(settings, "bridge_multisig_threshold", 3)),
                total=len(validators),
            )
        except (ImportError, ArithmeticError, AttributeError, KeyError, RecursionError, TypeError, ValueError) as e:
            logger.warning("Failed to parse VALIDATOR_SET for proof augmentation: %s", e)
            return None

    def _augment_proof_validator_signatures(
        self,
        block: Block,
        source_chain: str,
        validator_signatures: list[str],
    ) -> list[str]:
        """Top up ``validator_signatures`` until the multisig threshold is met.

        Issue #670: blocks sealed on a PBFT commit certificate carry
        ``attestations=[]`` (or fewer than the threshold) in their metadata,
        and a proof copied verbatim from them fails the bc-2-side
        ``_verify_threshold_signatures`` membership/threshold check forever.

        The signatures added here are over the sealed block's canonical
        header message — the exact shape the verifier rebuilds — so this
        strengthens provability without weakening verification. Sources, in
        order: (a) validator keys held locally (``VALIDATOR_KEYS``), (b) a
        best-effort remote attestation round via ``RemoteAttestationService``
        for the still-missing count. Failures degrade to the sealed set.
        """
        try:
            return self._augment_proof_validator_signatures_impl(block, source_chain, validator_signatures)
        except _OPS_ERRORS:
            logger.exception(
                "Proof signature augmentation failed for block %s height %s — keeping sealed attestations",
                source_chain,
                block.height,
            )
            return validator_signatures

    def _augment_proof_validator_signatures_impl(
        self,
        block: Block,
        source_chain: str,
        validator_signatures: list[str],
    ) -> list[str]:
        from aitbc.bridge import check_threshold, recover_all_signers
        from aitbc_chain.config import bridge_header_signature_domains

        threshold = int(getattr(settings, "bridge_multisig_threshold", 3) or 0)
        if threshold <= 1:
            return validator_signatures

        vset = self._proof_source_validator_set(source_chain)
        if vset is None:
            return validator_signatures

        message = self._proof_header_message(block)
        proposer_sig = block.signature or ""
        # #1521: count existing signatures under the same height-gated
        # preimages the verifier uses — proposal domain for the block's own
        # signature, attestation domain (+legacy in the dual-accept window)
        # for validator signatures.
        height = getattr(block, "height", None)
        proposer_domains = bridge_header_signature_domains(height, "proposal")
        attester_domains = bridge_header_signature_domains(height, "attestation")
        signers = recover_all_signers(message, [proposer_sig] if proposer_sig else [], proposer_domains)
        signers += recover_all_signers(message, validator_signatures, attester_domains)
        meets, count, deduped = check_threshold(signers, vset, threshold)
        if meets:
            # Cheap path: sealed attestations + proposer already satisfy the
            # threshold — keep the proof byte-identical to before.
            return validator_signatures

        needed = threshold - count
        logger.info(
            "Bridge proof for %s height %s has %d/%d signers; collecting %d more",
            source_chain,
            block.height,
            count,
            threshold,
            needed,
        )
        covered = {s.lower() for s in deduped}
        member_addrs = {a.lower() for a in vset.addresses}
        collected = list(validator_signatures)

        local_keys = self._local_validator_key_map()
        needed = self._top_up_local_proof_signatures(block, message, local_keys, member_addrs, covered, collected, needed)

        # (b) remote attestation round for whatever is still missing.
        if needed > 0:
            needed = self._top_up_remote_proof_signatures(
                block, source_chain, message, local_keys, member_addrs, covered, collected, needed
            )

        if needed > 0:
            logger.warning(
                "Bridge proof for %s height %s remains below threshold after augmentation "
                "(%d signer(s) still missing); peers can only re-attest while the block "
                "is at/near their tip",
                source_chain,
                block.height,
                needed,
            )
        return collected

    def _top_up_local_proof_signatures(
        self,
        block: Block,
        message: dict[str, Any],
        local_keys: dict[str, str],
        member_addrs: set[str],
        covered: set[str],
        collected: list[str],
        needed: int,
    ) -> int:
        # (a) local validator keys — always reachable in this process.
        from aitbc.crypto.consensus_signing import sign_consensus_message, sign_consensus_message_domain
        from aitbc.crypto.signature_recovery import canonical_address
        from aitbc_chain.config import bridge_header_signing_domain

        # #1521: minted under the same height-gated attestation domain the
        # verifier expects — legacy preimage below the activation height.
        signing_domain = bridge_header_signing_domain(getattr(block, "height", None), "attestation")
        for address, private_key in local_keys.items():
            if needed <= 0:
                break
            try:
                canon = canonical_address(address).lower()
            except (TypeError, ValueError):
                canon = address.lower()
            if canon == (block.proposer or "").lower() or canon in covered or canon not in member_addrs:
                continue
            try:
                if signing_domain is None:
                    signature = sign_consensus_message(message, private_key)
                else:
                    signature = sign_consensus_message_domain(message, private_key, signing_domain)
            except (ImportError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
                logger.warning("Failed to sign proof attestation with local key %s: %s", address, e)
                continue
            collected.append(signature)
            covered.add(canon)
            needed -= 1
        return needed

    def _top_up_remote_proof_signatures(
        self,
        block: Block,
        source_chain: str,
        message: dict[str, Any],
        local_keys: dict[str, str],
        member_addrs: set[str],
        covered: set[str],
        collected: list[str],
        needed: int,
    ) -> int:
        from aitbc.bridge import recover_all_signers
        from aitbc_chain.config import bridge_header_signature_domains

        # #1521: remote attestations verify under the height-gated attestation
        # domains, same as the proof verifier.
        attester_domains = bridge_header_signature_domains(getattr(block, "height", None), "attestation")
        for att in self._collect_remote_proof_attestations(block, source_chain, needed, local_keys):
            signature = str(att.get("signature") or "")
            if not signature:
                continue
            try:
                recovered = recover_all_signers(message, [signature], attester_domains)
            except Exception as e:  # noqa: BLE001 - unrecoverable signer set just yields no signatures
                logger.debug("attestation signer recovery failed: %s", type(e).__name__)
                recovered = []
            if not recovered:
                continue
            signer = recovered[0].lower()
            if signer in covered or signer not in member_addrs:
                continue
            collected.append(signature)
            covered.add(signer)
            needed -= 1
            if needed <= 0:
                break
        return needed

    def _collect_remote_proof_attestations(
        self,
        block: Block,
        source_chain: str,
        needed: int,
        local_keys: dict[str, str],
    ) -> list[dict[str, str]]:
        """Best-effort remote attestations over the sealed block's header.

        Reuses ``RemoteAttestationService.collect_attestations`` — the same
        gossip request the proposer publishes at seal time — so peers re-sign
        the identical canonical header message. Two inherent limits:

        - ``collect_attestations`` returns immediately when the node holds no
          validator keys, so this path is only live on nodes that produce.
        - v9 attesters re-verify the request's transaction set against their
          own parent state; a sealed block is attestable only while it is
          still the peer's tip (the "late request" branch), so this helps the
          prompt relayer pass right after sealing, not historical rebuilds.

        ``build_proof`` is synchronous and may run while the app event loop is
        blocked by its own caller, so the collection always runs on a
        dedicated loop in a worker thread. Backends whose publish path is
        bound to the main loop simply fail and degrade to zero answers.
        """
        if needed <= 0 or not local_keys:
            return []
        try:
            from ..consensus.remote_attestation import RemoteAttestationService
        except Exception as e:  # noqa: BLE001 - optional consensus helper import; module-level side effects are unbounded
            logger.debug("Remote attestation service unavailable for proof build: %s", e)
            return []

        envelopes: list[dict[str, Any]] = [tx.envelope for tx in (block.transactions or []) if isinstance(tx.envelope, dict)]
        service = RemoteAttestationService(
            source_chain,
            local_keys,
            session_factory=lambda: self._session_for(source_chain),
        )
        timeout = float(getattr(settings, "bridge_proof_attestation_timeout_seconds", 2.0) or 0.0)
        if timeout <= 0:
            return []

        result: dict[str, Any] = {}

        def _run() -> None:
            try:
                result["atts"] = asyncio.run(
                    service.collect_attestations(block, needed, timeout=timeout, transactions=envelopes)
                )
            except Exception as e:  # noqa: BLE001 - best-effort path, any failure degrades to sealed set
                result["err"] = e

        worker = threading.Thread(target=_run, name="bridge-proof-attestations", daemon=True)
        worker.start()
        worker.join(timeout + 5.0)
        if worker.is_alive():
            logger.warning("Remote proof attestation collection timed out for %s height %s", source_chain, block.height)
            return []
        if "err" in result:
            logger.debug("Remote proof attestation collection failed: %s", result["err"])
            return []
        return list(result.get("atts") or [])

    def _build_lock_event_value(self, record: CrossChainTransfer, height: int | None) -> str:
        """Canonical lock event string the source block at ``height`` committed to."""
        return lock_leaf_value(record.transfer_id, record.amount, record.target_chain, record.recipient, height)

    def _generate_transfer_id(
        self, source_chain: str, target_chain: str, sender: str, recipient: str, amount: int, timestamp: int
    ) -> str:
        """Generate unique transfer ID."""
        data = f"{source_chain}:{target_chain}:{sender}:{recipient}:{amount}:{timestamp}"
        return "0x" + hashlib.sha256(data.encode()).hexdigest()

    def _proof_binds_payout_fields(self, proof: dict[str, Any], record: CrossChainTransfer) -> bool:
        """True when the proof's Merkle leaf commits to every field the release pays on.

        Only the recipient-bound leaf (``bridge_lock_leaf_v2_height``) covers
        the recipient, so a proof from an older source block cannot stand on
        its own and is refused.
        """
        amount = proof.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            logger.warning("Proof amount must be a positive integer")
            return False
        if not proof.get("merkle_proof"):
            logger.warning("Proof-built transfer record needs a Merkle inclusion proof; rejecting")
            return False
        if not lock_leaf_v2_active(proof.get("block_height")):
            logger.warning(
                "Lock for %s is not on this node and its source block (height=%s) predates the "
                "recipient-bound leaf; rejecting",
                record.transfer_id[:16],
                proof.get("block_height"),
            )
            return False
        return True

    def _proof_required_fields_present(self, proof: dict[str, Any]) -> bool:
        """True when the proof carries every field ``_validate_proof`` requires."""
        required_fields = [
            "source_chain",
            "lock_tx_hash",
            "amount",
            "sender",
            "recipient",
            "chain_id",
            "block_height",
            "block_hash",
        ]
        for field in required_fields:
            if field not in proof:
                logger.warning("Proof missing field: %s", field)
                return False
        return True

    def _proof_fields_match_record(self, proof: dict[str, Any], record: CrossChainTransfer, record_chain_id: str) -> bool:
        """Step 1: verify the proof's claimed fields equal the transfer record's."""
        if proof.get("source_chain") != record.source_chain:
            logger.warning("Proof source_chain mismatch")
            return False
        if proof.get("amount") != record.amount:
            logger.warning("Proof amount mismatch")
            return False
        if proof.get("recipient") != record.recipient:
            logger.warning("Proof recipient mismatch")
            return False
        if proof.get("sender") != record.sender:
            logger.warning("Proof sender mismatch")
            return False

        # Bug 12: Verify chain_id matches
        if proof.get("chain_id") != record_chain_id:
            logger.warning("Proof chain_id mismatch: %s != %s", proof.get("chain_id"), record_chain_id)
            return False
        if proof.get("target_chain") is not None and proof.get("target_chain") != record.target_chain:
            logger.warning("Proof target_chain mismatch")
            return False

        # F1: the proven key and leaf must be the ones this transfer's fields
        # produce. Without this the Merkle check below only proves that *some*
        # lock exists — not that it carries this amount, recipient or target.
        if proof.get("lock_tx_hash") != (getattr(record, "source_tx_hash", None) or record.transfer_id):
            logger.warning("Proof lock_tx_hash does not match the transfer record")
            return False
        return True

    def _proof_lock_event_matches(self, proof: dict[str, Any], record: CrossChainTransfer) -> bool:
        """F1 leaf binding: a proof-built record must commit to the payout fields."""
        if proof.get("merkle_proof"):
            expected_event = self._build_lock_event_value(record, proof.get("block_height"))
            if proof.get("lock_event") != expected_event:
                logger.warning("Proof lock_event does not match the transfer fields")
                return False
        return True

    def _proof_block_anchor(self, proof: dict[str, Any]) -> tuple[int, str] | None:
        """Step 2: block anchor (height + hash must be present and consistent).

        Returns ``(block_height, block_hash)`` or None when either is invalid.
        """
        block_height = proof.get("block_height")
        block_hash = proof.get("block_hash")
        if not isinstance(block_height, int) or block_height < 0:
            logger.warning("Proof has invalid block_height")
            return None
        if not isinstance(block_hash, str) or not block_hash.strip():
            logger.warning("Proof has invalid block_hash")
            return None
        return block_height, block_hash

    def _verify_in_process_proof(
        self,
        proof: dict[str, Any],
        record: CrossChainTransfer,
        record_chain_id: str,
        block_height: int,
        block_hash: str,
    ) -> BridgeBlockHeader | None:
        """Step 5: in-process block header lookup and verification (v0.7.2).

        Returns the verified stored header, or None when any check fails
        (each failure is logged at the point it is detected).
        """
        # F2: only a header this node stored can anchor a proof. A header
        # built from the proof would let the proof choose its own roots,
        # proposer and confirmation_count.
        header = self._get_block_header(record_chain_id, block_height)
        if header is None:
            logger.warning("No stored block header for chain=%s height=%s; rejecting proof", record_chain_id, block_height)
            return None

        # Verify block hash matches
        if header.hash != block_hash:
            logger.warning(
                "Block hash mismatch: proof=%s vs header=%s (height=%s)",
                block_hash[:16],
                header.hash[:16],
                block_height,
            )
            return None

        # Step 5a: Bridge state root verification
        proof_bridge_root = proof.get("bridge_state_root") or proof.get("state_root", "")
        expected_bridge_root = header.bridge_state_root or header.state_root
        if proof_bridge_root and proof_bridge_root != expected_bridge_root:
            logger.warning(
                "Bridge state root mismatch: proof=%s vs header=%s",
                proof_bridge_root[:16],
                expected_bridge_root[:16],
            )
            return None

        # Step 5b: Block header signature verification (B4)
        if not self._verify_block_header_signature(header):
            logger.warning("Block header signature verification failed for height=%s", block_height)
            return None

        # Step 5c: Merkle proof verification (B3)
        merkle_proof = proof.get("merkle_proof", [])
        if merkle_proof:
            merkle_state_root = header.bridge_state_root or header.state_root
            if not self._verify_merkle_proof(merkle_state_root, proof):
                logger.warning("Merkle proof verification failed for height=%s", block_height)
                return None
        else:
            # v0.10.16: Merkle inclusion proof is required for production
            # release paths. When bridge_release_enabled is True, a missing
            # merkle_proof is a hard failure; the standalone
            # bridge_require_merkle_proof flag still allows explicit enforcement.
            release_enabled = getattr(settings, "bridge_release_enabled", False)
            require_merkle = release_enabled or getattr(settings, "bridge_require_merkle_proof", False)
            if require_merkle:
                logger.warning(
                    "Proof has no merkle_proof and release/production enforcement enabled — rejecting (height=%s)",
                    block_height,
                )
                return None
            logger.warning(
                "Proof has no merkle_proof — skipping trie verification (field+sig only, height=%s)",
                block_height,
            )

        # Step 5d: Finality check (B5)
        if not self._check_finality_for_transfer(header, record.amount):
            logger.warning(
                "Finality check failed for height=%s (confirmations=%s, amount=%s)",
                block_height,
                header.confirmation_count,
                record.amount,
            )
            return None
        return header

    def _proof_signature_present(self, proof: dict[str, Any]) -> bool:
        """Step 3: a proof must carry proposer_signature or validator_signatures."""
        proposer_signature = proof.get("proposer_signature")
        validator_signatures = proof.get("validator_signatures", [])
        if not proposer_signature and not validator_signatures:
            logger.warning("Proof has no signatures (proposer_signature or validator_signatures required)")
            return False
        return True

    def _verify_proof_threshold_and_freshness(
        self, proof: dict[str, Any], header: BridgeBlockHeader | None, record: CrossChainTransfer, record_chain_id: str
    ) -> bool:
        """Steps 4+6: multi-sig threshold verification, then validator-set freshness."""
        # Step 4: Multi-sig threshold verification (v0.7.1, kept)
        # Moved to occur after the BridgeBlockHeader is available.
        if not self._verify_threshold_signatures(proof, header=header):
            logger.warning("Proof signature verification failed (threshold or single-sig)")
            return False

        # Step 6: Validator set epoch grace period check (B6) — epoch-aware:
        # the current epoch is authoritative; superseded epochs get the grace
        # window. A proof's validator_epoch of 0/absent resolves to latest.
        if not self._check_validator_set_freshness(record_chain_id, proof.get("validator_epoch") or None):
            logger.warning("Validator set for chain=%s is stale (grace period expired)", record_chain_id)
            return False
        return True

    def _validate_proof(self, proof: dict[str, Any], record: CrossChainTransfer, require_leaf_binding: bool = False) -> bool:
        """Validate cross-chain transfer proof with cryptographic verification (v0.7.3).

        ``require_leaf_binding`` is set when ``record`` was built from the
        proof itself: the field checks below then compare the proof with
        itself, so the proof must carry a recipient-bound leaf and a Merkle
        inclusion proof against a stored header, or it is refused.
        """
        if not self._proof_required_fields_present(proof):
            return False

        # Bug 12: Verify chain_id matches
        record_chain_id = getattr(record, "chain_id", None) or record.source_chain

        # Step 1: Verify field equality with record
        if not self._proof_fields_match_record(proof, record, record_chain_id):
            return False

        # F1: the proven key and leaf must be the ones this transfer's fields
        # produce. Without this the Merkle check below only proves that *some*
        # lock exists — not that it carries this amount, recipient or target.
        if require_leaf_binding and not self._proof_binds_payout_fields(proof, record):
            return False
        if not self._proof_lock_event_matches(proof, record):
            return False

        # Step 2: Verify block anchor (height + hash must be present and consistent)
        anchor = self._proof_block_anchor(proof)
        if anchor is None:
            return False
        block_height, block_hash = anchor

        # Step 3: Signature requirement check (proposer_signature or validator_signatures)
        if not self._proof_signature_present(proof):
            return False

        # Step 5: Block header lookup + verification (v0.7.2)
        header: BridgeBlockHeader | None = None
        verification_mode = getattr(settings, "bridge_verification_mode", "in_process")
        if verification_mode == "in_process":
            header = self._verify_in_process_proof(proof, record, record_chain_id, block_height, block_hash)
            if header is None:
                return False
        elif require_leaf_binding:
            logger.warning("Proof-built transfer record needs in-process Merkle verification; rejecting")
            return False

        return self._verify_proof_threshold_and_freshness(proof, header, record, record_chain_id)
