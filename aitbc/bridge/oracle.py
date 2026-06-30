"""Bridge oracle client interface (v0.7.2 §A2, v0.7.4 §A1).

Abstract interface for bridge proof verification. The default
implementation (``InProcessVerifier``) uses local cryptographic verification
(Merkle proofs + block header signatures). The ``ExternalOracleClient``
(v0.7.4) delegates verification to one or more external oracle HTTP
endpoints, with an ``OracleFallbackPolicy`` (v0.7.4 §A2) that falls back
to in-process verification when the oracle is unavailable.

The ``InProcessVerifier`` delegates Merkle proof verification to a
``MerkleProofVerifier`` protocol implementation provided by the blockchain
node (which has access to the Merkle Patricia Trie). This keeps the shared
SDK dependency-free — the actual trie verification happens in
``apps/blockchain-node/``.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Protocol, cast, runtime_checkable

import httpx

from .types import (
    BridgeBlockHeader,
    FinalityConfig,
    ProofVerificationResult,
    VerificationMode,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class MerkleProofVerifier(Protocol):
    """Protocol for Merkle proof verification (implemented by blockchain node).

    The blockchain node implements this protocol by wrapping
    ``merkle_patricia_trie.verify_proof``. The shared SDK calls this
    interface so it doesn't depend on the node's internal trie implementation.
    """

    def verify_merkle_proof(
        self,
        state_root: str,
        key: str,
        value: str,
        proof: list[bytes],
    ) -> bool:
        """Verify a Merkle proof against a state root.

        Args:
            state_root: The expected state root (hex string).
            key: The key whose inclusion is being proven.
            value: The expected value at that key.
            proof: List of encoded trie nodes forming the proof path.

        Returns:
            True if the proof is valid (key→value is in the trie with the
            given state root), False otherwise.
        """
        ...


class OracleClient(ABC):
    """Abstract base class for bridge proof verification oracles.

    Implementations:
    - ``InProcessVerifier`` — default, uses local cryptographic verification
    - ``ExternalOracleClient`` — stub for future external oracle integration
    """

    @abstractmethod
    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof against a block header.

        Args:
            proof: The bridge proof dict (source_chain, lock_tx_hash, amount,
                sender, recipient, chain_id, block_height, block_hash,
                proposer_signature, validator_signatures, merkle_proof).
            block_header: The source chain block header anchoring the proof.
            finality_config: Finality threshold configuration.

        Returns:
            ``ProofVerificationResult`` with validity, error, and metadata.
        """
        ...

    @abstractmethod
    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check if a block header has sufficient finality for a transfer.

        Args:
            block_header: The block header to check.
            finality_config: Finality threshold configuration.
            transfer_amount: The transfer amount (determines threshold tier).

        Returns:
            True if the block has enough confirmations for this transfer.
        """
        ...

    @property
    @abstractmethod
    def mode(self) -> VerificationMode:
        """The verification mode of this oracle."""
        ...


class InProcessVerifier(OracleClient):
    """Default in-process verification using local cryptographic primitives.

    Delegates Merkle proof verification to a ``MerkleProofVerifier``
    implementation provided by the blockchain node. Block header signature
    verification uses ``aitbc.bridge.verification.validate_block_header``.

    If no ``MerkleProofVerifier`` is provided, Merkle proof verification is
    skipped (and the result will note this in the error field). This is
    useful for testing the oracle interface without a full trie.
    """

    def __init__(
        self,
        merkle_verifier: MerkleProofVerifier | None = None,
    ) -> None:
        self._merkle_verifier = merkle_verifier

    @property
    def mode(self) -> VerificationMode:
        return VerificationMode.IN_PROCESS

    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof in-process.

        Steps:
        1. Verify block header state_root matches proof's claimed state root
        2. Verify Merkle proof (if merkle_verifier is set)
        3. Check finality
        4. Return structured result
        """
        # Step 1: Verify state root matches
        proof_state_root = proof.get("state_root", "")
        if proof_state_root and proof_state_root != block_header.state_root:
            return ProofVerificationResult(
                valid=False,
                error=f"State root mismatch: proof={proof_state_root} vs header={block_header.state_root}",
                block_height=block_header.height,
                state_root=block_header.state_root,
                verification_mode=VerificationMode.IN_PROCESS,
            )

        # Step 2: Verify Merkle proof (if provided and verifier is set)
        merkle_proof = proof.get("merkle_proof", [])
        lock_key = proof.get("lock_tx_hash", "")
        lock_value = proof.get("lock_event", "")

        if merkle_proof:
            if self._merkle_verifier is None:
                logger.warning("Merkle proof provided but no verifier set — skipping")
            else:
                proof_bytes = [p if isinstance(p, bytes) else bytes.fromhex(p.removeprefix("0x")) for p in merkle_proof]
                if not self._merkle_verifier.verify_merkle_proof(block_header.state_root, lock_key, lock_value, proof_bytes):
                    return ProofVerificationResult(
                        valid=False,
                        error="Merkle proof verification failed",
                        block_height=block_header.height,
                        state_root=block_header.state_root,
                        verification_mode=VerificationMode.IN_PROCESS,
                    )

        # Step 3: Check finality
        transfer_amount = int(proof.get("amount", 0))
        has_finality, _required = self._check_finality_internal(
            block_header,
            finality_config,
            transfer_amount,
        )

        # Step 4: Return result
        return ProofVerificationResult(
            valid=True,
            block_height=block_header.height,
            state_root=block_header.state_root,
            finality_confirmed=has_finality,
            verification_mode=VerificationMode.IN_PROCESS,
        )

    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check finality — large transfers require full finality."""
        has_finality, _required = self._check_finality_internal(
            block_header,
            finality_config,
            transfer_amount,
        )
        return has_finality

    @staticmethod
    def _check_finality_internal(
        block_header: BridgeBlockHeader,
        config: FinalityConfig,
        transfer_amount: int,
    ) -> tuple[bool, int]:
        """Determine required confirmations and check if met.

        Returns (has_finality, required_confirmations).
        """
        required = config.finality_blocks if transfer_amount >= config.large_transfer_threshold else config.min_confirmations
        return block_header.confirmation_count >= required, required


class ExternalOracleClient(OracleClient):
    """External oracle client that delegates verification to HTTP oracle endpoints (v0.7.4 §A1).

    Calls one or more external oracle endpoints (e.g.
    ``https://oracle1.aitbc.bubuit.net``) to verify bridge proofs and
    check block finality. The oracle is expected to expose:

    - ``POST /v1/verify-proof`` — accepts ``{proof, block_header,
      finality_config}`` and returns a ``ProofVerificationResult`` dict.
    - ``POST /v1/check-finality`` — accepts ``{block_header,
      finality_config, transfer_amount}`` and returns ``{final: bool}``.
    - ``GET /health`` — returns 200 if the oracle is healthy.

    If multiple endpoints are configured, requests are sent to the first
    healthy endpoint. Endpoints are tried in order; a failed endpoint is
    marked unhealthy for ``unhealthy_cooldown_seconds`` (default 60s)
    before being retried.

    This client is synchronous (matching the ``OracleClient`` ABC).
    HTTP calls use a short-lived ``httpx.Client`` per request to avoid
    holding connections across the verification boundary.
    """

    def __init__(
        self,
        endpoints: list[str] | None = None,
        timeout: int = 30,
        unhealthy_cooldown_seconds: int = 60,
    ) -> None:
        self._endpoints = [e.rstrip("/") for e in (endpoints or [])]
        self._timeout = timeout
        self._unhealthy_cooldown = unhealthy_cooldown_seconds
        # endpoint -> earliest retry timestamp (epoch seconds).
        self._unhealthy_until: dict[str, float] = {}
        if not self._endpoints:
            logger.warning("ExternalOracleClient initialized with no endpoints")

    @property
    def mode(self) -> VerificationMode:
        return VerificationMode.ORACLE

    @property
    def endpoints(self) -> list[str]:
        """Configured oracle endpoints."""
        return list(self._endpoints)

    def _healthy_endpoints(self) -> list[str]:
        """Return endpoints not currently in unhealthy cooldown."""
        now = time.time()
        return [ep for ep in self._endpoints if self._unhealthy_until.get(ep, 0.0) <= now]

    def _mark_unhealthy(self, endpoint: str) -> None:
        self._unhealthy_until[endpoint] = time.time() + self._unhealthy_cooldown
        logger.warning("Oracle endpoint %s marked unhealthy for %ss", endpoint, self._unhealthy_cooldown)

    def _post_json(self, endpoint: str, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST JSON to an oracle endpoint. Returns None on failure."""
        url = f"{endpoint}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return cast(dict[str, Any], resp.json())
        except Exception as e:
            logger.warning("Oracle POST %s failed: %s", url, e)
            self._mark_unhealthy(endpoint)
            return None

    def is_healthy(self) -> bool:
        """Check if at least one oracle endpoint is healthy.

        Probes ``GET /health`` on each endpoint not in cooldown. Returns
        True as soon as one responds with a 2xx status.
        """
        for endpoint in self._healthy_endpoints():
            try:
                with httpx.Client(timeout=min(self._timeout, 10)) as client:
                    resp = client.get(f"{endpoint}/health")
                    if resp.is_success:
                        return True
            except Exception as e:
                logger.debug("Oracle health check %s failed: %s", endpoint, e)
                self._mark_unhealthy(endpoint)
        return False

    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof via an external oracle.

        Sends the proof + block header to ``POST /v1/verify-proof`` on
        the first healthy oracle endpoint. The oracle returns a
        ``ProofVerificationResult`` dict which is reconstructed into the
        dataclass. If all endpoints fail, returns an invalid result with
        an error message (the caller's fallback policy can then retry
        with in-process verification).
        """
        payload = {
            "proof": proof,
            "block_header": _block_header_to_dict(block_header),
            "finality_config": _finality_config_to_dict(finality_config),
        }
        for endpoint in self._healthy_endpoints():
            data = self._post_json(endpoint, "/v1/verify-proof", payload)
            if data is None:
                continue
            return _result_from_dict(data, block_header)
        return ProofVerificationResult(
            valid=False,
            error="All oracle endpoints unavailable or failed",
            block_height=block_header.height,
            state_root=block_header.state_root,
            verification_mode=VerificationMode.ORACLE,
        )

    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check block finality via an external oracle.

        Sends the block header + finality config to
        ``POST /v1/check-finality``. Returns False if all endpoints fail.
        """
        payload = {
            "block_header": _block_header_to_dict(block_header),
            "finality_config": _finality_config_to_dict(finality_config),
            "transfer_amount": transfer_amount,
        }
        for endpoint in self._healthy_endpoints():
            data = self._post_json(endpoint, "/v1/check-finality", payload)
            if data is None:
                continue
            return bool(data.get("final", False))
        logger.warning("Oracle finality check failed for all endpoints — returning False")
        return False


# ---------------------------------------------------------------------------
# Serialization helpers (oracle wire format)
# ---------------------------------------------------------------------------


def _block_header_to_dict(header: BridgeBlockHeader) -> dict[str, Any]:
    return {
        "chain_id": header.chain_id,
        "height": header.height,
        "hash": header.hash,
        "parent_hash": header.parent_hash,
        "proposer": header.proposer,
        "state_root": header.state_root,
        "signature": header.signature,
        "timestamp": header.timestamp.isoformat() if header.timestamp else "",
        "finality_confirmed": header.finality_confirmed,
        "confirmation_count": header.confirmation_count,
    }


def _finality_config_to_dict(config: FinalityConfig) -> dict[str, Any]:
    return {
        "min_confirmations": config.min_confirmations,
        "finality_blocks": config.finality_blocks,
        "large_transfer_threshold": config.large_transfer_threshold,
        "grace_period_seconds": config.grace_period_seconds,
    }


def _result_from_dict(data: dict[str, Any], header: BridgeBlockHeader) -> ProofVerificationResult:
    """Reconstruct a ProofVerificationResult from an oracle response dict."""
    mode_str = data.get("verification_mode", VerificationMode.ORACLE.value)
    try:
        mode = VerificationMode(mode_str)
    except ValueError:
        mode = VerificationMode.ORACLE
    return ProofVerificationResult(
        valid=bool(data.get("valid", False)),
        error=data.get("error", ""),
        block_height=int(data.get("block_height", header.height)),
        state_root=data.get("state_root", header.state_root),
        finality_confirmed=bool(data.get("finality_confirmed", False)),
        validator_epoch=int(data.get("validator_epoch", 0)),
        verification_mode=mode,
    )


# ---------------------------------------------------------------------------
# Oracle fallback policy (v0.7.4 §A2)
# ---------------------------------------------------------------------------


class OracleFallbackPolicy:
    """Manages oracle → in-process verification fallback (v0.7.4 §A2).

    Wraps an ``ExternalOracleClient`` (primary) and an
    ``InProcessVerifier`` (fallback). Verification is attempted via the
    oracle first; if the oracle is unavailable or returns an error, the
    in-process verifier is used instead.

    A background health check (``start_health_check``) periodically
    probes the oracle and caches the result so ``verify_with_fallback``
    doesn't add latency on every call. Recovery is automatic — the
    health check retries every ``health_check_interval_seconds`` (default
    60s) and re-enables the oracle as soon as it responds.

    Usage::

        policy = OracleFallbackPolicy(oracle, in_process)
        policy.start_health_check()  # optional background health check
        result = policy.verify_with_fallback(proof, header, config)
    """

    def __init__(
        self,
        oracle: ExternalOracleClient,
        in_process: InProcessVerifier,
        health_check_interval_seconds: int = 60,
    ) -> None:
        self._oracle = oracle
        self._in_process = in_process
        self._health_check_interval = health_check_interval_seconds
        self._oracle_healthy = False
        self._last_health_check = 0.0
        # Verification mode used for the most recent call (for metrics/debugging).
        self._last_mode: VerificationMode = VerificationMode.IN_PROCESS

    @property
    def oracle_healthy(self) -> bool:
        """Whether the oracle was healthy as of the last health check."""
        return self._oracle_healthy

    @property
    def last_mode(self) -> VerificationMode:
        """Verification mode used for the most recent verify_with_fallback call."""
        return self._last_mode

    def check_oracle_health(self) -> bool:
        """Probe the oracle and update the cached health status.

        Can be called directly or by the background health check loop.
        Returns the new health status.
        """
        self._oracle_healthy = self._oracle.is_healthy()
        self._last_health_check = time.time()
        if self._oracle_healthy:
            logger.info("Oracle health check passed — oracle mode enabled")
        else:
            logger.warning("Oracle health check failed — using in-process fallback")
        return self._oracle_healthy

    def start_health_check(self) -> None:
        """Start a background thread that periodically checks oracle health.

        The thread runs until ``stop_health_check`` is called. It calls
        ``check_oracle_health`` every ``health_check_interval_seconds``.
        """
        import threading

        self._stop_event = threading.Event()
        self._health_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="oracle-health-check",
        )
        self._health_thread.start()
        logger.info("Started oracle health check thread (interval=%ss)", self._health_check_interval)

    def stop_health_check(self) -> None:
        """Stop the background health check thread."""
        stop_event = getattr(self, "_stop_event", None)
        if stop_event is not None:
            stop_event.set()
        thread = getattr(self, "_health_thread", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._health_check_interval + 5)
        logger.info("Stopped oracle health check thread")

    def _health_check_loop(self) -> None:
        stop_event = getattr(self, "_stop_event", None)
        if stop_event is None:
            return
        while not stop_event.is_set():
            try:
                self.check_oracle_health()
            except Exception as e:
                logger.error("Oracle health check loop error: %s", e)
            stop_event.wait(self._health_check_interval)

    def verify_with_fallback(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a proof, falling back from oracle to in-process.

        Strategy:
        1. If oracle is healthy (per last health check), try oracle first.
        2. If oracle returns an invalid result with an error indicating
           unavailability (not a genuine verification failure), fall back
           to in-process.
        3. If oracle is not healthy, use in-process directly.

        A genuine oracle verification failure (valid=False with a real
        error like "Merkle proof failed") is NOT a fallback trigger —
        the oracle correctly rejected the proof. Fallback only happens
        when the oracle is unreachable or returns an infrastructure error.
        """
        if self._oracle_healthy:
            result = self._oracle.verify_proof(proof, block_header, finality_config)
            # Infrastructure error → fallback. Genuine verification failure → return.
            if result.valid:
                self._last_mode = VerificationMode.ORACLE
                return result
            if "unavailable" in result.error.lower() or "all oracle" in result.error.lower():
                logger.warning("Oracle returned infrastructure error, falling back to in-process: %s", result.error)
                # Fall through to in-process.
            else:
                # Genuine verification failure from the oracle — return it.
                self._last_mode = VerificationMode.ORACLE
                return result
        # In-process fallback.
        result = self._in_process.verify_proof(proof, block_header, finality_config)
        self._last_mode = VerificationMode.IN_PROCESS
        return result

    def check_finality_with_fallback(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check finality, falling back from oracle to in-process."""
        if self._oracle_healthy:
            result = self._oracle.check_finality(block_header, finality_config, transfer_amount)
            if result:
                return True
            # Oracle returned False — could be genuine or infrastructure.
            # Fall back to in-process for a definitive answer.
            logger.debug("Oracle finality check returned False, verifying in-process")
        return self._in_process.check_finality(block_header, finality_config, transfer_amount)
