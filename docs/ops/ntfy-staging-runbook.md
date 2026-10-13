# SD-2a — self-hosted ntfy on ns2 (runbook, staging only)

Alert delivery for the AITBC watchers that does not depend on hub. ntfy runs
in its own **Incus system container** on ns2, published as
`https://ntfy.bubuit.net` (DNS already points at ns2's public IP
152.53.242.245). TLS terminates on the ns2 host nginx; inside the container
ntfy binds loopback only.

Companion files (this repo):

| file | install to |
|---|---|
| `scripts/deployment/ntfy/server.yml` | `/etc/ntfy/server.yml` **inside the container** |
| `scripts/deployment/ntfy/ntfy-override.conf` | `/etc/systemd/system/ntfy.service.d/override.conf` **inside the container** |
| `scripts/deployment/ntfy/ntfy.bubuit.net.nginx` | `/etc/nginx/sites-enabled/ntfy.bubuit.net` on **ns2 host** |
| `scripts/deployment/ntfy/aitbc-log-scrub.conf` | `/etc/nginx/conf.d/aitbc-log-scrub.conf` on **ns2 host** (same format as SEC-14c) |

## 1. Container spec

```bash
# on ns2 — Debian 13 system container, autostart with the host
incus launch images:debian/13 ntfy
incus config set ntfy boot.autostart=true
incus config set ntfy limits.cpu=2 limits.memory=512MB

# record the base image fingerprint for the pin (the alias moves with each
# rebuild — the fingerprint is the immutable reference):
incus image info images:debian/13 | grep -E "Fingerprint|Created"

# persistent volume for all ntfy state (cache/auth/webpush DBs)
incus storage volume create default ntfy-data
incus config device add ntfy varlibntfy disk source=ntfy-data path=/var/lib/ntfy

# the ONLY published port: a proxy device on the host's loopback.
# listen is evaluated on the host, connect inside the container —
# ntfy itself stays bound to container loopback.
incus config device add ntfy ntfy2586 proxy \
    listen=tcp:127.0.0.1:2586 connect=tcp:127.0.0.1:2586
```

- Restart policy: `Restart=always RestartSec=5` in the unit override
  (inside the container) plus `boot.autostart=true` on the container.
- Nothing else is published: the proxy device listens on host loopback
  only, and the container's eth0 sits on the internal incusbr0 NAT bridge.

## 2. Install + server.yml

```bash
incus exec ntfy -- bash
# inside the container:
apt update && apt install -y curl ca-certificates
curl -fLO https://github.com/binwiederhier/ntfy/releases/download/v2.29.0/ntfy_2.29.0_linux_amd64.deb
echo "e2e693d6490e5d33ef4310a48cbd36f2b1c67cb5fc5cbb6a55d1118836d453c5  ntfy_2.29.0_linux_amd64.deb" | sha256sum -c -
dpkg -i ntfy_2.29.0_linux_amd64.deb   # ships ntfy.service + ntfy user + /etc/ntfy/server.yml
```

Version pinned: **v2.29.0** (released 2026-10-07 — v2.30.0 is one day old;
prefer the release with soak time). Checksum from the release's own
`checksums.txt`. If the tarball is preferred over the deb:
`ntfy_2.29.0_linux_amd64.tar.gz` sha256
`7862bcb9bc422d9f442fffa72b6393386475f880079edd0978a5d31d3307314e`.

Then install `server.yml` (this repo) over `/etc/ntfy/server.yml`, generate
the VAPID pair **on ns2's container** and edit the two `web-push-*-key`
lines in place:

```bash
ntfy webpush keys    # prints VAPID public + private key
# paste into /etc/ntfy/server.yml — private key exists ONLY in that file on
# that container. Never in the repo, TOPOLOGY, chat, or env files.

mkdir -p /etc/systemd/system/ntfy.service.d
# copy ntfy-override.conf there, then:
systemctl daemon-reload && systemctl enable --now ntfy
```

server.yml decisions (verbatim in the file): `base-url` https,
`behind-proxy: true` (X-Forwarded-For is trusted — safe because the only
path in is the host nginx), `auth-default-access: deny-all`,
`enable-signup: false`, `enable-login: true`, `cache-duration: 24h`
(delivery buffer, not archive — alert history lives in alerts.log),
attachments off, rate limits sized for scripted senders.

**iOS upstream:** `upstream-base-url` deliberately unset — operator
decision 2026-10-13, verbatim: **"No iOS — omit it"**. With it unset the
server never contacts ntfy.sh. If an iOS device ever needs push:
`upstream-base-url: "https://ntfy.sh"` sends a per-message poll request
(topic name + message ID, **not** the body — the app polls back for
content) and only for topics that actually have iOS subscribers. Cost is
zero until an iOS subscriber exists; revisit only then.

