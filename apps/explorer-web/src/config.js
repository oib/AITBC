"use strict";
var _a, _b, _c, _d;
Object.defineProperty(exports, "__esModule", { value: true });
exports.CONFIG = void 0;
exports.CONFIG = {
    // Toggle between "mock" (static JSON under public/mock/) and "live" coordinator APIs.
    dataMode: (_b = (_a = import.meta.env) === null || _a === void 0 ? void 0 : _a.VITE_DATA_MODE) !== null && _b !== void 0 ? _b : "mock",
    mockBasePath: "/mock",
    apiBaseUrl: (_d = (_c = import.meta.env) === null || _c === void 0 ? void 0 : _c.VITE_COORDINATOR_API) !== null && _d !== void 0 ? _d : "http://localhost:8000",
};
