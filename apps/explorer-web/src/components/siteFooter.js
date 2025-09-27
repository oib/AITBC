"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.siteFooter = siteFooter;
function siteFooter() {
    var year = new Date().getFullYear();
    return "\n    <footer class=\"site-footer\">\n      <div class=\"site-footer__inner\">\n        <p>&copy; ".concat(year, " AITBC Foundation. Explorer UI under active development.</p>\n      </div>\n    </footer>\n  ");
}
