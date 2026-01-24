import { config, type DataMode } from "../config";
import { getDataMode, setDataMode } from "../lib/mockData";

const LABELS: Record<DataMode, string> = {
  mock: "Mock Data",
  live: "Live API",
};

export function initDataModeToggle(onChange: () => void): void {
  const container = document.querySelector<HTMLDivElement>("[data-role='data-mode-toggle']");
  if (!container) return;

  const currentMode = getDataMode();
  const isLive = currentMode === "live";

  container.innerHTML = `
    <div class="data-mode-toggle">
      <span class="mode-label">Data Mode:</span>
      <button class="mode-button ${isLive ? "live" : "mock"}" id="dataModeBtn">
        ${isLive ? "Live API" : "Mock Data"}
      </button>
    </div>
  `;

  const btn = document.getElementById("dataModeBtn") as HTMLButtonElement;
  if (btn) {
    btn.addEventListener("click", () => {
      const newMode = getDataMode() === "live" ? "mock" : "live";
      setDataMode(newMode);
      // Reload the page to refresh data
      window.location.reload();
    });
  }
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
      <small>${mode === "mock" ? "Static JSON samples" : `Coordinator API (${config.apiBaseUrl})`}</small>
    </label>
  `;
}
