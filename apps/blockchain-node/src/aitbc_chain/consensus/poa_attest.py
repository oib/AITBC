"""Attestation collection and validator-set scoping for ``PoAProposer`` (poa split).

Import ``aitbc_chain.consensus.poa`` first (it wires these
mixins into ``PoAProposer``); this module is not meant to be imported
directly."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError

from .poa import _PoaBaseMixin, _active_consensus_domain, _sign_consensus

from ..config import settings
from ..models import Block
from aitbc.crypto.signature_recovery import canonical_address


class _AttestMixin(_PoaBaseMixin):
    if TYPE_CHECKING:

        def _block_header_message(self, *args: Any, **kwargs: Any) -> Any: ...

    def _consensus_participants_anomaly_checked(self) -> list[str]:
        """Consensus participants after the #693 anomaly re-read.

        Never sizes an attestation round off a poisoned empty view.
        """
        if self._multi_validator is None:
            return list(self._validator_keys.keys())
        self._multi_validator.reload_state_if_anomalous()
        return self._multi_validator.get_consensus_participants()

    def _remote_validators_configured(self, proposer_c: str) -> bool:
        """True when consensus members other than ``proposer_c`` are configured.

        ``proposer_c`` must already be canonicalised. ``VALIDATOR_SET`` is the
        membership source of truth, so it is consulted first; the registered
        (persisted) validator set is the fallback when env is unset or
        unparseable. Distinguishes "single-validator island" from "remotes
        configured but missing from the active view" for the #693 floor guard.
        """
        raw = getattr(settings, "validator_set", "") or ""
        if raw.strip():
            try:
                env = json.loads(raw)
            except (RecursionError, TypeError, ValueError):  # malformed payload JSON decodes to the empty/default branch
                env = None
            if isinstance(env, list):
                return any(
                    isinstance(v, dict) and bool(v.get("address")) and canonical_address(v["address"]) != proposer_c
                    for v in env
                )
        if self._multi_validator is not None:
            return any(canonical_address(addr) != proposer_c for addr in self._multi_validator.validators)
        return False

    async def _collect_attestations(
        self,
        block: Block,
        transactions: list[dict[str, Any]] | None = None,
        round_number: int | None = None,
    ) -> list[dict[str, str]]:
        """Collect canonical header signatures from local and remote validators.

        Local attestations are produced immediately. Remote attestations are
        requested over the gossip broker and collected up to the configured
        timeout. Duplicates are de-duplicated by validator address.

        ``round_number`` is the proposer round this node selected for the
        block — the same deterministic derivation attesters apply to the
        attest_request header. #1298 T7a: at/above the armed
        domain-separation height the round is inside the signed attestation
        payload unconditionally (round_lock does not gate it), so local
        attestations must bind it exactly like remote ones or every importer
        rejects them.
        """
        attestations: list[dict[str, str]] = []
        seen: set[str] = set()

        active_validators = self._consensus_participants_anomaly_checked()
        configured_min = getattr(settings, "multi_validator_min_attestations", 0)
        # The configured minimum cannot exceed the number of validators that are
        # allowed to attest (everyone except the proposer).  This prevents an
        # impossible quorum from stalling block production when the validator
        # set is small or a member is offline.
        effective_min = max(0, min(configured_min, max(0, len(active_validators) - 1)))

        attestations = self._local_attestations(block, round_number)
        seen.update(canonical_address(att["validator"]) for att in attestations)

        if self._remote_attestation is not None:
            min_remote = max(0, effective_min - len(attestations))
            if min_remote > 0 or effective_min > 0:
                # Give slow validators more time when more responses are needed.
                base_timeout = getattr(settings, "multi_validator_attestation_timeout_seconds", 1.0)
                timeout = max(float(base_timeout), 0.5 * min_remote + float(base_timeout))
                try:
                    remote = await self._remote_attestation.collect_attestations(
                        block,
                        min_remote,
                        timeout=timeout,
                        transactions=transactions,
                        unlock_justification=self._unlock_justifications.get(block.height),
                    )
                    for att in remote:
                        addr = canonical_address(att["validator"])
                        if addr not in seen:
                            attestations.append(att)
                            seen.add(addr)
                        else:
                            self._logger.debug("Dropping duplicate remote attestation from %s", att["validator"])
                except (
                    ImportError,
                    SQLAlchemyError,
                    ArithmeticError,
                    OSError,
                    RuntimeError,
                    ValueError,
                    TypeError,
                    AttributeError,
                    KeyError,
                ) as e:
                    self._logger.warning("Failed to collect remote attestations: %s", e)

        return attestations

    def _attestation_signers(self) -> dict[str, str]:
        """``_validator_keys`` filtered to validator-set members (#1940 F6).

        Filtering lives here (not in ``_local_attestations``) to keep that
        function under the C901 threshold; ``None`` allowed-set means no
        validator set is configured → every key signs, legacy behavior.
        """
        allowed = self._attestable_addresses()
        if allowed is None:
            return self._validator_keys
        return {a: k for a, k in self._validator_keys.items() if canonical_address(a) in allowed}

    def _local_attestations(self, block: Block, round_number: int | None) -> list[dict[str, str]]:
        """Sign this node's validator keys over the block header.

        #1298 T7a: at/above the armed domain-separation height the round is
        inside the signed attestation payload unconditionally (round_lock
        does not gate it), so local attestations must bind it exactly like
        remote ones or every importer rejects them.
        """
        attestations: list[dict[str, str]] = []
        if not self._validator_keys:
            return attestations
        from aitbc.crypto.consensus_signing import DOMAIN_BLOCK_ATTESTATION

        domain = _active_consensus_domain(block.height, DOMAIN_BLOCK_ATTESTATION)
        att_round: int | None = None
        if domain is not None:
            att_round = round_number
            if att_round is None and self._remote_attestation is not None:
                # No round threaded through (direct/test callers): derive
                # it exactly the way remote attesters will.
                att_round = self._remote_attestation._collect_round_for_block(block)
            if att_round is None:
                # Underivable round: sign the unbound domain preimage —
                # verifiers still accept it (mixed round-bound/unbound
                # handling) — rather than dropping the attestation.
                self._logger.warning(
                    "Attestation round underivable for block %s at height %s — signing unbound",
                    getattr(block, "hash", "")[:18],
                    block.height,
                )
        message = self._block_header_message(block)
        if att_round is not None:
            message["round"] = att_round
        # #1940 F6: _attestation_signers scopes keys to the validator set —
        # the remote listener filters the same way; a non-member key on a
        # config error would produce attestations every importer rejects.
        for address, private_key in self._attestation_signers().items():
            if canonical_address(address) == canonical_address(block.proposer):
                continue
            try:
                signature = _sign_consensus(message, private_key, domain)
                attestation: dict[str, str] = {"validator": address, "signature": signature}
                if att_round is not None:
                    # Import-side verification rebuilds the same
                    # round-bound preimage from this hint (or derives it).
                    attestation["round"] = str(att_round)
                attestations.append(attestation)
            except (ImportError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
                self._logger.warning("Failed to collect attestation from %s: %s", address, e)
        return attestations
