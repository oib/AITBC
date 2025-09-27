import { CONFIG, type DataMode } from "../config";
import { getDataMode, setDataMode } from "../lib/mockData";

const LABELS: Record<DataMode, string> = {
  mock: "Mock Data",
  live: "Live API",
};

export function initDataModeToggle(onChange: () => void): void {
  const container = document.querySelector<HTMLDivElement>("[data-role='data-mode-toggle']");
  if (!container) {
    return;
  }

  container.innerHTML = renderControls(getDataMode());

  const select = container.querySelector<HTMLSelectElement>("select[data-mode-select]");
  if (!select) {
    return;
  }

  select.value = getDataMode();
  select.addEventListener("change", (event) => {
    const value = (event.target as HTMLSelectElement).value as DataMode;
    setDataMode(value);
    document.documentElement.dataset.mode = value;
    onChange();
  });
}

function renderControls(mode: DataMode): string {
  const options = (Object.keys(LABELS) as DataMode[])
    .map((id) => `<option value="${id}" ${id === mode ? "selected" : ""}>${LABELS[id]}</option>`)
    .join("");

  return `
    <label class="data-mode-toggle">
      <span>Data Mode</span>
      <select data-mode-select>
        ${options}
      </select>
      <small>${mode === "mock" ? "Static JSON samples" : `Coordinator API (${CONFIG.apiBaseUrl})`}</small>
    </label>
  `;
}
