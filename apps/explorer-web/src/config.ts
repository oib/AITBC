export type DataMode = "mock" | "live";

export interface ExplorerConfig {
  dataMode: DataMode;
  mockBasePath: string;
  apiBaseUrl: string;
}

export const config = {
  // Base URL for the coordinator API
  apiBaseUrl: import.meta.env.VITE_COORDINATOR_API ?? 'https://aitbc.bubuit.net/api',
  // Base path for mock data files (used by fetchMock)
  mockBasePath: '/explorer/mock',
  // Default data mode: "live" or "mock"
  dataMode: 'live', // Changed from 'mock' to 'live'
} as const;
