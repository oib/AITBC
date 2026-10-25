"""In-process stand-ins for the escrow path's HTTP edges (ESCROW-E2E-TEST-1).

Three fake endpoints sit behind one :class:`StubChain` state object:

- the customer node's local blockchain RPC (``LOCAL_RPC_URL``) — serves
  ``/health`` and ``/rpc/account/*`` but refuses ``POST /rpc/escrow/create``
  with a bare 403, exactly the nginx-allowlist position a customer node sits
  in, so the real ``_escrow_create`` falls through to the coordinator relay;
- the settlement node's chain RPC (``SETTLEMENT_RPC_URL``) — enforces the
  rules the real chain route enforces: ``lock_tx.to`` must be the advertised
  node wallet, an occupied ``(from, nonce)`` mempool slot answers 400
  "already occupied", a release may not exceed the locked amount and may not
  repeat on a settled escrow;
- the coordinator (``COORDINATOR_URL``) — forwarded to a FastAPI
  ``TestClient`` running the real app, so relayed calls cross the real
  ``AuthMiddleware``/security-matrix boundary in-process.

Errors are raised as :class:`aitbc.exceptions.NetworkError` with an
``httpx.HTTPStatusError`` as ``__cause__`` — the same shape both
``_find_http_status_error`` (coordinator) and ``http_response_status`` /
``http_error_detail`` (CLI) unwrap in production.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from aitbc.exceptions import NetworkError

LOCAL_RPC_URL = "http://127.0.0.1:8202"
SETTLEMENT_RPC_URL = "http://settlement-node.test"
COORDINATOR_URL = "http://coordinator.test"


def refusal(method: str, url: str, status_code: int, detail: str) -> NetworkError:
    """A NetworkError carrying an HTTP status answer, like a real refusal."""
    request = httpx.Request(method, url)
    response = httpx.Response(status_code, json={"detail": detail}, request=request)
    error = NetworkError(f"{method} {url} failed with HTTP {status_code}")
    error.__cause__ = httpx.HTTPStatusError(f"status {status_code}", request=request, response=response)
    return error


class StubChain:
    """The settlement-capable chain, enforcing the real escrow rules."""

    def __init__(self, node_wallet: str, chain_id: str = "ait-testchain") -> None:
        self.node_wallet = node_wallet
        self.chain_id = chain_id
        self.escrows: dict[str, dict[str, Any]] = {}
        self.account_nonces: dict[str, int] = {}
        # Pending mempool slots — a sealed/pending tx claims (from, nonce).
        self.occupied_slots: dict[tuple[str, int], dict[str, Any]] = {}
        # Call log: (base, method, path, payload) — assertions read this.
        self.calls: list[tuple[str, str, str, dict[str, Any] | None]] = []
        self.release_tx_counter = 0
        # A customer node's local RPC cannot serve /rpc/escrow/create — the
        # nginx allowlist 403s it. None disables the refusal.
        self.refuse_local_create: int | None = 403
        # One-shot refusal for the next /rpc/transactions/market POST.
        self.next_market_tx_error: tuple[int, str] | None = None

    # -- helpers --------------------------------------------------------

    def calls_to(self, path_suffix: str, *, method: str = "POST", base: str | None = None) -> list:
        return [c for c in self.calls if c[1] == method and c[2].endswith(path_suffix) and (base is None or c[0] == base)]

    def escrow(self, job_id: str) -> dict[str, Any]:
        return self.escrows[job_id]

    def occupy_slot(self, sender: str, nonce: int, tx: dict[str, Any] | None = None) -> None:
        self.occupied_slots[(sender.lower(), nonce)] = tx or {}

    def set_state(self, job_id: str, **fields: Any) -> None:
        """Force an escrow row's state (e.g. refunded) without a release call."""
        self.escrows[job_id].update(fields)

    # -- the RPC surface -------------------------------------------------

    def get(self, base: str, path: str) -> Any:
        self.calls.append((base, "GET", path, None))
        if path == "/health":
            # The settlement wallet is advertised at the blockchain RPC's own
            # /health — the same field get_node_wallet reads.
            return {"status": "ok", "node_wallet": self.node_wallet, "chain_id": self.chain_id}
        if path == "/proposer":
            return {"chain_id": self.chain_id}
        if path.startswith("/rpc/account/"):
            address = path.rsplit("/", 1)[-1]
            return {"nonce": self.account_nonces.get(address.lower(), 0)}
        if path.startswith("/rpc/escrow/"):
            job_id = path.rsplit("/", 1)[-1]
            row = self.escrows.get(job_id)
            if row is None:
                raise refusal("GET", base + path, 404, f"escrow not found for job_id={job_id}")
            return dict(row)
        raise refusal("GET", base + path, 404, f"no such route: {path}")

    def post(self, base: str, path: str, payload: dict[str, Any] | None) -> Any:
        self.calls.append((base, "POST", path, payload))
        url = base + path
        if base == LOCAL_RPC_URL and path == "/rpc/escrow/create" and self.refuse_local_create is not None:
            raise refusal("POST", url, self.refuse_local_create, "Forbidden")
        if path == "/rpc/escrow/create":
            return self._create(url, base, payload or {})
        if path == "/rpc/transactions/market":
            return self._market_tx(url, payload or {})
        if path.startswith("/rpc/escrow/") and path.endswith("/release"):
            job_id = path[len("/rpc/escrow/") : -len("/release")]
            return self._release(url, job_id, payload or {})
        raise refusal("POST", url, 404, f"no such route: {path}")

    # -- the enforced rules ----------------------------------------------

    def _create(self, url: str, base: str, body: dict[str, Any]) -> dict[str, Any]:
        job_id = body.get("job_id")
        lock_tx = body.get("lock_tx") or {}
        if not isinstance(job_id, str) or not job_id:
            raise refusal("POST", url, 400, "job_id is required")
        existing = self.escrows.get(job_id)
        if existing is not None:
            return {"contract_id": existing["contract_id"], "duplicate": True}
        # The rule that broke in production: the lock must pay the node
        # wallet (escrow custody), never the consensus proposer id.
        to = lock_tx.get("to")
        if not isinstance(to, str) or to.lower() != self.node_wallet.lower():
            raise refusal("POST", url, 400, "lock_tx to must be the node wallet")
        amount_units = lock_tx.get("amount")
        if not isinstance(amount_units, int) or amount_units <= 0:
            raise refusal("POST", url, 400, "lock_tx amount must be a positive integer of compute units")
        contract_id = f"esc-{job_id}"
        self.escrows[job_id] = {
            "job_id": job_id,
            "contract_id": contract_id,
            "buyer": body.get("buyer"),
            "provider": body.get("provider"),
            "amount": body.get("amount"),
            "locked_units": amount_units,
            "state": "locked",
        }
        # A signed lock sits in the mempool and occupies its nonce slot —
        # the record leg colliding here is the nonce-race regression.
        sender = lock_tx.get("from")
        nonce = lock_tx.get("nonce")
        if isinstance(sender, str) and isinstance(nonce, int):
            self.occupy_slot(sender, nonce, lock_tx)
        return {"contract_id": contract_id, "success": True}

    def _release(self, url: str, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        row = self.escrows.get(job_id)
        if row is None:
            raise refusal("POST", url, 404, f"escrow not found for job_id={job_id}")
        if row.get("state") == "refunded" or row.get("refunded_at"):
            raise refusal("POST", url, 409, f"Escrow for job_id={job_id} has already been refunded")
        if row.get("state") == "released" or row.get("released_at"):
            # One release per job: a repeat returns the stored outcome.
            return {
                "success": True,
                "contract_id": row["contract_id"],
                "tx_hash": row.get("release_tx_hash"),
                "duplicate": True,
            }
        raw_amount = body.get("amount")
        if raw_amount is None:
            amount = Decimal(str(row["amount"]))
        else:
            try:
                amount = Decimal(str(raw_amount))
            except (InvalidOperation, ValueError):
                raise refusal("POST", url, 400, f"Invalid amount: {raw_amount}") from None
            if amount <= 0:
                raise refusal("POST", url, 400, "release amount must be positive")
        if amount > Decimal(str(row["amount"])):
            raise refusal("POST", url, 400, "release amount exceeds the locked amount")
        self.release_tx_counter += 1
        tx_hash = f"0xrelease{self.release_tx_counter:04d}"
        row.update(state="released", released_at="now", release_tx_hash=tx_hash)
        refund = Decimal(str(row["amount"])) - amount
        return {
            "success": True,
            "contract_id": row["contract_id"],
            "tx_hash": tx_hash,
            "released_amount": str(amount),
            "refunded_amount": str(refund),
        }

    def _market_tx(self, url: str, tx: dict[str, Any]) -> dict[str, Any]:
        if self.next_market_tx_error is not None:
            status_code, detail = self.next_market_tx_error
            self.next_market_tx_error = None
            raise refusal("POST", url, status_code, detail)
        sender = str(tx.get("from", "")).lower()
        nonce = tx.get("nonce")
        if isinstance(nonce, int) and (sender, nonce) in self.occupied_slots:
            raise refusal(
                "POST",
                url,
                400,
                f"nonce slot ({tx.get('from')}, {nonce}) already occupied by 0xpending with fee 360000 >= 360000",
            )
        if not tx.get("signature"):
            raise refusal("POST", url, 400, "Signature required")
        if isinstance(nonce, int):
            self.occupy_slot(sender, nonce, tx)
        tx_hash = f"0xrec{len(self.occupied_slots):04d}"
        return {"transaction_hash": tx_hash}


class AsyncChainClient:
    """Drop-in for ``AsyncAITBCHTTPClient`` bound to a :class:`StubChain`."""

    def __init__(self, chain: StubChain, *args: Any, timeout: float = 10.0, api_key: Any = None, **kwargs: Any) -> None:
        self.chain = chain

    async def get(self, url: str, **kwargs: Any) -> Any:
        base, path = self._split(url)
        return self.chain.get(base, path)

    async def post(self, url: str, json: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        base, path = self._split(url)
        return self.chain.post(base, path, json)

    @staticmethod
    def _split(url: str) -> tuple[str, str]:
        for base in (SETTLEMENT_RPC_URL, LOCAL_RPC_URL):
            if url.startswith(base):
                return base, url[len(base) :]
        raise AssertionError(f"chain client asked for an unstubbed URL: {url}")


def make_async_client_class(chain: StubChain):
    """Class factory — the services instantiate the client per call."""

    class _Bound(AsyncChainClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(chain, *args, **kwargs)

    return _Bound


class CliHttpBridge:
    """Drop-in for ``AITBCHTTPClient`` routing between the three stub edges.

    ``base_url`` picks the destination: the coordinator URL forwards to the
    FastAPI ``TestClient`` (real middleware, real relay routers); the local
    and settlement URLs reach the :class:`StubChain`.
    """

    def __init__(
        self,
        test_client: Any,
        chain: StubChain,
        base_url: str = "",
        timeout: int | float = 30,
        headers: dict[str, str] | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._test_client = test_client
        self._chain = chain
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})

    def get(self, endpoint: str, params: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        return self._dispatch("GET", endpoint, None)

    def get_json(self, endpoint: str, params: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        return self._dispatch("GET", endpoint, None)

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._dispatch("POST", endpoint, json)

    def _dispatch(self, method: str, endpoint: str, payload: dict[str, Any] | None) -> Any:
        if self.base_url == COORDINATOR_URL:
            self._chain.calls.append((COORDINATOR_URL, method, endpoint, payload))
            response = self._test_client.request(
                method,
                endpoint,
                json=payload,
                headers=self.headers or None,
            )
            if response.status_code >= 400:
                # Re-wrap the httpx answer as the wrapped NetworkError the
                # real client's raise_for_status path produces.
                error = NetworkError(f"{method} {endpoint} failed with HTTP {response.status_code}")
                error.__cause__ = httpx.HTTPStatusError(
                    f"status {response.status_code}", request=response.request, response=response
                )
                raise error
            return response.json()
        if self.base_url in (LOCAL_RPC_URL, SETTLEMENT_RPC_URL):
            if method == "GET":
                return self._chain.get(self.base_url, endpoint)
            return self._chain.post(self.base_url, endpoint, payload)
        raise AssertionError(f"CLI bridge asked for an unstubbed base_url: {self.base_url}")


def make_cli_bridge_class(test_client: Any, chain: StubChain):
    class _Bound(CliHttpBridge):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(test_client, chain, *args, **kwargs)

    return _Bound
