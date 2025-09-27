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
exports.overviewTitle = void 0;
exports.renderOverviewPage = renderOverviewPage;
exports.initOverviewPage = initOverviewPage;
var mockData_1 = require("../lib/mockData");
exports.overviewTitle = "Network Overview";
function renderOverviewPage() {
    return "\n    <section class=\"overview\">\n      <p class=\"lead\">High-level summaries of recent blocks, transactions, and receipts will appear here.</p>\n      <div class=\"overview__grid\">\n        <article class=\"card\">\n          <h3>Latest Block</h3>\n          <ul class=\"stat-list\" id=\"overview-block-stats\">\n            <li class=\"placeholder\">Loading block data\u2026</li>\n          </ul>\n        </article>\n        <article class=\"card\">\n          <h3>Recent Transactions</h3>\n          <ul class=\"stat-list\" id=\"overview-transaction-stats\">\n            <li class=\"placeholder\">Loading transaction data\u2026</li>\n          </ul>\n        </article>\n        <article class=\"card\">\n          <h3>Receipt Metrics</h3>\n          <ul class=\"stat-list\" id=\"overview-receipt-stats\">\n            <li class=\"placeholder\">Loading receipt data\u2026</li>\n          </ul>\n        </article>\n      </div>\n    </section>\n  ";
}
function initOverviewPage() {
    return __awaiter(this, void 0, void 0, function () {
        var _a, blocks, transactions, receipts, blockStats, latest, txStats, succeeded, receiptStats, attested;
        return __generator(this, function (_b) {
            switch (_b.label) {
                case 0: return [4 /*yield*/, Promise.all([
                        (0, mockData_1.fetchBlocks)(),
                        (0, mockData_1.fetchTransactions)(),
                        (0, mockData_1.fetchReceipts)(),
                    ])];
                case 1:
                    _a = _b.sent(), blocks = _a[0], transactions = _a[1], receipts = _a[2];
                    blockStats = document.querySelector("#overview-block-stats");
                    if (blockStats) {
                        if (blocks.length > 0) {
                            latest = blocks[0];
                            blockStats.innerHTML = "\n        <li><strong>Height:</strong> ".concat(latest.height, "</li>\n        <li><strong>Hash:</strong> ").concat(latest.hash.slice(0, 18), "\u2026</li>\n        <li><strong>Proposer:</strong> ").concat(latest.proposer, "</li>\n        <li><strong>Time:</strong> ").concat(new Date(latest.timestamp).toLocaleString(), "</li>\n      ");
                        }
                        else {
                            blockStats.innerHTML = "<li class=\"placeholder\">No mock block data available.</li>";
                        }
                    }
                    txStats = document.querySelector("#overview-transaction-stats");
                    if (txStats) {
                        if (transactions.length > 0) {
                            succeeded = transactions.filter(function (tx) { return tx.status === "Succeeded"; });
                            txStats.innerHTML = "\n        <li><strong>Total Mock Tx:</strong> ".concat(transactions.length, "</li>\n        <li><strong>Succeeded:</strong> ").concat(succeeded.length, "</li>\n        <li><strong>Pending:</strong> ").concat(transactions.length - succeeded.length, "</li>\n      ");
                        }
                        else {
                            txStats.innerHTML = "<li class=\"placeholder\">No mock transaction data available.</li>";
                        }
                    }
                    receiptStats = document.querySelector("#overview-receipt-stats");
                    if (receiptStats) {
                        if (receipts.length > 0) {
                            attested = receipts.filter(function (receipt) { return receipt.status === "Attested"; });
                            receiptStats.innerHTML = "\n        <li><strong>Total Receipts:</strong> ".concat(receipts.length, "</li>\n        <li><strong>Attested:</strong> ").concat(attested.length, "</li>\n        <li><strong>Pending:</strong> ").concat(receipts.length - attested.length, "</li>\n      ");
                        }
                        else {
                            receiptStats.innerHTML = "<li class=\"placeholder\">No mock receipt data available.</li>";
                        }
                    }
                    return [2 /*return*/];
            }
        });
    });
}
