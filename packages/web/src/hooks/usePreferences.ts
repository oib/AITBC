import { useEffect, useState } from "react";

export interface AitbcPreferences {
  mode: "system" | "light" | "dark" | "high-contrast";
  reducedMotion: boolean;
  highContrast: boolean;
}

const STORAGE_KEY = "aitbc-theme-preference";

const DEFAULTS: AitbcPreferences = {
  mode: "system",
  reducedMotion: false,
  highContrast: false,
};

export function usePreferences(): {
  preferences: AitbcPreferences;
  setPreferences: (prefs: Partial<AitbcPreferences>) => void;
} {
  const [preferences, setState] = useState<AitbcPreferences>(DEFAULTS);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setState({ ...DEFAULTS, ...parsed });
      }
    } catch {
      // ignore parse/storage errors
    }
  }, []);

  const setPreferences = (prefs: Partial<AitbcPreferences>) => {
    setState((current) => {
      const next = { ...current, ...prefs };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore storage errors
      }
      return next;
    });
  };

  return { preferences, setPreferences };
}
