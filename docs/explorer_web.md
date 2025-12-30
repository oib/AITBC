# Explorer Web – Task Breakdown

## Status (2025-12-30)

- **Stage 1**: ✅ **DEPLOYED** - Explorer Web successfully deployed in production at https://aitbc.bubuit.net/explorer/
  - All pages implemented with mock data integration, responsive design, and live data toggle
  - Genesis block (height 0) properly displayed
  - Mock/live data toggle functional
  - nginx proxy configured at `/explorer/` route
- **Stage 2**: ✅ Completed - Live mode validated against coordinator endpoints with Playwright e2e tests.
- **Stage 3**: ✅ Completed - JavaScript error fixes deployed (2025-12-30)
  - Fixed "can't access property 'length', t is undefined" error on page load
  - Updated fetchMock function to return correct data structure
  - Added defensive null checks across all page init functions

## Stage 1 (MVP) - COMPLETED

- **Structure & Assets**
  - ✅ Populate `apps/explorer-web/public/` with `index.html` and all page scaffolds.
  - ✅ Add base stylesheets (`public/css/base.css`, `public/css/layout.css`, `public/css/theme.css`).
  - ✅ Include logo and icon assets under `public/assets/`.

- **TypeScript Modules**
  - ✅ Provide configuration and data helpers (`src/config.ts`, `src/lib/mockData.ts`, `src/lib/models.ts`).
  - ✅ Add shared store/utilities module for cross-page state.
  - ✅ Implement core page controllers and components under `src/pages/` and `src/components/` (overview, blocks, transactions, addresses, receipts, header/footer, data mode toggle).

- **Mock Data**
  - ✅ Provide mock JSON fixtures under `public/mock/`.
  - ✅ Enable mock/live mode toggle via `getDataMode()` and `<data-mode-toggle>` components.

- **Interaction & UX**
  - ✅ Implement search box detection for block numbers, hashes, and addresses.
  - ✅ Add pagination or infinite scroll for block and transaction tables.
  - ✅ Expand responsive polish beyond overview cards (tablet/mobile grid, table hover states).

- **Live Mode Integration**
  - ✅ Hit live coordinator endpoints via nginx (`/api/explorer/blocks`, `/api/explorer/transactions`, `/api/explorer/addresses`, `/api/explorer/receipts`) via `getDataMode() === "live"`.
  - ✅ Add fallbacks + error surfacing for partial/failed live responses.
  - ✅ Implement Playwright e2e tests for live mode functionality.

- **Documentation**
  - ✅ Update `apps/explorer-web/README.md` with build/run instructions and API assumptions.
  - ✅ Capture coordinator API + CORS considerations in README deployment notes.

## Production Deployment Details

- **Container**: Incus container 'aitbc' at `/var/www/aitbc.bubuit.net/explorer/`
- **Build**: Vite + TypeScript build process
- **Port**: Static files served by nginx
- **Access**: https://aitbc.bubuit.net/explorer/
- **Features**: Genesis block display, mock/live toggle, responsive design
- **Mock Data**: Blocks.json with proper `{items: [...]}` structure

## Stage 2+ - IN PROGRESS

- 🔄 Integrate WebSocket streams for live head and mempool updates.
- 🔄 Add token balances and ABI decoding when supported by blockchain node.
- 🔄 Provide export-to-CSV functionality and light/dark theme toggle.
