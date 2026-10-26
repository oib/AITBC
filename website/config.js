/**
 * AITBC website shared configuration.
 *
 * Loaded before other website scripts so they can reference a single source of
 * truth for the chain id and explorer API base URL. Loaded via a <script> tag
 * in the HTML pages that need it (explorer.html, marketplace.html).
 *
 * v0.5.3 (Agent B, item B6): extracted hardcoded chain_id from explorer.js and
 * marketplace.js into this shared module.
 */
window.AITBC_CONFIG = Object.freeze({
    // Chain identifier used by the explorer/marketplace analytics endpoints.
    chainId: 'bc-2',
    // Base URL for the explorer API (proxied by nginx).
    explorerApiUrl: '/explorer-api',
    // Bridge payout account — public on-chain sender of every ETH→AIT bridge
    // payout. Used by bridges.html to list recent payouts through the public
    // explorer search (no wallet-ledger data leaves loopback).
    bridgePayoutAddress: '0x356ddE1ced333D7F4d40308fef824260ADbA7c4A',
});
