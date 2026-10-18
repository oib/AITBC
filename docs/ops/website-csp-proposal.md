# Content-Security-Policy proposal for the hub website

Status: **enforcing on the hub** (18 Oct 2026 — `Content-Security-Policy`
live after the WEB-CSP-2 externalization removed every inline script and
`on*=` handler; verified by browser click-through under enforcement: an
injected inline `<script>` was refused by `script-src 'self'`, and the
Explorer legend toggle and dashboard Apply/Clear all work). The deployed
policy is stricter than the draft below — it has `script-src 'self'` (no
`unsafe-inline`), `base-uri 'none'`, `frame-ancestors 'self'`, and no
`form-action`. The exact deployed directives are mirrored in
`examples/nginx/nginx-aitbc.conf.example` and guarded by
`tests/unit/test_website_api_contract.py`. The inventories below are kept
as the historical record of what blocked enforcement.

All scripts and styles are same-origin or inline; there are no third-party
includes, so a strict policy is achievable with modest markup work.

## Current repository configuration (proposed — not yet deployed)

The repository now carries the next enforcement step. These changes live in
the checkout and `examples/nginx/nginx-aitbc.conf.example`; they are **not
live on the hub** until a separate deployment approval applies the vhost
diff and restarts the Explorer service.

- **Strict `style-src 'self'`** — the `'unsafe-inline'` token is removed
  from the deployed `style-src`. Every inline `<style>` body moved to a
  per-page stylesheet (`block.css`, `tx.css`, `search.css`,
  `follower-api-key-announcement.css`) and every static `style=` attribute
  moved to shared utility classes in `style.css`. Dynamic chart and
  tx-composition values are still set by trusted first-party JavaScript
  through direct CSSOM writes (`el.style.setProperty` / `el.style.width`),
  which CSP does not block. `tests/unit/test_website_csp_ready.py` bans
  style attributes and `<style>` blocks in first-party HTML/SVG/JS source.
- **Versioned asset caching** — a `map` keyed on `?v=<16-hex>` (the
  `stamp-website-assets.py` stamp) gives `Cache-Control: max-age=31536000,
  immutable` to `.js`/`.css` only. Bare or malformed versions and `.svg`
  get one hour (`max-age=3600`, matching the previous JS/CSS behavior).
  HTML stays `no-cache` even when it carries a `v` query. The maps check
  `$status` so error responses (404 etc.) never get the immutable policy.
