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
  [Secret Management](secret-management.md) for where they do belong.
- **Cipher suites, protocol versions and HSTS are the terminator's
  configuration**, not AITBC's. Reviewing them means reviewing that host, which
  is operated outside this repository.

## See Also

- [Network Policy](../deployment/NETWORK_POLICY.md) - Public surfaces and TLS termination
- [Network Security](network-security.md) - Network hardening
- [Firewall Rules](firewall-rules.md) - Access control
- [Secret Management](secret-management.md) - Certificate storage
