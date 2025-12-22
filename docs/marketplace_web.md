# Marketplace Web – Task Breakdown

## Status (2025-12-22)

- **Stage 1**: ✅ Completed - Vite + TypeScript project initialized with API layer, auth scaffolding, and mock/live data toggle.
- **Stage 2**: ✅ Completed - Connected to coordinator endpoints with feature flags for live mode rollout.

## Stage 1 (MVP) - Completed

- **Project Initialization**
  - ✅ Scaffold Vite + TypeScript project under `apps/marketplace-web/`.
  - ✅ Define `package.json`, `tsconfig.json`, `vite.config.ts`, and `.env.example` with `VITE_API_BASE`, `VITE_FEATURE_WALLET`.
  - ✅ Configure ESLint/Prettier presets.

- **API Layer**
  - ✅ Implement `src/api/http.ts` for base fetch wrapper with mock vs real toggle.
  - ✅ Create `src/api/marketplace.ts` with typed functions for offers, bids, stats, wallet.
  - ✅ Provide mock JSON files under `public/mock/` for development.

- **State Management**
  - ✅ Implement lightweight store in `src/lib/api.ts` with pub/sub and caching.
  - ✅ Define shared TypeScript interfaces in `src/lib/types.ts`.

- **Views & Components**
  - ✅ Build router in `src/main.ts` and bootstrap application.
  - ✅ Implement views: offer list, bid form, stats cards.
  - ✅ Create components with validation and responsive design.
  - ✅ Add filters (region, hardware, price, latency).

- **Styling & UX**
  - ✅ Create CSS system implementing design and responsive layout.
  - ✅ Ensure accessibility: semantic HTML, focus states, keyboard navigation.
  - ✅ Add toast notifications and form validation messaging.

- **Authentication**
  - ✅ Implement auth/session scaffolding in `src/lib/auth.ts`.
  - ✅ Add feature flags for marketplace actions.

- **Documentation**
  - ✅ Update `apps/marketplace-web/README.md` with instructions for dev/build, mock API usage, and configuration.

## Stage 2+

- Integrate real coordinator/pool hub endpoints and authentication.
- Add WebSocket updates for live offer/pricing changes.
- Implement i18n support with dictionaries in `public/i18n/`.
- Add Vitest test suite for utilities and API modules.
