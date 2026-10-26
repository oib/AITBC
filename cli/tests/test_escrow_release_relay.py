"""ESCROW-RELEASE-2: release call sites go through the coordinator JWT
release relay first; the rpc fallback fires only on auth/transport failures,
never on a relay business refusal.
"""

from types import SimpleNamespace
from typing import Any, cast

import click

import aitbc_cli.commands.market.escrow as esc_mod


class _Resp:
    def __init__(self, status_code: int, detail: str, headers: dict | None = None):
        self.status_code = status_code
        self._detail = detail
        self.headers = headers or {}

    def json(self):
        return {"detail": self._detail}


class _StatusError(RuntimeError):
    def __init__(self, status_code: int, detail: str = "", headers: dict | None = None):
        super().__init__(f"HTTP {status_code}")
        self.response = _Resp(status_code, detail, headers)


def _config():
    return SimpleNamespace(
        hub_proposer_id="0xPROP",
        blockchain_rpc_api_key=None,
        hub_discovery_url="https://hub.aitbc.bubuit.net",
        blockchain_rpc_url="http://127.0.0.1:8202",
        coordinator_api_url="http://localhost:8203",
    )


def _ctx():
    return cast(click.Context, SimpleNamespace(obj={"output_format": "json"}))


class _RelayClient:
    """Stand-in for the coordinator HTTP client the relay helper builds."""

    posts: list[dict] = []
    result: Any = None
    exc: Exception | None = None

    def __init__(self, **kw):
        self.kw = kw

    def post(self, endpoint, json=None):
        assert endpoint == "/v1/escrow/release"
        self.posts.append(dict(json))
        if self.exc is not None:
            raise self.exc
        return self.result


class _RpcClient:
    """Stand-in for the chain rpc client (posts + gets tracked)."""

    posts: list[dict] = []
    gets: list[str] = []
    post_result: Any = None
    post_exc: Exception | None = None
    get_result: Any = None
    get_exc: Exception | None = None

    def __init__(self, base_url, **kw):
        self.base_url = base_url

    def post(self, endpoint, json=None):
        self.posts.append({"endpoint": endpoint, "json": dict(json or {})})
        if self.post_exc is not None:
            raise self.post_exc
        return self.post_result

    def get(self, endpoint):
        self.gets.append(endpoint)
        if self.get_exc is not None:
            raise self.get_exc
        return self.get_result


def _wire(monkeypatch, relay_cls=None, rpc_cls=None, token="tok"):
    """Patch the client factories; return the class attributes for inspection."""
    relay = relay_cls or _RelayClient
    rpc = rpc_cls or _RpcClient
    relay.posts = []
    relay.result = {"success": True, "tx_hash": "0xrel", "released_amount": "0.5"}
    relay.exc = None
    rpc.posts = []
    rpc.gets = []
    rpc.post_result = {"tx_hash": "0xrpc", "released_amount": "0.5"}
    rpc.post_exc = None
    rpc.get_result = {"job_id": "j1", "amount": "1.0", "buyer": "0xB"}
    rpc.get_exc = None
    monkeypatch.setattr(esc_mod, "AITBCHTTPClient", relay)
    monkeypatch.setattr(esc_mod, "_get_rpc_client", lambda config, base_url, timeout=10: rpc(base_url))
    monkeypatch.setattr(esc_mod, "_client_token", lambda ctx: token)
    monkeypatch.setattr(esc_mod, "_coordinator_base_url", lambda ctx: "http://coord")
    return relay, rpc


# --- relay happy path --------------------------------------------------------


