# explorer-web.md
Chain Explorer (blocks · tx · receipts)

## 0) Purpose
A lightweight, fast, dark-themed web UI to browse a minimal AITBC blockchain:
- Latest blocks & block detail
- Transaction list & detail
- Address detail (balance, nonce, tx history)
- Receipt / logs view
- Simple search (block #, hash, tx hash, address)

MVP reads from **blockchain-node** (HTTP/WS API).
No write operations.

---

## 1) Tech & Conventions
- **Pure frontend** (no backend rendering): static HTML + JS modules + CSS.
- **No frameworks** (keep it portable and fast).
- **Files split**: HTML, CSS, JS in separate files (user preference).
- **ES Modules** with strict typing via JSDoc or TypeScript (optional).
- **Dark theme** with orange/ice accents (brand).
- **No animations** unless explicitly requested.
- **Time format**: UTC ISO + relative (e.g., “2m ago”).

---

## 2) Folder Layout (within workspace)
```
explorer-web/
├─ public/
│  ├─ index.html            # routes: / (latest blocks)
│  ├─ block.html            # /block?hash=... or /block?number=...
│  ├─ tx.html               # /tx?hash=...
│  ├─ address.html          # /address?addr=...
│  ├─ receipts.html         # /receipts?tx=...
│  ├─ 404.html
│  ├─ assets/
│  │  ├─ logo.svg
│  │  └─ icons/*.svg
│  ├─ css/
│  │  ├─ base.css
│  │  ├─ layout.css
│  │  └─ theme-dark.css
│  └─ js/
│     ├─ config.js          # API endpoint(s)
│     ├─ api.js             # fetch helpers
│     ├─ store.js           # simple state cache
│     ├─ utils.js           # formatters (hex, time, numbers)
│     ├─ components/
│     │  ├─ header.js
│     │  ├─ footer.js
│     │  ├─ searchbox.js
│     │  ├─ block-table.js
│     │  ├─ tx-table.js
│     │  ├─ pager.js
│     │  └─ keyvalue.js
│     ├─ pages/
│     │  ├─ home.js         # latest blocks + mempool/heads
│     │  ├─ block.js
│     │  ├─ tx.js
│     │  ├─ address.js
│     │  └─ receipts.js
│     └─ vendors/           # (empty; we keep it native for now)
├─ docs/
│  └─ explorer-web.md       # this file
└─ README.md
```

---

## 3) API Contracts (read-only)
Assume **blockchain-node** exposes:

### 3.1 REST (HTTP)
- `GET /api/chain/head` → `{ number, hash, timestamp }`
- `GET /api/blocks?limit=25&before=<blockNumber>` → `[{number,hash,parentHash,timestamp,txCount,miner,size,gasUsed}]`
- `GET /api/block/by-number/:n` → `{ ...fullBlock }`
- `GET /api/block/by-hash/:h` → `{ ...fullBlock }`
- `GET /api/tx/:hash` → `{ hash, from, to, nonce, value, fee, gas, gasPrice, blockHash, blockNumber, timestamp, input }`
- `GET /api/address/:addr` → `{ address, balance, nonce, txCount }`
- `GET /api/address/:addr/tx?limit=25&before=<blockNumber>` → `[{hash,blockNumber,from,to,value,fee,timestamp}]`
- `GET /api/tx/:hash/receipt` → `{ status, gasUsed, logs: [{address, topics:[...], data, index}], cumulativeGasUsed }`
- `GET /api/search?q=...`
  - Accepts block number, block hash, tx hash, or address
  - Returns a typed result: `{ type: "block"|"tx"|"address" , key: ... }`

### 3.2 WebSocket (optional, later)
- `ws://.../api/stream/heads` → emits new head `{number,hash,timestamp}`
- `ws://.../api/stream/mempool` → emits tx previews `{hash, from, to, value, timestamp}`

> If the node isn’t ready, create a tiny mock server (FastAPI) consistent with these shapes (already planned in other modules).

---

## 4) Pages & UX

### 4.1 Header (every page)
- Left: logo + “AITBC Explorer”
- Center: search box (accepts block#, block/tx hash, address)
- Right: network tag (e.g., “Local Dev”) + head block# (live)

### 4.2 Home `/`
- **Latest Blocks** (table)
  - columns: `#`, `Hash (short)`, `Tx`, `Miner`, `GasUsed`, `Time`
  - infinite scroll / “Load older”
- (optional) **Mempool feed** (compact list, toggleable)
- Empty state: helpful instructions + sample query strings

### 4.3 Block Detail `/block?...`
- Top summary (KeyValue component)
  - `Number, Hash, Parent, Miner, Timestamp, Size, GasUsed, Difficulty?`
- Transactions table (paginated)
- “Navigate”: Parent ↖, Next ↗, View in raw JSON (debug)

### 4.4 Tx Detail `/tx?hash=...`
- Summary: `Hash, Status, Block, From, To, Value, Fee, Nonce, Gas(gasPrice)`
- Receipt section (logs rendered as topics/data, collapsible)
- Input data: hex preview + decode attempt (if ABI registry exists – later)

### 4.5 Address `/address?addr=...`
- Summary: `Address, Balance, Nonce, TxCount`
- Transactions list (sent/received filter)
- (later) Token balances when chain supports it

### 4.6 Receipts `/receipts?tx=...`
- Focused receipts + logs view with copy buttons

### 4.7 404
- Friendly message + search

---

## 5) Components (JS modules)
- `header.js` : builds header + binds search submit.
- `searchbox.js` : debounced input, detects type (see utils).
- `block-table.js` : render rows, short-hash, time-ago.
- `tx-table.js` : similar render with direction arrows.
- `pager.js` : simple “Load more” with event callback.
- `keyvalue.js` : `<dl>` key/value grid for details.
- `footer.js` : version, links.

---

## 6) Utils
- `formatHexShort(hex, bytes=4)` → `0x1234…abcd`
- `formatNumber(n)` with thin-space groupings
- `formatValueWei(wei)` → AIT units when available (or plain wei)
- `timeAgo(ts)` + `formatUTC(ts)`
- `parseQuery()` helpers for `?hash=...`
- `detectSearchType(q)`:
  - `0x` + 66 chars → tx/block hash
  - numeric → block number
  - `0x` + 42 → address
  - fallback → “unknown”

---

## 7) State (store.js)
- `state.head` (number/hash/timestamp)
- `state.cache.blocks[number] = block`
- `state.cache.txs[hash] = tx`
- `state.cache.address[addr] = {balance, nonce, txCount}`
- Simple in-memory LRU eviction (optional).

---

## 8) Styling
- `base.css`: resets, typography, links, buttons, tables.
- `layout.css`: header/footer, grid, content widths (max 960px desktop).
- `theme-dark.css`: colors:
  - bg: `#0b0f14`, surface: `#11161c`
  - text: `#e6eef7`
  - accent-orange: `#ff8a00`
  - accent-ice: `#a8d8ff`
- Focus states visible. High contrast table rows on hover.

---

## 9) Error & Loading UX
- Loading spinners (minimal).
- Network errors: inline banner with retry.
- Empty: clear messages & how to search.

---

## 10) Security & Hardening
- Treat inputs as untrusted.
- Only GETs; block any attempt to POST.
- Strict `Content-Security-Policy` sample (for hosting):
  - `default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self' https://blockchain-node.local;`
- Avoid third-party CDNs.

---

## 11) Test Plan (manual first)
1. Home loads head + 25 latest blocks.
2. Scroll/pager loads older batches.
3. Block search by number + by hash.
4. Tx search → detail + receipt.
5. Address search → tx list.
6. Error states when node is offline.
7. Timezones: display UTC consistently.

---

## 12) Dev Tasks (Windsurf order of work)
1. **Scaffold** folders & empty files.
2. Implement `config.js` with `API_BASE`.
3. Implement `api.js` (fetch JSON + error handling).
4. Build `utils.js` (formatters + search detect).
5. Build `header.js` + `footer.js`.
6. Home page: blocks list + pager.
7. Block detail page.
8. Tx detail + receipts.
9. Address page with tx list.
10. 404 + polish (copy buttons, tiny helpers).
11. CSS pass (dark theme).
12. Final QA.

---

## 13) Mock Data (for offline dev)
Place under `public/js/vendors/mock.js` (opt-in):
- Export functions that resolve Promises with static JSON fixtures in `public/mock/*.json`.
- Toggle via `config.js` flag `USE_MOCK=true`.

---

## 14) Minimal HTML Skeleton (example: index.html)
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>AITBC Explorer</title>
    <link rel="stylesheet" href="./css/base.css" />
    <link rel="stylesheet" href="./css/layout.css" />
    <link rel="stylesheet" href="./css/theme-dark.css" />
  </head>
  <body>
    <header id="app-header"></header>
    <main id="app"></main>
    <footer id="app-footer"></footer>
    <script type="module">
      import { renderHeader } from './js/components/header.js';
      import { renderFooter } from './js/components/footer.js';
      import { renderHome }   from './js/pages/home.js';
      renderHeader(document.getElementById('app-header'));
      renderFooter(document.getElementById('app-footer'));
      renderHome(document.getElementById('app'));
    </script>
  </body>
</html>
```

---

## 15) config.js (example)
```js
export const CONFIG = {
  API_BASE: 'http://localhost:8545', // adapt to blockchain-node
  USE_MOCK: false,
  PAGE_SIZE: 25,
  NETWORK_NAME: 'Local Dev',
};
```

---

## 16) API Helpers (api.js — sketch)
```js
import { CONFIG } from './config.js';

async function jget(path) {
  const res = await fetch(`${CONFIG.API_BASE}${path}`, { method: 'GET' });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  head:      () => jget('/api/chain/head'),
  blocks:    (limit, before) => jget(`/api/blocks?limit=${limit}&before=${before ?? ''}`),
  blockByNo: (n) => jget(`/api/block/by-number/${n}`),
  blockByHash: (h) => jget(`/api/block/by-hash/${h}`),
  tx:        (hash) => jget(`/api/tx/${hash}`),
  receipt:   (hash) => jget(`/api/tx/${hash}/receipt`),
  address:   (addr) => jget(`/api/address/${addr}`),
  addressTx: (addr, limit, before) => jget(`/api/address/${addr}/tx?limit=${limit}&before=${before ?? ''}`),
  search:    (q) => jget(`/api/search?q=${encodeURIComponent(q)}`),
};
```

---

## 17) Performance Checklist
- Use pagination/infinite scroll (no huge payloads).
- Cache recent blocks/tx in-memory (store.js).
- Avoid layout thrash: table builds via DocumentFragment.
- Defer non-critical fetches (e.g., mempool).
- Keep CSS small and critical.

---

## 18) Deployment
- Serve `public/` via Nginx under `/explorer/` or own domain.
- Set correct `connect-src` in CSP to point to blockchain-node.
- Ensure CORS on blockchain-node for the explorer origin (read-only).

---

## 19) Roadmap (post-MVP)
- Live head updates via WS.
- Mempool stream view.
- ABI registry + input decoding.
- Token balances (when chain supports).
- Export to CSV / JSON for tables.
- Theming switch (dark/light).

---

