# Marketplace Web – Task Breakdown

## Status (2025-09-27)

- **Stage 1**: Frontend scaffolding pending. Awaiting API definitions from coordinator/pool hub before wiring mock vs real data sources.

## Stage 1 (MVP)

- **Project Initialization**
  - Scaffold Vite + TypeScript project under `apps/marketplace-web/`.
  - Define `package.json`, `tsconfig.json`, `vite.config.ts`, and `.env.example` with `VITE_API_BASE`, `VITE_FEATURE_WALLET`.
  - Configure ESLint/Prettier presets if desired.

- **API Layer**
  - Implement `src/api/http.ts` for base fetch wrapper with mock vs real toggle.
  - Create `src/api/marketplace.ts` with typed functions for offers, bids, stats, wallet.
  - Provide mock JSON files under `public/.mock/` for development.

- **State Management**
  - Implement lightweight store in `src/store/state.ts` with pub/sub and caching.
  - Define shared TypeScript interfaces in `src/store/types.ts` per bootstrap doc.

- **Views & Components**
  - Build router in `src/router.ts` and bootstrap in `src/app.ts`.
  - Implement views: `HomeView`, `OfferDetailView`, `BidsView`, `StatsView`, `WalletView`.
  - Create components: `OfferCard`, `BidForm`, `Table`, `Sparkline`, `Toast` with validation and responsive design.
  - Add filters (region, hardware, price, latency) on home view.

- **Styling & UX**
  - Create CSS files (`styles/base.css`, `styles/layout.css`, `styles/components.css`) implementing dark theme and 960px layout.
  - Ensure accessibility: semantic HTML, focus states, keyboard navigation.
  - Add toast notifications and form validation messaging.

- **Documentation**
  - Update `apps/marketplace-web/README.md` with instructions for dev/build, mock API usage, and configuration.

## Stage 2+

- Integrate real coordinator/pool hub endpoints and authentication.
- Add WebSocket updates for live offer/pricing changes.
- Implement i18n support with dictionaries in `public/i18n/`.
- Add Vitest test suite for utilities and API modules.
