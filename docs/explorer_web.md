# Explorer Web – Task Breakdown

## Status (2025-09-28)

- **Stage 1**: Overview page renders block/transaction/receipt summaries from mock data with empty-state fallbacks. Remaining work focuses on blocks/transactions detail UIs, responsive polish, and live data toggle validation.

## Stage 1 (MVP)

- **Structure & Assets**
  - ⏳ Populate `apps/explorer-web/public/` with `index.html`, `block.html`, `tx.html`, `address.html`, `receipts.html`, `404.html` scaffolds.
  - ✅ Add base stylesheets (`public/css/base.css`, `public/css/layout.css`, `public/css/theme.css`).
  - ⏳ Include logo and icon assets under `public/assets/`.

- **TypeScript Modules**
  - ✅ Provide configuration and data helpers (`src/config.ts`, `src/lib/mockData.ts`, `src/lib/models.ts`).
  - ⏳ Add shared store/utilities module for cross-page state.
  - ✅ Implement core page controllers and components under `src/pages/` and `src/components/` (overview, blocks, transactions, addresses, receipts, header/footer, data mode toggle).

- **Mock Data**
  - ✅ Provide mock JSON fixtures under `public/mock/`.
  - ✅ Enable mock/live mode toggle via `getDataMode()` and `<data-mode-toggle>` components.

- **Interaction & UX**
  - ⏳ Implement search box detection for block numbers, hashes, and addresses.
  - ⏳ Add pagination or infinite scroll for block and transaction tables.
  - ⏳ Expand responsive polish beyond overview cards (tablet/mobile grid, table hover states).

- **Documentation**
  - ✅ Update `apps/explorer-web/README.md` with build/run instructions and API assumptions.
  - ✅ Capture coordinator API + CORS considerations in README deployment notes.

## Stage 2+

- Integrate WebSocket streams for live head and mempool updates.
- Add token balances and ABI decoding when supported by blockchain node.
- Provide export-to-CSV functionality and light/dark theme toggle.
