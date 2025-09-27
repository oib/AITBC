"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.initDataModeToggle = initDataModeToggle;
var config_1 = require("../config");
var mockData_1 = require("../lib/mockData");
var LABELS = {
    mock: "Mock Data",
    live: "Live API",
};
function initDataModeToggle(onChange) {
    var container = document.querySelector("[data-role='data-mode-toggle']");
    if (!container) {
        return;
    }
    container.innerHTML = renderControls((0, mockData_1.getDataMode)());
    var select = container.querySelector("select[data-mode-select]");
    if (!select) {
        return;
    }
    select.value = (0, mockData_1.getDataMode)();
    select.addEventListener("change", function (event) {
        var value = event.target.value;
        (0, mockData_1.setDataMode)(value);
        document.documentElement.dataset.mode = value;
        onChange();
    });
}
function renderControls(mode) {
    var options = Object.keys(LABELS)
        .map(function (id) { return "<option value=\"".concat(id, "\" ").concat(id === mode ? "selected" : "", ">").concat(LABELS[id], "</option>"); })
        .join("");
    return "\n    <label class=\"data-mode-toggle\">\n      <span>Data Mode</span>\n      <select data-mode-select>\n        ".concat(options, "\n      </select>\n      <small>").concat(mode === "mock" ? "Static JSON samples" : "Coordinator API (".concat(config_1.CONFIG.apiBaseUrl, ")"), "</small>\n    </label>\n  ");
}
