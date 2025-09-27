"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
require("../public/css/theme.css");
require("../public/css/base.css");
require("../public/css/layout.css");
var siteHeader_1 = require("./components/siteHeader");
var siteFooter_1 = require("./components/siteFooter");
var overview_1 = require("./pages/overview");
var blocks_1 = require("./pages/blocks");
var transactions_1 = require("./pages/transactions");
var addresses_1 = require("./pages/addresses");
var receipts_1 = require("./pages/receipts");
var dataModeToggle_1 = require("./components/dataModeToggle");
var mockData_1 = require("./lib/mockData");
var overviewConfig = {
    title: overview_1.overviewTitle,
    render: overview_1.renderOverviewPage,
    init: overview_1.initOverviewPage,
};
var routes = {
    "/": overviewConfig,
    "/index.html": overviewConfig,
    "/blocks": {
        title: blocks_1.blocksTitle,
        render: blocks_1.renderBlocksPage,
        init: blocks_1.initBlocksPage,
    },
    "/transactions": {
        title: transactions_1.transactionsTitle,
        render: transactions_1.renderTransactionsPage,
        init: transactions_1.initTransactionsPage,
    },
    "/addresses": {
        title: addresses_1.addressesTitle,
        render: addresses_1.renderAddressesPage,
        init: addresses_1.initAddressesPage,
    },
    "/receipts": {
        title: receipts_1.receiptsTitle,
        render: receipts_1.renderReceiptsPage,
        init: receipts_1.initReceiptsPage,
    },
};
function render() {
    var _a, _b, _c;
    var root = document.querySelector("#app");
    if (!root) {
        console.warn("[Explorer] Missing #app root element");
        return;
    }
    document.documentElement.dataset.mode = (0, mockData_1.getDataMode)();
    var currentPath = window.location.pathname.replace(/\/$/, "");
    var normalizedPath = currentPath === "" ? "/" : currentPath;
    var page = (_a = routes[normalizedPath]) !== null && _a !== void 0 ? _a : null;
    root.innerHTML = "\n    ".concat((0, siteHeader_1.siteHeader)((_b = page === null || page === void 0 ? void 0 : page.title) !== null && _b !== void 0 ? _b : "Explorer"), "\n    <main class=\"page\">").concat((page !== null && page !== void 0 ? page : notFoundPageConfig).render(), "</main>\n    ").concat((0, siteFooter_1.siteFooter)(), "\n  ");
    (0, dataModeToggle_1.initDataModeToggle)(render);
    void ((_c = page === null || page === void 0 ? void 0 : page.init) === null || _c === void 0 ? void 0 : _c.call(page));
}
var notFoundPageConfig = {
    title: "Not Found",
    render: function () { return "\n    <section class=\"not-found\">\n      <h2>Page Not Found</h2>\n      <p>The requested view is not available yet.</p>\n    </section>\n  "; },
};
document.addEventListener("DOMContentLoaded", render);
