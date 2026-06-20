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
    chainId: 'ait-hub.aitbc.bubuit.net',
    // Base URL for the explorer API (proxied by nginx).
    explorerApiUrl: '/explorer-api',
});
