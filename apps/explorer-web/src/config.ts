export type DataMode = "mock" | "live";

export interface ExplorerConfig {
  dataMode: DataMode;
  mockBasePath: string;
  apiBaseUrl: string;
}

export const CONFIG: ExplorerConfig = {
  // Base URL for the coordinator API
  apiBaseUrl: "https://aitbc.bubuit.net/api",
  // Base path for mock data files (used by fetchMock)
  mockBasePath: "/explorer/mock",
  // Default data mode: "live" or "mock"
  dataMode: "live" as "live" | "mock",
};
