"""#1946: wallet RateLimitMiddleware must key on the trusted-proxy-aware
client IP — the service binds loopback behind nginx, so the raw peer is
always 127.0.0.1 and an unkeyed limiter collapses every caller into one
shared bucket (one client can 429 the whole service)."""


def test_wallet_limiter_keys_on_client_ip() -> None:
    from aitbc.rate_limiting import client_ip_for_rate_limit
    from wallet_app.main import app

    limiters = [m for m in app.user_middleware if m.cls.__name__ == "RateLimitMiddleware"]
    assert limiters, "wallet app lost its RateLimitMiddleware"
    assert limiters[0].kwargs.get("key_func") is client_ip_for_rate_limit
