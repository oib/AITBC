"""Remote block-header attestation over the gossip broker.

v0.7.6: minimal second-node validator PoC. Proposers publish a block header
over the ``consensus.attest_request.<chain_id>`` gossip topic. Other validators
sign the canonical header and publish responses on
``consensus.attest_response.<chain_id>``. The proposer collects responses and
includes them in ``block_metadata``.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from aitbc.aitbc_logging import get_logger
from aitbc.async_tasks import create_task_with_logging
from aitbc.crypto.consensus_signing import sign_consensus_message, verify_block_signature
from aitbc.crypto.signature_recovery import canonical_address

from ..config import settings
from ..gossip import gossip_broker
from ..models import Block

logger = get_logger(__name__)


def _same_address(a: str, b: str) -> bool:
    """Compare two addresses in either ait1/0x spelling."""
    return canonical_address(a) == canonical_address(b)


class RemoteAttestationService:
    """Collect and serve remote block-header attestations over gossip."""

    def __init__(self, chain_id: str, validator_keys: dict[str, str]) -> None:
        self._chain_id = chain_id
        self._validator_keys = validator_keys
        self._request_topic = f"consensus.attest_request.{chain_id}"
        self._response_topic = f"consensus.attest_response.{chain_id}"
        self._listener_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._listener_task is not None:
            return
        self._stop_event.clear()
        self._listener_task = create_task_with_logging(
            self._listen(),
            name=f"remote_attestation_listener_{self._chain_id}",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

    async def _listen(self) -> None:
        try:
            sub = await gossip_broker.subscribe(self._request_topic, max_queue_size=1000)
        except Exception as e:
            logger.warning("Failed to subscribe to attestation requests: %s", e)
            return

        logger.info("Subscribed to remote attestation requests on %s", self._request_topic)
        try:
            async for request in sub:
                if self._stop_event.is_set():
                    break
                try:
                    await self._handle_request(request)
                except Exception as e:
                    logger.warning("Error handling attestation request: %s", e)
        finally:
            sub.close()

    async def _handle_request(self, request: Any) -> None:
        if not isinstance(request, dict):
            return
        header = request.get("header")
        if not isinstance(header, dict):
            return

        proposer = header.get("proposer", "")
        if not proposer:
            return

        # Only sign for blocks produced by a known validator in our set.
        validator_set = self._load_validator_set()
        if validator_set and canonical_address(proposer) not in {canonical_address(v) for v in validator_set}:
            return

        for address, private_key in self._validator_keys.items():
            # Do not sign our own block.
            if _same_address(address, proposer):
                continue
            # Only sign with keys that are part of the configured validator set.
            if validator_set and canonical_address(address) not in {canonical_address(v) for v in validator_set}:
                continue

            message = {
                "chain_id": header.get("chain_id", self._chain_id),
                "height": header.get("height", 0),
                "hash": header.get("hash", ""),
                "parent_hash": header.get("parent_hash", ""),
                "proposer": proposer,
                "state_root": header.get("state_root", ""),
                "bridge_state_root": header.get("bridge_state_root", ""),
            }
            try:
                signature = sign_consensus_message(message, private_key)
            except Exception as e:
                logger.warning("Failed to sign attestation: %s", e)
                continue

            response = {
                "chain_id": self._chain_id,
                "height": message["height"],
                "hash": message["hash"],
                "validator": address,
                "signature": signature,
            }
            try:
                await gossip_broker.publish(self._response_topic, response)
            except Exception as e:
                logger.warning("Failed to publish attestation response: %s", e)
                continue
            logger.debug("Published attestation response for height %s from %s", message["height"], address)
            return

    def _load_validator_set(self) -> set[str]:
        validator_set_str = getattr(settings, "validator_set", "")
        if not validator_set_str:
            return set()
        try:
            data = json.loads(validator_set_str)
            return {v.get("address", "") for v in data if v.get("address")}
        except Exception:
            return set()

    async def collect_attestations(
        self,
        block: Block,
        min_count: int,
        timeout: float | None = None,
    ) -> list[dict[str, str]]:
        """Publish a header and collect at least min_count remote attestations."""
        if not self._validator_keys:
            return []

        effective_timeout = float(
            timeout if timeout is not None else getattr(settings, "multi_validator_attestation_timeout_seconds", 1.0)
        )

        header = {
            "chain_id": self._chain_id,
            "height": block.height,
            "hash": block.hash,
            "parent_hash": block.parent_hash or "",
            "proposer": block.proposer,
            "state_root": block.state_root or "",
            "bridge_state_root": block.bridge_state_root or "",
        }
        request = {"header": header, "timestamp": time.time()}

        # Subscribe first to avoid missing a fast response.
        try:
            sub = await gossip_broker.subscribe(self._response_topic, max_queue_size=1000)
        except Exception as e:
            logger.warning("Failed to subscribe to attestation responses: %s", e)
            return []

        try:
            await gossip_broker.publish(self._request_topic, request)
        except Exception as e:
            logger.warning("Failed to publish attestation request: %s", e)
            sub.close()
            return []

        attestations: list[dict[str, str]] = []
        start = time.monotonic()
        try:
            while time.monotonic() - start < effective_timeout:
                remaining = effective_timeout - (time.monotonic() - start)
                if remaining <= 0:
                    break
                try:
                    response = await asyncio.wait_for(sub.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                if not isinstance(response, dict):
                    continue
                if response.get("chain_id") != self._chain_id or response.get("hash") != block.hash:
                    continue
                validator = response.get("validator", "")
                signature = response.get("signature", "")
                if not validator or not signature:
                    continue
                try:
                    if verify_block_signature(header, signature, validator):
                        attestations.append({"validator": validator, "signature": signature})
                        logger.debug(
                            "Collected valid attestation from %s for height %s",
                            validator,
                            block.height,
                        )
                except Exception as e:
                    logger.warning("Failed to verify attestation from %s: %s", validator, e)
                if len(attestations) >= min_count:
                    break
        finally:
            sub.close()

        return attestations
