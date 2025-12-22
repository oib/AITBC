# marketplace-web

Web app for listing compute **offers**, placing **bids**, and viewing **market stats** in the AITBC stack.  
Stage-aware: works **now** against a mock API, later switches to **coordinator/pool-hub/blockchain** endpoints without touching the UI.

## Goals

1. Browse offers (GPU/CPU, price per token, location, queue, latency).
2. Place/manage bids (instant or scheduled).
3. Watch market stats (price trends, filled volume, miner capacity).
4. Wallet view (balance, recent tx; read-only first).
5. Internationalization (EU langs later), dark theme, 960px layout.

## Tech/Structure (Windsurf-friendly)

- Vanilla **TypeScript + Vite** (no React), separate JS/CSS files.
- File layout (desktop 960px grid, mobile-first CSS, dark theme):

```
marketplace-web/
├─ public/
│  ├─ icons/              # favicons, app icons
│  └─ i18n/               # JSON dictionaries (en/… later)
├─ src/
│  ├─ app.ts              # app bootstrap/router
│  ├─ router.ts           # hash-router (/, /offer/:id, /bids, /stats, /wallet)
│  ├─ api/
│  │  ├─ http.ts          # fetch wrapper + baseURL swap (mock → real)
│  │  └─ marketplace.ts   # typed API calls
│  ├─ store/
│  │  ├─ state.ts         # global app state (signals or tiny pubsub)
│  │  └─ types.ts         # shared types/interfaces
│  ├─ views/
│  │  ├─ HomeView.ts
│  │  ├─ OfferDetailView.ts
│  │  ├─ BidsView.ts
│  │  ├─ StatsView.ts
│  │  └─ WalletView.ts
│  ├─ components/
│  │  ├─ OfferCard.ts
│  │  ├─ BidForm.ts
│  │  ├─ Table.ts
│  │  ├─ Sparkline.ts     # minimal chart (no external lib)
│  │  └─ Toast.ts
│  ├─ styles/
│  │  ├─ base.css         # reset, variables, dark theme
│  │  ├─ layout.css       # 960px grid, sections, header/footer
│  │  └─ components.css
│  └─ util/
│     ├─ format.ts        # fmt token, price, time
│     ├─ validate.ts      # input validation
│     └─ i18n.ts          # simple t() loader
├─ index.html
├─ vite.config.ts
└─ README.md
```

## Routes (Hash router)

- `/` — Offer list + filters
- `/offer/:id` — Offer details + **BidForm**
- `/bids` — User bids (open, filled, cancelled)
- `/stats` — Price/volume/capacity charts
- `/wallet` — Balance + last 10 tx (read-only)

## UI/UX Spec

- **Dark theme**, accent = ice-blue/white outlines (fits OIB style).
- **960px max width** desktop, mobile-first, Nothing Phone 2a as reference.
- **Toast** bottom-center for actions.
- Forms: no animations, clear validation, disable buttons during submit.

## Data Types (minimal)

```ts
type TokenAmount = `${number}`;        // keep as string to avoid FP errors
type PricePerToken = `${number}`;

interface Offer {
  id: string;
  provider: string;                     // miner or pool label
  hw: { gpu: string; vramGB?: number; cpu?: string };
  region: string;                       // e.g., eu-central
  queue: number;                        // jobs waiting
  latencyMs: number;
  price: PricePerToken;                 // AIToken per 1k tokens processed
  minTokens: number;
  maxTokens: number;
  updatedAt: string;
}

interface BidInput {
  offerId: string;
  tokens: number;                       // requested tokens to process
  maxPrice: PricePerToken;              // cap
}

interface Bid extends BidInput {
  id: string;
  status: "open" | "filled" | "cancelled" | "expired";
  createdAt: string;
  filledTokens?: number;
  avgFillPrice?: PricePerToken;
}

interface MarketStats {
  ts: string[];
  medianPrice: number[];                // per interval
  filledVolume: number[];               // tokens
  capacity: number[];                   // available tokens
}

interface Wallet {
  address: string;
  balance: TokenAmount;
  recent: Array<{ id: string; kind: "mint"|"spend"|"refund"; amount: TokenAmount; at: string }>;
}
```

