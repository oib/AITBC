# SSL/TLS Configuration

**Certificate management is out of scope for AITBC.** No service in this
repository obtains, stores, rotates or renews a certificate, and no deployment
script installs an ACME client. Earlier revisions of this page carried certbot
recipes; they described something AITBC has never done.

TLS terminates on the proxy host in front of the fleet — see
[Network Policy](../deployment/NETWORK_POLICY.md). Everything behind it speaks
cleartext HTTP over a container-internal address, by design: the bind address,
not TLS, is what limits reach on that plane.

## Implications for security review

- **Do not treat a cleartext AITBC listener as a finding on its own.** It is the
  intended configuration. The question worth asking about any given port is
  whether its bind address is right, which
  [Network Policy](../deployment/NETWORK_POLICY.md) covers.
- **Secrets must not be placed in certificate stores.** See
  [Secret Management](SECURITY.md) for where they do belong.
- **Cipher suites, protocol versions and HSTS are the terminator's
  configuration**, not AITBC's. Reviewing them means reviewing that host, which
  is operated outside this repository.

## See also

- [Security overview](SECURITY.md) — the consolidated page that replaced the generic checklists

## Deployment notes

- AITBC services speak plain HTTP and bind to loopback or a
  container-internal address. None of them listen on `443`, and none
  should be given a certificate.
- Do not add `ssl_certificate` directives to a service's own nginx vhost.
  The vhosts shipped under `infra/nginx/` proxy cleartext to the service
  and expect TLS to have been handled upstream.
- If a service needs to know it is being reached over TLS, read the
  forwarded headers. Services are started with uvicorn's
  `--proxy-headers`.
