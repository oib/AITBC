"""Proposal execution/timelock methods for ``GovernanceService`` (#1860 Phase 6 split).

Pure-move split of the execution-side methods of
``governance_service.governance_service``: ``execute_proposal``,
``_submit_service_signed_execute``, ``_enforce_execution_timelock`` and
``_apply_parameter_change`` now live on the ``_ExecutionMixin`` base class.
``governance_service.py`` composes ``GovernanceService`` from this mixin
and the votes mixin, so the method surface — including
``GovernanceService.<method>`` attribute access used by tests — is
unchanged. Moved code is byte-identical; ``_OPS_ERRORS`` comes from
``governance_service_common``.

Import ``governance_service.governance_service`` (or
``governance_service.services``); this module is not meant to be imported
directly.
"""

import logging
from typing import TYPE_CHECKING, Any

from ..config import settings
from ..domain.governance import Proposal, ProposalExecutionLog
from .governance_service_common import _OPS_ERRORS

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..clients.blockchain import BlockchainClient

logger = logging.getLogger(__name__)


class _ExecutionMixin:
    if TYPE_CHECKING:
        # Attributes and sibling methods supplied by ``GovernanceService``
        # (and the votes mixin) once the bases are composed — declared here
        # so mypy can check the moved bodies.
        session: AsyncSession
        _blockchain: BlockchainClient

        @staticmethod
        def _verify_client_signed_tx(
            signed_tx: dict[str, Any],
            tx_type: str,
            expected_signer: str,
            expected_payload_fields: dict[str, Any],
        ) -> None: ...

        async def get_proposal(self, proposal_id: str) -> Proposal | None: ...

        async def _stamp_executed_after_execute(
            self,
            proposal_id: str,
            proposal: Proposal,
            execution_log: ProposalExecutionLog,
            *,
            tx_hash: str | None,
            block_height: int | None,
            automation_result: dict[str, Any] | None,
        ) -> Proposal: ...

    # Proposal Execution Methods
    async def execute_proposal(
        self,
        proposal_id: str,
        executor_address: str = "",
        signed_tx: dict[str, Any] | None = None,
    ) -> Proposal | None:
        """Execute a passed proposal and log the steps.

        The execution timelock is always enforced first — see
        :meth:`_enforce_execution_timelock`. It is checked whether or not this
        deployment submits transactions on-chain, and a proposal whose timelock
        cannot be verified is refused rather than exempted.

        When on-chain submission is enabled, a GOVERNANCE_EXECUTE transaction is
        then submitted and its tx_hash stored on the proposal.

        Raises:
            ValueError: If the proposal has not succeeded, or its timelock cannot
                be verified or has not expired. The refusal is recorded in the
                proposal's execution log.
        """
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            return None

        if proposal.status != "succeeded":
            raise ValueError(f"Proposal not in succeeded state: {proposal.status}")

        # Log execution start
        execution_log = ProposalExecutionLog(proposal_id=proposal_id, execution_step="start", status="pending", result={})
        self.session.add(execution_log)

        try:
            tx_hash = None
            block_height = None

            # V23-18: enforce the timelock before anything is written, and independently of
            # whether this deployment submits transactions on-chain. This check used to live
            # inside the on-chain branch below, which meant the default configuration
            # (enable_onchain_submission=False) executed proposals with no timelock at all.
            await self._enforce_execution_timelock(proposal)

            if settings.enable_onchain_submission and signed_tx is not None:
                self._verify_client_signed_tx(
                    signed_tx,
                    "GOVERNANCE_EXECUTE",
                    executor_address,
                    {"proposal_id": proposal_id, "executor": executor_address, "chain_id": proposal.chain_id},
                )
                result = await self._blockchain.submit_signed_governance_tx(signed_tx)
                tx_hash = result.get("tx_hash") or result.get("transaction_hash")
                block_height = result.get("block_height")
            elif settings.enable_onchain_submission and settings.proposer_private_key:
                tx_hash, block_height = await self._submit_service_signed_execute(proposal, proposal_id, executor_address)

            # v0.10.1: Parameter automation must apply BEFORE the proposal is marked
            # executed — a failed apply used to leave an "executed" proposal whose
            # change never landed.
            automation_result = None
            if proposal.proposal_type == "parameter_change" and proposal.proposal_value:
                automation_result = await self._apply_parameter_change(proposal)
                if not automation_result.get("applied"):
                    raise ValueError(f"parameter apply failed: {automation_result}")

            return await self._stamp_executed_after_execute(
                proposal_id,
                proposal,
                execution_log,
                tx_hash=tx_hash,
                block_height=block_height,
                automation_result=automation_result,
            )
        except Exception as e:
            # Log execution failure
            execution_log.status = "failed"
            execution_log.error_message = str(e)
            await self.session.commit()
            raise

    async def _submit_service_signed_execute(
        self, proposal: Proposal, proposal_id: str, executor_address: str
    ) -> tuple[str | None, int | None]:
        """Submit a service-signed GOVERNANCE_EXECUTE for ``proposal_id``.

        v13: the tx payload must carry the ``execution_payload`` sealed at
        PROPOSE — without it the node rejects the tx (#1214). Refuses locally
        when the sealed payload cannot be verified rather than relaying a tx
        the chain is guaranteed to reject.
        """
        from aitbc.governance.onchain import build_execute_tx

        payload = build_execute_tx(proposal_id, executor_address, proposal.chain_id)
        sealed = await self._blockchain.get_sealed_governance_proposal(proposal_id, proposal.chain_id)
        sealed_payload = (sealed or {}).get("execution_payload")
        if not isinstance(sealed_payload, dict):
            raise ValueError(
                f"Cannot verify sealed execution_payload for proposal {proposal_id} on "
                f"{proposal.chain_id} — refusing to submit an EXECUTE the v13 binding rejects"
            )
        payload["execution_payload"] = sealed_payload
        result = await self._blockchain.submit_governance_tx(
            tx_type="GOVERNANCE_EXECUTE",
            sender=executor_address,
            private_key=settings.proposer_private_key,
            payload=payload,
            chain_id=proposal.chain_id,
        )
        return result.get("tx_hash") or result.get("transaction_hash"), result.get("block_height")

    async def _enforce_execution_timelock(self, proposal: Proposal) -> None:
        """Refuse execution unless the timelock is provably expired (V23-18).

        A timelock is a safety control, so every path that cannot *prove* the delay
        elapsed refuses rather than proceeds. Three things can go missing, and each is
        a refusal:

        - the proposal has no recorded on-chain block height (its GOVERNANCE_PROPOSE
          submission failed, or it predates on-chain governance);
        - it has no recorded ``voting_ends_block``;
        - the chain is unreachable, so there is no current height to compare against.

        The previous implementation treated the first of these as "no timelock applies"
        and executed, which turned a best-effort on-chain submission into a silent
        load-bearing part of a safety control: one RPC hiccup at creation time produced a
        proposal that later executed instantly.

        Raises:
            ValueError: If the timelock cannot be verified, or has not expired.
        """
        import logging

        logger = logging.getLogger(__name__)

        if not settings.require_execution_timelock:
            logger.warning(
                "Execution timelock BYPASSED for proposal %s: require_execution_timelock is False. "
                "This is a development-only setting.",
                proposal.proposal_id,
            )
            return

        if proposal.block_height is None:
            raise ValueError(
                f"Cannot verify timelock for proposal {proposal.proposal_id}: no on-chain block "
                "height was recorded at creation, so there is no point to measure the delay from. "
                "The GOVERNANCE_PROPOSE submission likely failed; re-submit the proposal."
            )

        is_emergency = proposal.proposal_type == "emergency"

        # Proposals created before V23-18 have no voting_ends_block. Refuse rather than
        # reconstruct one: deriving it from current settings would produce whatever answer
        # the current configuration implies, which is not evidence of anything.
        if proposal.voting_ends_block is None:
            raise ValueError(
                f"Cannot verify timelock for proposal {proposal.proposal_id}: no voting_ends_block "
                "was recorded at creation. Proposals created before this field existed must be "
                "re-submitted to be executed on-chain."
            )

        try:
            current_height = await self._blockchain.get_block_height(proposal.chain_id)
        except Exception as e:
            # Unreachable chain means unknown height. Unknown height means the delay is
            # unproven, and unproven means refused — an unreachable chain must not become
            # a way to execute a proposal early.
            raise ValueError(
                f"Cannot verify timelock for proposal {proposal.proposal_id}: chain {proposal.chain_id} is unreachable ({e})"
            ) from e

        effective_timelock = settings.emergency_timelock_blocks if is_emergency else settings.timelock_blocks
        blocks_since_voting_ended = current_height - proposal.voting_ends_block

        if blocks_since_voting_ended < effective_timelock:
            raise ValueError(
                f"Timelock not expired: {blocks_since_voting_ended} blocks since voting ended, "
                f"need {effective_timelock}"
                f"{' (emergency fast-track)' if is_emergency else ''}"
            )

    async def _apply_parameter_change(self, proposal: Proposal) -> dict[str, Any]:
        """Apply a governance-approved parameter change to the target service (v0.10.1).

        Calls the target service's parameter API (POST /v1/{service}/parameters/apply)
        with the parameter change details from the proposal's ``proposal_value``.
        """
        import httpx

        params = proposal.proposal_value
        target_service = params.get("target_service", "")
        parameter_name = params.get("parameter_name", "")
        new_value = params.get("new_value")

        if not target_service or not parameter_name:
            return {"applied": False, "reason": "missing target_service or parameter_name"}

        # Map target_service to its parameter-apply endpoint. The routes are not
        # uniform: pool-hub mounts its router at /v1/parameters while market
        # serves /v1/market/parameters/apply directly on the app.
        service_endpoints = {
            "poolhub": f"{settings.poolhub_url}/v1/parameters/apply",
            "market": f"{settings.market_url}/v1/market/parameters/apply",
        }

        if target_service == "blockchain":
            # Direct config change not supported via API — log warning
            return {"applied": False, "reason": "blockchain parameter changes require manual config update"}

        endpoint = service_endpoints.get(target_service)
        if not endpoint:
            return {"applied": False, "reason": f"unknown target_service: {target_service}"}
        payload = {
            "proposal_id": proposal.proposal_id,
            "target_service": target_service,
            "parameter_name": parameter_name,
            "old_value": params.get("old_value"),
            "new_value": new_value,
            "description": params.get("description", ""),
        }

        headers = {}
        if target_service == "market" and settings.market_api_key:
            headers["X-Api-Key"] = settings.market_api_key
        if target_service == "poolhub" and settings.poolhub_api_key:
            # pool-hub authenticates this call on X-PoolHub-Key
            # (apps/pool-hub .../routers/parameters.py), not X-Api-Key.
            headers["X-PoolHub-Key"] = settings.poolhub_api_key

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 200:
                    result = resp.json()
                    return {"applied": True, "target_service": target_service, "result": result}
                else:
                    return {
                        "applied": False,
                        "target_service": target_service,
                        "status_code": resp.status_code,
                        "error": resp.text,
                    }
        except _OPS_ERRORS as e:
            return {"applied": False, "target_service": target_service, "error": str(e)}