## 3. nginx on the ns2 host

`aitbc-log-scrub.conf` into `/etc/nginx/conf.d/` (defines `aitbc_scrub`,
identical to SEC-14c), then the vhost file into sites-enabled.

TLS via **certbot `--nginx`** (http-01): the :80 block serves
`/.well-known/acme-challenge/` and redirects the rest; once DNS resolves —
it already does — `certbot --nginx -d ntfy.bubuit.net` issues the cert and
fills the `ssl_certificate*` lines. This is a fresh single-name cert rather
than reusing another host's material: independent blast radius, no key
copies across machines.

The vhost carries websocket upgrade headers, `proxy_read/send_timeout 12h`
(long-lived ws/long-poll streams must not be reaped), `proxy_buffering
off`, and logs with `aitbc_scrub` — query strings never reach the log, and
the JSON publish API keeps the topic out of the URL (§5).

```bash
nginx -t && systemctl reload nginx
certbot --nginx -d ntfy.bubuit.net   # once; rewrites ssl_* lines in place
```

## 4. Access plan (operator runs on ns2's container, output stays there)

```bash
incus exec ntfy -- bash

# writer: used by the watchers, may ONLY publish to aitbc-alerts
ntfy user add alerts-writer                 # prompts for a password (admin API login, not used by watchers)
ntfy access alerts-writer aitbc-alerts write-only
ntfy token add alerts-writer                # prints tk_... — the watcher token

# reader: the operator's phone/browser login
ntfy user add operator                      # prompts for password
ntfy access operator aitbc-alerts read-only
ntfy access operator aitbc-heartbeat read-only

# optional second heartbeat sender (see §6)
ntfy user add heartbeat2
ntfy access heartbeat2 aitbc-heartbeat write-only
ntfy token add heartbeat2
```

The token and passwords are typed/pasted on ns2 and land only in the
watchers' env files later (SD-2b wiring task) — never in this repo,
TOPOLOGY, or chat. `deny-all` default means no other topic is reachable.

## 5. Message hygiene

Watchers publish with the JSON API — topic in the POST body, never in the
URL:

```json
POST / {"topic": "aitbc-alerts",
        "title": "<alert name> on <host>",
        "priority": 4,
        "tags": ["warning"],
        "message": "<severity>: <short summary>",
        "click": "https://hub.aitbc.bubuit.net/explorer-api/alerts"}
```

Allowed fields: alert name, host, severity, link to the public alerts page.
**Never**: wallet/node addresses, tx hashes, keys, file paths, env values.
Query-string publishing (`?message=`) is banned — although aitbc_scrub
already drops query strings from the access log.

## 6. Heartbeat

Hourly "all quiet" from hub to `aitbc-heartbeat` (separate topic,
`priority: 1` — no notification sound) via a systemd timer or cron:

```bash
curl -s -H "Authorization: Bearer tk_..." -d \
  '{"topic":"aitbc-heartbeat","message":"all quiet","priority":1}' \
  https://ntfy.bubuit.net/
```

Absence notice: no heartbeat within ~75 min means *something* in the chain
is dead — hub's sender, or ntfy, or ns2 itself (which also serves the
public hub vhost, so that outage is noticed anyway). Optional second
sender on node0 posting at :30 past distinguishes the cases: both silent ⇒
ns2/ntfy down; only hub's missing ⇒ hub's watcher path down.

## 7. Verification (operator, on ns2)

```bash
# publish as the watcher token — should return a message JSON
curl -s -H "Authorization: Bearer tk_..." -d \
  '{"topic":"aitbc-alerts","title":"selftest","message":"ok","priority":3}' \
  https://ntfy.bubuit.net/

# unauthenticated read must be refused (401/403)
curl -s -o /dev/null -w "%{http_code}\n" https://ntfy.bubuit.net/aitbc-alerts/json

# wrong-permission write must be refused (operator is read-only)
curl -s -o /dev/null -w "%{http_code}\n" -u operator:<pw> -d \
  '{"topic":"aitbc-alerts","message":"x"}' https://ntfy.bubuit.net/
```

Then: phone/browser subscription receives the selftest; close and reopen
the browser (or lock the phone) and confirm web push still delivers —
that exercises the VAPID pair.

## 8. Rollback

```bash
# on ns2:
nginx -t && rm /etc/nginx/sites-enabled/ntfy.bubuit.net \
    /etc/nginx/conf.d/aitbc-log-scrub.conf && systemctl reload nginx
certbot delete --cert-name ntfy.bubuit.net   # optional; cert expires harmlessly
incus stop ntfy && incus delete ntfy
incus storage volume delete default ntfy-data
# last: remove the ntfy.bubuit.net DNS record at the DNS provider
```
