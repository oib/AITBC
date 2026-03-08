export interface MarketplaceSession {
  token: string;
  expiresAt: number;
}

const STORAGE_KEY = "marketplace-session";

export function saveSession(session: MarketplaceSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function loadSession(): MarketplaceSession | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const data = JSON.parse(raw) as MarketplaceSession;
    if (typeof data.token === "string" && typeof data.expiresAt === "number") {
      if (data.expiresAt > Date.now()) {
        return data;
      }
      clearSession();
    }
  } catch (error) {
    console.warn("Failed to parse stored marketplace session", error);
  }
  return null;
}

export function clearSession(): void {
  localStorage.removeItem(STORAGE_KEY);
}
