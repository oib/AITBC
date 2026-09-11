# SSL/TLS Configuration

**AITBC does not manage certificates.** There is no certbot dependency, no ACME
client, and no renewal hook in any AITBC service or deployment script. Nothing in
this repository obtains, installs, renews or reloads a certificate.

TLS is terminated in front of AITBC, on the proxy host described in
[Network Policy](NETWORK_POLICY.md) — the only host that answers `443`. How that
host obtains its certificates is an operator decision outside this repository's
scope, and deliberately not documented here.

## What that means for a deployment

- AITBC services speak plain HTTP and bind to loopback or a container-internal
  address. None of them listen on `443`, and none should be given a certificate.
- Do not add `ssl_certificate` directives to a service's own nginx vhost. The
  vhosts shipped under `infra/nginx/` proxy cleartext to the service and expect
  TLS to have been handled upstream.
- If a service needs to know it is being reached over TLS, read the forwarded
  headers. Services are started with uvicorn's `--proxy-headers`.
- Certificate expiry is monitored by whoever operates the terminator, not by
  AITBC's own monitoring.

## See Also

- [Network Policy](NETWORK_POLICY.md) - Which ports are public, and where TLS terminates
- [Single Server](single-server.md) - Nginx configuration
- [Configuration](configuration.md) - Environment configuration
