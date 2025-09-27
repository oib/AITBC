"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.addressesTitle = void 0;
exports.renderAddressesPage = renderAddressesPage;
exports.initAddressesPage = initAddressesPage;
var mockData_1 = require("../lib/mockData");
exports.addressesTitle = "Addresses";
function renderAddressesPage() {
    return "\n    <section class=\"addresses\">\n      <header class=\"section-header\">\n        <h2>Address Lookup</h2>\n        <p class=\"lead\">Enter an account address to view recent transactions, balances, and receipt history (mock results shown below).</p>\n      </header>\n      <form class=\"addresses__search\" aria-label=\"Search for an address\">\n        <label class=\"addresses__label\" for=\"address-input\">Address</label>\n        <div class=\"addresses__input-group\">\n          <input id=\"address-input\" name=\"address\" type=\"search\" placeholder=\"0x...\" disabled />\n          <button type=\"submit\" disabled>Search</button>\n        </div>\n        <p class=\"placeholder\">Searching will be enabled after integrating the coordinator/blockchain node endpoints.</p>\n      </form>\n      <section class=\"addresses__details\">\n        <h3>Recent Activity</h3>\n        <table class=\"table addresses__table\">\n          <thead>\n            <tr>\n              <th scope=\"col\">Address</th>\n              <th scope=\"col\">Balance</th>\n              <th scope=\"col\">Tx Count</th>\n              <th scope=\"col\">Last Active</th>\n            </tr>\n          </thead>\n          <tbody id=\"addresses-table-body\">\n            <tr>\n              <td class=\"placeholder\" colspan=\"4\">Loading addresses\u2026</td>\n            </tr>\n          </tbody>\n        </table>\n      </section>\n    </section>\n  ";
}
function initAddressesPage() {
    return __awaiter(this, void 0, void 0, function () {
        var tbody, addresses;
        return __generator(this, function (_a) {
            switch (_a.label) {
                case 0:
                    tbody = document.querySelector("#addresses-table-body");
                    if (!tbody) {
                        return [2 /*return*/];
                    }
                    return [4 /*yield*/, (0, mockData_1.fetchAddresses)()];
                case 1:
                    addresses = _a.sent();
                    if (addresses.length === 0) {
                        tbody.innerHTML = "\n      <tr>\n        <td class=\"placeholder\" colspan=\"4\">No mock addresses available.</td>\n      </tr>\n    ";
                        return [2 /*return*/];
                    }
                    tbody.innerHTML = addresses.map(renderAddressRow).join("");
                    return [2 /*return*/];
            }
        });
    });
}
function renderAddressRow(address) {
    return "\n    <tr>\n      <td><code>".concat(address.address, "</code></td>\n      <td>").concat(address.balance, "</td>\n      <td>").concat(address.txCount, "</td>\n      <td>").concat(new Date(address.lastActive).toLocaleString(), "</td>\n    </tr>\n  ");
}
