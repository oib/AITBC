export type DataMode = "mock" | "live";

export interface ExplorerConfig {
  dataMode: DataMode;
  mockBasePath: string;
  apiBaseUrl: string;
}

export const CONFIG: ExplorerConfig = {
  // Toggle between "mock" (static JSON under public/mock/) and "live" coordinator APIs.
  dataMode: (import.meta.env?.VITE_DATA_MODE as DataMode) ?? "mock",
  mockBasePath: "/mock",
  apiBaseUrl: import.meta.env?.VITE_COORDINATOR_API ?? "http://localhost:8000",
};