## Mock API (Stage 0)

Base URL: `/.mock` (served via Vite dev middleware or static JSON)

- `GET /.mock/offers.json` → `Offer[]`
- `GET /.mock/offers/:id.json` → `Offer`
- `POST /.mock/bids` (body `BidInput`) → `Bid`
- `GET /.mock/bids.json` → `Bid[]`
- `GET /.mock/stats.json` → `MarketStats`
- `GET /.mock/wallet.json` → `Wallet`

Switch to real endpoints by changing **`BASE_URL`** in `api/http.ts`.

## Real API (Stage 2/3/4 wiring)

When coordinator/pool-hub/blockchain are ready:

- `GET /api/market/offers` → `Offer[]`
- `GET /api/market/offers/:id` → `Offer`
- `POST /api/market/bids` → create bid, returns `Bid`
- `GET /api/market/bids?owner=<wallet>` → `Bid[]`
- `GET /api/market/stats?range=24h|7d|30d` → `MarketStats`
- `GET /api/wallet/summary?addr=<wallet>` → `Wallet`

Auth header (later): `Authorization: Bearer <session-or-wallet-token>`.

## State & Caching

- In-memory store (`store/state.ts`) with tiny pub/sub.
- Offer list cached 30s; stats cached 60s; bust on route change if stale.
- Optimistic UI for **Bid** create; reconcile on server response.

## Filters (Home)

- Region (multi)
- HW capability (GPU model, min VRAM, CPU present)
- Price range (slider)
- Latency max (ms)
- Queue max

All filters are client-side over fetched offers (server-side later).

## Validation Rules

- `BidInput.tokens` ∈ `[offer.minTokens, offer.maxTokens]`.
- `maxPrice >= offer.price` for instant fill hint; otherwise place as limit.
- Warn if `queue > threshold` or `latencyMs > threshold`.

## Security Notes (Web)

- Input sanitize; never eval.  
- CSRF not needed for read-only; for POST use standard token once auth exists.
- Rate-limit POST (server).  
- Display wallet **read-only** unless signing is integrated (later via wallet-daemon).

## i18n

- `public/i18n/en.json` as root.  
- `util/i18n.ts` provides `t(key, params?)`.  
- Keys only (no concatenated sentences). EU languages can be added later via your i18n tool.

## Accessibility

- Semantic HTML, label every input, focus states visible.
- Keyboard: Tab order, Enter submits forms, Esc closes dialogs.
- Color contrast AA in dark theme.

## Minimal Styling Rules

- `styles/base.css`: CSS variables for colors, spacing, radius.  
- `styles/layout.css`: header, main container (max-width: 960px), grid for cards.  
- `styles/components.css`: OfferCard, Table, Buttons, Toast.

## Testing

- Manual first:  
  - Offers list loads, filters act.
  - Place bid with edge values.
  - Stats sparkline renders with missing points.
- Later: Vitest for `util/` + `api/` modules.

## Env/Config

- `VITE_API_BASE` → mock or real.
- `VITE_DEFAULT_REGION` → optional default filter.
- `VITE_FEATURE_WALLET=readonly|disabled`.

## Build/Run

```
# dev
npm i
npm run dev

# build
npm run build
npm run preview
```

## Migration Checklist (Mock → Real)

1. Replace `VITE_API_BASE` with coordinator gateway URL.
2. Enable auth header injection when session is present.
3. Wire `/wallet` to wallet-daemon read endpoint.
4. Swap stats source to real telemetry.
5. Keep the same types; server must honor them.

## Open Tasks

- [ ] Create file skeletons per structure above.
- [ ] Add mock JSON under `public/.mock/`.
- [ ] Implement OfferCard + filters.
- [ ] Implement BidForm with validation + optimistic UI.
- [ ] Implement StatsView with `Sparkline` (no external chart lib).
- [ ] Wire `VITE_API_BASE` switch.
- [ ] Basic a11y pass + dark theme polish.
- [ ] Wallet view (read-only).