def test_release_via_relay_success_no_rpc(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5", job_tx_hash="0xj")
    assert result == {"success": True, "tx_hash": "0xrel", "released_amount": "0.5"}
    assert failures == []
    assert relay.posts == [{"job_id": "j1", "amount": "0.5", "job_tx_hash": "0xj"}]
    # The rpc path was never touched — the relay is authoritative.
    assert rpc.posts == []


def test_release_via_relay_reads_lock_amount_when_unset(monkeypatch):
    """The bare-release sites send no amount: the helper reads the escrow's
    locked amount (GET is not allowlist-blocked) to build the relay body."""
    relay, rpc = _wire(monkeypatch)
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1")
    assert result is not None
    assert relay.posts == [{"job_id": "j1", "amount": "1.0"}]
    assert "/rpc/escrow/j1" in rpc.gets


# --- business refusals are terminal (NO rpc fallback) ------------------------


def test_relay_buyer_mismatch_403_never_falls_back(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(403, "escrow buyer does not match the wallet bound to this credential")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is None
    assert rpc.posts == []
    assert len(failures) == 1
    assert "403" in failures[0] and "buyer" in failures[0]


def test_relay_already_refunded_409_never_falls_back(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(409, "Escrow for job_id=j1 has already been refunded")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is None
    assert rpc.posts == []
    assert "409" in failures[0]


def test_relay_amount_over_lock_400_never_falls_back(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(400, "release amount exceeds the escrow's locked amount")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="9")
    assert result is None
    assert rpc.posts == []
    assert "400" in failures[0]


# --- fallback classes ---------------------------------------------------------


def test_no_credential_falls_back_with_named_hint(monkeypatch):
    relay, rpc = _wire(monkeypatch, token=None)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert relay.posts == []  # relay never attempted
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"
    assert rpc.posts[0]["json"] == {"amount": "0.5"}
    assert any("no stored client credential" in f and "auth login" in f for f in failures)


def test_relay_502_falls_back_to_rpc(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(502, "the escrow release relay could not reach the settlement node")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"
    assert any("relay unavailable" in f and "502" in f for f in failures)


def test_relay_connection_error_falls_back(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = ConnectionError("refused")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert any("relay unavailable" in f for f in failures)


def test_relay_401_falls_back_expired_jwt(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(401, "token expired")
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is not None
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"


def test_relay_404_falls_back_undeployed_endpoint(monkeypatch):
    """An older coordinator without the relay route 404s — the rpc path keeps
    the release working until the fleet is upgraded."""
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(404, "Not Found")
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is not None
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"


def test_relay_bare_forbidden_403_falls_back(monkeypatch):
    """A bare {"detail": "Forbidden"} 403 is the middleware deny-by-default on
    a coordinator missing the route's security-matrix entry — a deployment
    gap, not a business refusal — so the rpc fallback still fires."""
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(403, "Forbidden")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"
    assert any("relay unavailable" in f and "403" in f for f in failures)


def test_relay_business_403_with_detail_stays_terminal(monkeypatch):
    """A 403 carrying a real refusal reason (not the bare middleware word)
    remains terminal — only the exact 'Forbidden' string is a skip."""
    relay, rpc = _wire(monkeypatch)
    relay.exc = _StatusError(403, "client credential cannot release another buyer's escrow")
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is None
    assert rpc.posts == []


# --- amount validation: invalid amounts never reach the relay ---------------


def test_zero_amount_skips_relay_goes_rpc(monkeypatch):
    """A zero metered amount would 400 terminally at the relay — the helper
    must send it straight to the rpc, which reports the refusal itself."""
    relay, rpc = _wire(monkeypatch)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert relay.posts == []
    assert rpc.posts[0]["json"] == {"amount": "0"}
    assert any("not positive" in f for f in failures)


def test_unparseable_amount_skips_relay_goes_rpc(monkeypatch):
    relay, rpc = _wire(monkeypatch)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="abc")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert relay.posts == []
    assert any("not a number" in f for f in failures)


# --- one retry on transport failure -------------------------------------------


def test_relay_retried_once_on_connection_error(monkeypatch):
    """A timeout/connection error gets one retry before the rpc fallback —
    the relay dedups on job_id so a repost cannot double-release."""

    class _FlakyRelay(_RelayClient):
        attempts = 0

        def post(self, endpoint, json=None):
            type(self).attempts += 1
            self.posts.append(dict(json))
            if type(self).attempts == 1:
                raise ConnectionError("refused")
            return {"success": True, "tx_hash": "0xrel"}

    relay, rpc = _wire(monkeypatch, relay_cls=_FlakyRelay)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"success": True, "tx_hash": "0xrel"}
    assert _FlakyRelay.attempts == 2
    assert len(relay.posts) == 2
    assert rpc.posts == []


def test_relay_two_connection_errors_then_falls_back(monkeypatch):
    """Both attempts failing on transport → rpc fallback, exactly two tries."""

    class _DeadRelay(_RelayClient):
        attempts = 0

        def post(self, endpoint, json=None):
            type(self).attempts += 1
            raise ConnectionError("refused")

    relay, rpc = _wire(monkeypatch, relay_cls=_DeadRelay)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrpc", "released_amount": "0.5"}
    assert _DeadRelay.attempts == 2
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"
    assert any("relay unavailable" in f for f in failures)


def test_relay_http_error_not_retried(monkeypatch):
    """A statused failure (e.g. 502) is NOT retried — only transport errors."""

    class _ErrorRelay(_RelayClient):
        attempts = 0

        def post(self, endpoint, json=None):
            type(self).attempts += 1
            raise _StatusError(502, "the escrow release relay could not reach the settlement node")

    relay, rpc = _wire(monkeypatch, relay_cls=_ErrorRelay)
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is not None
    assert _ErrorRelay.attempts == 1
    assert rpc.posts[0]["endpoint"] == "/rpc/escrow/j1/release"


# --- bounded retry on a relay 425 "lock not yet sealed" ----------------------


def _no_sleep(monkeypatch):
    """Record sleep durations instead of sleeping; return the calls list."""
    calls: list[float] = []
    monkeypatch.setattr(esc_mod.time, "sleep", calls.append)
    return calls


def test_relay_425_then_200_releases(monkeypatch):
    """A fast job asked before the lock sealed: the helper waits and reposts
    the same body — the relay dedup makes the repost safe."""
    _no_sleep(monkeypatch)

    class _Sealing(_RelayClient):
        attempts = 0

        def post(self, endpoint, json=None):
            type(self).attempts += 1
            self.posts.append(dict(json))
            if type(self).attempts == 1:
                raise _StatusError(425, "escrow lock for job_id=j1 is not yet sealed in a block")
            return {"success": True, "tx_hash": "0xrel"}

    relay, rpc = _wire(monkeypatch, relay_cls=_Sealing)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"success": True, "tx_hash": "0xrel"}
    assert _Sealing.attempts == 2
    assert relay.posts == [{"job_id": "j1", "amount": "0.5"}, {"job_id": "j1", "amount": "0.5"}]
    assert rpc.posts == []


def test_relay_425_forever_named_retryable_no_rpc(monkeypatch):
    """The 425 bound is finite: a never-sealing lock ends in a named
    *retryable* condition (not a business refusal) and the rpc path is
    never tried — it would 425 identically and cannot authenticate."""
    sleeps = _no_sleep(monkeypatch)

    class _NeverSealed(_RelayClient):
        attempts = 0

        def post(self, endpoint, json=None):
            type(self).attempts += 1
            raise _StatusError(425, "escrow lock for job_id=j1 is not yet sealed in a block")

    relay, rpc = _wire(monkeypatch, relay_cls=_NeverSealed)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is None
    assert rpc.posts == []
    # Bounded: a handful of reposts, total sleep under ~30 s.
    assert 1 < _NeverSealed.attempts < 10
    assert 0 < sum(sleeps) <= esc_mod._SEAL_WAIT_TOTAL
    assert len(failures) == 1
    assert "425" in failures[0]
    assert "not yet sealed" in failures[0]
    assert "retryable" in failures[0]


def test_relay_425_honours_retry_after_header(monkeypatch):
    """The wait comes from Retry-After when the response carries one
    (capped per wait); without it the default applies."""
    sleeps = _no_sleep(monkeypatch)

    class _RetryAfter(_RelayClient):
        attempts = 0

        def post(self, endpoint, json=None):
            type(self).attempts += 1
            if type(self).attempts == 1:
                raise _StatusError(
                    425,
                    "lock not yet sealed",
                    headers={"Retry-After": "30"},  # capped at _SEAL_WAIT_CAP
                )
            if type(self).attempts == 2:
                raise _StatusError(425, "lock not yet sealed")  # no header -> default
            return {"success": True, "tx_hash": "0xrel"}

    _wire(monkeypatch, relay_cls=_RetryAfter)
    result, _ = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"success": True, "tx_hash": "0xrel"}
    assert sleeps == [esc_mod._SEAL_WAIT_CAP, esc_mod._SEAL_WAIT_DEFAULT]


def test_relay_425_business_4xx_still_terminal(monkeypatch):
    """Interleaved sanity: a non-425 4xx is never retried and never waits."""
    sleeps = _no_sleep(monkeypatch)

    class _Conflict(_RelayClient):
        attempts = 0

        def post(self, endpoint, json=None):
            type(self).attempts += 1
            raise _StatusError(409, "Escrow for job_id=j1 has already been refunded")

    _wire(monkeypatch, relay_cls=_Conflict)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is None
    assert _Conflict.attempts == 1
    assert sleeps == []
    assert "409" in failures[0]


def test_amount_unreadable_posts_without_amount(monkeypatch):
    """No amount argument and no readable escrow row → relay without an
    amount field; the coordinator derives the full lock server-side (#469)."""
    relay, rpc = _wire(monkeypatch)
    rpc.get_exc = _StatusError(404, "escrow not found")
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1")
    assert result == {"success": True, "tx_hash": "0xrel", "released_amount": "0.5"}
    assert relay.posts == [{"job_id": "j1"}]
    assert rpc.posts == []
    assert failures == []


# --- ESCROW-BREAKER-1: the relay leg must not be starved by circuit breaker ---


def _real_relay_client_with_session(monkeypatch):
    """Use the real ``AITBCHTTPClient`` for the relay while patching the
    transport (``requests.Session.post``) at the bottom. Returns the list that
    collects every real HTTP request that went out."""
    import requests

    from aitbc.network.client import AITBCHTTPClient as _RealClient

    sent: list[str] = []
    monkeypatch.setattr(esc_mod, "AITBCHTTPClient", _RealClient)
    monkeypatch.setattr(esc_mod, "_client_token", lambda ctx: "tok")
    monkeypatch.setattr(esc_mod, "_coordinator_base_url", lambda ctx: "http://coord")

    def _install(responder):
        def _post(self, url, **kw):
            sent.append(url)
            status_code, resp_url, content, headers = responder(url)
            resp = requests.Response()
            resp.status_code, resp.url, resp._content = status_code, resp_url, content
            resp.headers.update(headers)
            resp.request = requests.PreparedRequest()
            resp.request.prepare(method="POST", url=url)
            return resp

        monkeypatch.setattr(requests.Session, "post", _post)

    return sent, _install


def test_relay_reposts_not_starved_by_own_circuit_breaker(monkeypatch):
    """ESCROW-BREAKER-1 reproducer: a lock that stays unsealed past the
    breaker threshold must still get its full bounded repost budget.

    The relay helper reuses one ``AITBCHTTPClient`` across the 425
    wait+repost loop, and every 425 counted as a breaker failure — after
    ``circuit_breaker_threshold`` (5) reposts the client's ``check()``
    rejected the next POST outright *before it was sent*, the error carried
    no HTTP status, and it was classified as a transport failure →
    "unavailable" → rpc fallback → escrow stayed locked (live finding on
    #472). The relay client now opts out of the circuit breaker: its bounded
    retry budget is the flood protection."""
    _no_sleep(monkeypatch)
    relay, rpc = _wire(monkeypatch)
    sent, install = _real_relay_client_with_session(monkeypatch)
    install(
        lambda url: (
            425,
            url,
            b'{"detail": "escrow lock for job_id=j1 is not yet sealed in a block"}',
            {"Retry-After": "1"},
        )
    )
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result is None
    assert rpc.posts == []
    # The named retryable-425 condition — not a generic "unavailable" skip
    # produced by a breaker rejection.
    assert len(failures) == 1
    assert "425" in failures[0]
    assert "not yet sealed" in failures[0]
    # Every repost really went out on the wire — more than the default
    # breaker threshold (5) would have allowed.
    assert len(sent) > 5
    assert all(url.endswith("/v1/escrow/release") for url in sent)


def test_relay_recovers_after_breaker_threshold_of_425s(monkeypatch):
    """The lock seals mid-loop: repost number > threshold must still be sent
    and release the escrow."""
    _no_sleep(monkeypatch)
    relay, rpc = _wire(monkeypatch)
    sent, install = _real_relay_client_with_session(monkeypatch)
    n = {"i": 0}

    def responder(url):
        n["i"] += 1
        if n["i"] <= 7:  # past the default breaker threshold of 5
            return (
                425,
                url,
                b'{"detail": "escrow lock for job_id=j1 is not yet sealed in a block"}',
                {"Retry-After": "1"},
            )
        return 200, url, b'{"tx_hash": "0xrel", "released_amount": "0.5"}', {}

    install(responder)
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1", amount="0.5")
    assert result == {"tx_hash": "0xrel", "released_amount": "0.5"}
    assert len(sent) == 8
    assert rpc.posts == []


def test_relay_unaffected_by_same_process_rpc_probe_failures(monkeypatch):
    """Scope pin: the breaker is per-client-instance, so failures accrued by
    the rpc probing clients can never feed the relay client's breaker — and
    the relay must still go out right after local-503 + hub-403 probes."""
    _no_sleep(monkeypatch)
    relay, rpc = _wire(monkeypatch)
    rpc.get_exc = _StatusError(503, "node cannot settle")
    rpc.post_exc = _StatusError(403, "Forbidden")
    sent, install = _real_relay_client_with_session(monkeypatch)
    install(lambda url: (200, url, b'{"tx_hash": "0xrel", "released_amount": "0.5"}', {}))
    result, failures = esc_mod._post_escrow_release(_ctx(), _config(), "j1")  # no amount → probes
    assert result == {"tx_hash": "0xrel", "released_amount": "0.5"}
    assert sent == ["http://coord/v1/escrow/release"]
    assert rpc.gets  # the probing really ran and failed
    assert rpc.posts == []


# --- command-level ------------------------------------------------------------


def test_escrow_release_command_relays(monkeypatch):
    from click.testing import CliRunner

    relay, rpc = _wire(monkeypatch)
    monkeypatch.setattr(esc_mod, "get_config", _config)
    result = CliRunner().invoke(esc_mod.escrow_release, ["--job-id", "j1"], obj={"output_format": "json"})
    assert result.exit_code == 0
    assert relay.posts == [{"job_id": "j1", "amount": "1.0"}]
    assert rpc.posts == []
