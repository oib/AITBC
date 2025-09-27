# Explorer Web – Task Breakdown

## Status (2025-09-27)

- **Stage 1**: UI scaffolding and mock data remain TODO; no implementation merged yet. Pending work should align with coordinator receipt history once backend endpoints stabilize.

## Stage 1 (MVP)

- **Structure & Assets**
  - Populate `apps/explorer-web/public/` with `index.html`, `block.html`, `tx.html`, `address.html`, `receipts.html`, `404.html` scaffolds.
  - Add base stylesheets (`css/base.css`, `css/layout.css`, `css/theme-dark.css`).
  - Include logo and icon assets under `public/assets/`.

- **JavaScript Modules**
  - Implement `js/config.js`, `js/api.js`, `js/store.js`, and `js/utils.js` helpers.
  - Create component modules under `js/components/` (header, footer, searchbox, block-table, tx-table, pager, keyvalue).
  - Implement page controllers under `js/pages/` for home, block detail, tx detail, address view, receipts view.

- **Mock Data**
  - Provide optional mock JSON fixtures under `public/js/vendors/` or `public/mock/`.
  - Enable mock mode toggle via `CONFIG.USE_MOCK`.

- **Interaction & UX**
  - Implement search box detection for block numbers, hashes, and addresses.
  - Add pagination/infinite scroll for block and transaction tables.
  - Ensure dark theme styling with readable typography and table hover states.

- **Documentation**
  - Update `apps/explorer-web/README.md` with build/run instructions and API assumptions.
  - Document required CORS configuration for blockchain node.

## Stage 2+

- Integrate WebSocket streams for live head and mempool updates.
- Add token balances and ABI decoding when supported by blockchain node.
- Provide export-to-CSV functionality and light/dark theme toggle.
