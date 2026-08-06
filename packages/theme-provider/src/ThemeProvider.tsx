// @ts-nocheck
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

// Media queries are only meaningful in a browser. resolveMode above already guards on
// `typeof window`; readPreference did not, so its fallback branch would throw during any
// server render. It is safe today only because its sole call site is inside a useEffect —
// a latent crash waiting for the first non-effect caller (Next.js/RSC).
function prefersMedia(query: string): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(query).matches;
}

function readPreference(): ThemePreference {
  try {
    if (typeof localStorage !== "undefined") {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return {
          mode: parsed.mode ?? "system",
          reducedMotion: Boolean(parsed.reducedMotion),
          highContrast: Boolean(parsed.highContrast),
        };
      }
    }
  } catch {
    // ignore parse errors
  }
  return {
    mode: "system",
    reducedMotion: prefersMedia("(prefers-reduced-motion: reduce)"),
    highContrast: prefersMedia("(prefers-contrast: more)"),
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
    setMode: (mode) => setPreference((p: ThemePreference) => ({ ...p, mode })),
    setReducedMotion: (reducedMotion) => setPreference((p: ThemePreference) => ({ ...p, reducedMotion })),
    setHighContrast: (highContrast) =>
      setPreference((p: ThemePreference) => ({
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
