"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

export type ThemeMode = "system" | "light" | "dark" | "high-contrast";

export interface ThemePreference {
  mode: ThemeMode;
  reducedMotion: boolean;
  highContrast: boolean;
}

interface ThemeContextValue {
  preference: ThemePreference;
  setMode: (mode: ThemeMode) => void;
  setReducedMotion: (enabled: boolean) => void;
  setHighContrast: (enabled: boolean) => void;
}

const STORAGE_KEY = "aitbc-theme-preference";

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function resolveMode(mode: ThemeMode): Exclude<ThemeMode, "system"> {
  if (mode !== "system") return mode;
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function writePreference(pref: ThemePreference): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pref));
  } catch {
    // ignore storage errors in private mode
  }
}

function readPreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        mode: parsed.mode ?? "system",
        reducedMotion: Boolean(parsed.reducedMotion),
        highContrast: Boolean(parsed.highContrast),
      };
    }
  } catch {
    // ignore parse errors
  }
  return {
    mode: "system",
    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    highContrast: window.matchMedia("(prefers-contrast: more)").matches,
  };
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>({
    mode: "system",
    reducedMotion: false,
    highContrast: false,
  });

  useEffect(() => {
    setPreference(readPreference());
  }, []);

  useEffect(() => {
    const resolved = resolveMode(preference.mode);
    document.documentElement.setAttribute("data-aitbc-theme", resolved);

    if (preference.highContrast || resolved === "high-contrast") {
      document.documentElement.setAttribute("data-aitbc-contrast", "high");
    } else {
      document.documentElement.removeAttribute("data-aitbc-contrast");
    }

    if (preference.reducedMotion) {
      document.documentElement.setAttribute("data-aitbc-reduced-motion", "true");
    } else {
      document.documentElement.removeAttribute("data-aitbc-reduced-motion");
    }

    writePreference(preference);
  }, [preference]);

  const value: ThemeContextValue = {
    preference,
    setMode: (mode) => setPreference((p) => ({ ...p, mode })),
    setReducedMotion: (reducedMotion) => setPreference((p) => ({ ...p, reducedMotion })),
    setHighContrast: (highContrast) =>
      setPreference((p) => ({
        ...p,
        highContrast,
        mode: highContrast ? "high-contrast" : p.mode === "high-contrast" ? "system" : p.mode,
      })),
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useAitbcTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useAitbcTheme must be used within a ThemeProvider");
  }
  return ctx;
}
