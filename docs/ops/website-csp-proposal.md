# Content-Security-Policy proposal for the hub website

Status: **report-only deployed on the hub** (15 Oct 2026, operator-named
nginx edit, card-attested). The deployed policy is stricter than the draft
below — it has `script-src 'self'` (no `unsafe-inline`), `base-uri 'none'`,
`frame-ancestors 'self'`, and no `form-action` — so every inline script and
`on*=` handler reports as a violation, which is the intended discovery mode.
The exact deployed directives are mirrored in
`examples/nginx/nginx-aitbc.conf.example` and guarded by
`tests/unit/test_website_api_contract.py`.

All scripts and styles are same-origin or inline; there are no third-party
includes, so a strict policy is achievable with modest markup work.

## Two header layers (verified live, 15 Oct 2026)

nginx `add_header` is **not inherited**: once a `location` block defines any
`add_header` of its own, the server-level set does not apply to that
location. The hub therefore has two distinct header layers:

- **Static pages** (`location /` — the catch-all serving the HTML site)
  define no `add_header`, so they inherit the server-level set:
  `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy:
  strict-origin-when-cross-origin`, `Content-Security-Policy-Report-Only`
  and `Permissions-Policy`. `location = /dashboard/` and `location = /shop/`
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

## Roll-forward: enforcing the policy

Flipping `Content-Security-Policy-Report-Only` to `Content-Security-Policy`
is **blocked** on externalizing the inline `<script>` blocks, the ~100
`on*=` handlers and the `style` attributes (inventoried below). Until then,
an enforcing policy would break every page. That work is a separate WEB
task, not started.

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