- **CSP reporting** — the strict policy gains
  `report-uri /csp-report`. nginx routes POSTs to a new
  `POST /api/csp-report` collector inside the existing blockchain-explorer
  service (`apps/blockchain-explorer/routers/csp.py`) at
  1 request/second per client, burst 20, `client_max_body_size 16k`.
  The collector is POST-only, accepts both the legacy `csp-report`
  envelope and the modern `reports+json` batch (max 16 reports), and
  emits one bounded, sanitized `csp_violation` event through the app
  logger (inspect the Explorer journal for `csp_violation`, or the
  structured logger's `event` field). Reports are untrusted, best-effort
  diagnostics and may be rate limited or rejected. It retains **no** raw
  body, script sample, referrer, URL credentials, query string, or
  fragment; URLs are sanitized to scheme/host/path, capped at 512 chars.
- **Ordering** — the Explorer service must be restarted with the new
  router *before* nginx advertises `report-uri`, or reports 404. HSTS,
  the disabled unrelated routes, and all other host-specific config are
  unchanged.
- **Rollback** — if a page breaks under strict `style-src`, restoring
  `style-src 'self' 'unsafe-inline'` in the vhost CSP string is a
  one-line change; the collector and cache maps do not depend on it.

## Two header layers (verified live, 15 Oct 2026)

nginx `add_header` is **not inherited**: once a `location` block defines any
`add_header` of its own, the server-level set does not apply to that
location. The hub therefore has two distinct header layers:

- **Static pages** (`location /` — the catch-all serving the HTML site)
  define no `add_header`, so they inherit the server-level set:
  `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy:
  strict-origin-when-cross-origin`, `Content-Security-Policy`
  (enforcing since 18 Oct 2026) and `Permissions-Policy`. `location = /dashboard/` and `location = /shop/`
  carry their own `add_header Cache-Control`, which shadows **all**
  server-level headers — so each block repeats the full security set
  verbatim (deployed on hub 15 Oct; verified live — both dashboards serve
  all five headers). If a new static location gains its own `add_header`,
  it must repeat the set the same way.
- **API locations** (`/v1/`, `/rpc/`, `/agent/api/`, …) define their own
  `add_header` CORS lines, which shadow the server-level set — so API
  responses get their security headers from the FastAPI middleware instead.
  Verified by GET (not HEAD — the routes are GET-only and HEAD returns
  405): `content-security-policy: default-src 'self'; script-src 'self'
  'unsafe-inline'; style-src 'self' 'unsafe-inline'`,
  `referrer-policy: strict-origin-when-cross-origin`,
  `permissions-policy: geolocation=(), microphone=(), camera=()`.
  That middleware set is weaker than the static-page set (allows inline
  scripts, no `connect-src`/`object-src`/`frame-ancestors`); aligning it is
  a separate app-side task.

Any new `location` that should carry the security headers must either
define no `add_header` at all or repeat the server-level set — there is no
"add to inherited headers" in nginx.

Report-only has no collection endpoint: violations are visible only in
browser devtools. A `report-to` endpoint is a possible later step.

## Roll-forward: enforcing the policy — done 18 Oct 2026

The blocker (externalizing the inline `<script>` blocks and the `on*=`
handlers inventoried below) shipped in WEB-CSP-2; the `style=` attributes
remain and are covered by `style-src 'self' 'unsafe-inline'`. The hub
vhost was flipped to enforcing `Content-Security-Policy` in one edit,
`nginx -t` + reload, followed by a full-page click-through with the dev
console open — no legitimate resource was refused; an injected inline
`<script>` was blocked as intended. The `report-only` era below is kept
for the record.

## Proposed policy (report-only first)

```text
Content-Security-Policy-Report-Only:
  default-src 'self';
  script-src 'self' 'unsafe-inline' 'unsafe-hashes';
  style-src 'self' 'unsafe-inline';
  connect-src 'self';
  img-src 'self' data:;
  font-src 'self';
  object-src 'none';
  base-uri 'self';
  form-action 'self';
  frame-ancestors 'none';
```

Notes on each decision:

- `connect-src 'self'` — every API call is same-origin (the WEB-4 contract
  table confirms: all extracted calls resolve under `/`,
  `/explorer-api`, `/rpc`, `/v1`, `/exchange`, `/agent`, `/c`,
  `/pool-hub`). No WebSocket or EventSource usage exists in any page.
- `img-src 'self' data:` — `data:` retained only for the CSV-download blob
  pattern in `blocks.js` if it ever lands in an `img`; harmless to keep,
  can be tightened later. All images are local (favicon.svg).
- `object-src 'none'`, `frame-ancestors 'none'` — no plugins, no framing.
- `script-src 'unsafe-inline'` initially — the site cannot run a strict
  script policy yet (see inventory below). `'unsafe-hashes'` would let
  *generated* inline event handlers pass once they are hashed — but they
  are dynamic, so hashes churn; the real fix is removing them.
- `report-only` first so any missed resource fails loudly in telemetry,
  not on visitors. There is no reporting endpoint today; watch via
  browser devtools during staging or add `report-uri`/`report-to` if an
  endpoint is stood up later.

## What blocks a strict policy today

### Inline `<script>` blocks (block `script-src` without `unsafe-inline`)

| page | inline scripts |
|---|---|
| block.html | 1 (page loader + helpers) |
| tx.html | 1 |
| search.html | 1 |
| customer-dashboard.html | 1 |
| shop-dashboard.html | 1 |

Fix path: move each inline block into its own `website/<page>.js` file
loaded `defer` — mechanical, but a separate change set.

### Inline event-handler attributes (HTML + JS-generated)

Static HTML: block.html ×3, search.html ×5, tx.html ×1,
customer-dashboard.html ×2, shop-dashboard.html ×2 (total 13).
JS-generated: explorer.js ×6, index.js ×1 — these are the
`onclick="location.href='...'"` + `onkeydown` navigation patterns added
for keyboard access in WEB-6b, plus `onclick="copyValue(...)"` on copy
buttons (block/tx/search inline, explorer.js, index.js).

Fix path: replace generated-handler markup with `data-href` +
`addEventListener` delegation (one delegated listener per container),
and copy buttons with a `data-copy` + `click` listener (the data-copy
attribute already exists). `unsafe-hashes` is NOT recommended for these
— the attribute values embed per-row URLs, so the hash set is unbounded.

### Inline `style="..."` attributes (block `style-src` without `unsafe-inline`)

Static counts: exchange.html ×23, block.html ×7, search.html ×6,
tx.html ×6, customer-dashboard.html ×4, marketplace.html ×3,
shop-dashboard.html ×3, follower-api-key-announcement ×2, alerts ×1,
blocks ×1, bridges ×1.
JS-generated: explorer.js ×10, dashboard.js ×3, exchange.js ×3,
bridges.js ×1, marketplace.js ×1 (`style=` in templates — mostly
`cursor:pointer`, `width:…%` on the tx-composition bar, muted colors).

Most are presentational (`cursor:pointer`, margins). The only
data-driven one is the tx-composition bar width in explorer.js —
`style="width:${pct}%"` where pct is a computed number (safe content,
but still blocked by a strict style-src).

Fix path: move static styles into style.css classes; for the
composition bar keep `style=` (requires `style-src 'unsafe-inline'`
permanently) or compute it via a CSS custom property
(`style="--w:${pct}%"` + `.tx-comp-seg{width:var(--w)}` — still an
inline style attribute, so same constraint).

### Vendored / self-hosted resources — no action

`/vendor/lucide.min.js` and `style.css` are same-origin; `favicon.svg`
same-origin. No CDN, no external fonts, no iframes.

## Suggested nginx snippet (for review only — do not apply here)

```nginx
# inside the location / block for website pages:
add_header Content-Security-Policy-Report-Only
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    always;
```

Rollout order: (1) report-only for a soak period, (2) move the 5 inline
page scripts to files + replace generated handlers with delegated
listeners, (3) tighten `script-src` (drop `unsafe-inline`), then switch
to enforcing `Content-Security-Policy`. The generated-handler and
inline-script removals are mechanical repo work but out of WEB-9 scope.
