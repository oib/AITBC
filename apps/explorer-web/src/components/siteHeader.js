"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.siteHeader = siteHeader;
function siteHeader(title) {
    return "\n    <header class=\"site-header\">\n      <div class=\"site-header__inner\">\n        <a class=\"site-header__brand\" href=\"/\">AITBC Explorer</a>\n        <h1 class=\"site-header__title\">".concat(title, "</h1>\n        <div class=\"site-header__controls\">\n          <div data-role=\"data-mode-toggle\"></div>\n        </div>\n        <nav class=\"site-header__nav\">\n          <a href=\"/\">Overview</a>\n          <a href=\"/blocks\">Blocks</a>\n          <a href=\"/transactions\">Transactions</a>\n          <a href=\"/addresses\">Addresses</a>\n          <a href=\"/receipts\">Receipts</a>\n        </nav>\n      </div>\n    </header>\n  ");
}
