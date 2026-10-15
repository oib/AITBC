# Content-Security-Policy proposal for the hub website

Status: **proposal only** — applying it requires an nginx change, which is a
separate operator-gated task. No nginx config is modified here.

The site currently ships no CSP header (confirmed against
`examples/nginx/nginx-aitbc.conf.example` — no `Content-Security-Policy`
directive exists). All scripts and styles are same-origin or inline; there
are no third-party includes, so a strict policy is achievable with modest
markup work.

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
