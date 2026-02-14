import { loadSession } from "./auth";

export type DataMode = "mock" | "live";

interface OfferRecord {
  id: string;
  provider: string;
  capacity: number;
  price: number;
  sla: string;
  status: string;
}

interface OffersResponse {
  offers: OfferRecord[];
}

export interface MarketplaceStats {
  totalOffers: number;
  openCapacity: number;
  averagePrice: number;
  activeBids: number;
}

export interface MarketplaceOffer extends OfferRecord {}

const CONFIG = {
  dataMode: (import.meta.env?.VITE_MARKETPLACE_DATA_MODE as DataMode) ?? "mock",
  mockBase: "/mock",
  apiBase: import.meta.env?.VITE_MARKETPLACE_API ?? "http://localhost:8081",
  enableBids:
    (import.meta.env?.VITE_MARKETPLACE_ENABLE_BIDS ?? "true").toLowerCase() !==
    "false",
  requireAuth:
    (import.meta.env?.VITE_MARKETPLACE_REQUIRE_AUTH ?? "false").toLowerCase() ===
    "true",
};

function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Cache-Control": "no-cache",
  };

  const session = loadSession();
  if (session) {
    headers.Authorization = `Bearer ${session.token}`;
  }

  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...buildHeaders(),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchMarketplaceStats(): Promise<MarketplaceStats> {
  if (CONFIG.dataMode === "mock") {
    return request<MarketplaceStats>(`${CONFIG.mockBase}/stats.json`);
  }

  return request<MarketplaceStats>(`${CONFIG.apiBase}/marketplace/stats`);
}

export async function fetchMarketplaceOffers(): Promise<MarketplaceOffer[]> {
  if (CONFIG.dataMode === "mock") {
    const payload = await request<OffersResponse>(`${CONFIG.mockBase}/offers.json`);
    return payload.offers;
  }

  return request<MarketplaceOffer[]>(`${CONFIG.apiBase}/marketplace/offers`);
}

export async function submitMarketplaceBid(input: {
  provider: string;
  capacity: number;
  price: number;
  notes?: string;
}): Promise<void> {
  if (!CONFIG.enableBids) {
    throw new Error("Bid submissions are disabled by configuration");
  }

  if (CONFIG.dataMode === "mock") {
    await new Promise((resolve) => setTimeout(resolve, 600));
    return;
  }

  if (CONFIG.requireAuth && !loadSession()) {
    throw new Error("Authentication required to submit bids");
  }

  const response = await fetch(`${CONFIG.apiBase}/marketplace/bids`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildHeaders(),
    },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to submit bid");
  }
}

export const MARKETPLACE_CONFIG = CONFIG;
